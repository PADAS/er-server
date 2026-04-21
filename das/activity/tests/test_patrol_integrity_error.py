"""
Tests for ``SerialNumberModelMixin``'s counter-based serial number allocation.

The mixin allocates per-tenant serial numbers via
per-model counter rows protected by ``SELECT ... FOR UPDATE``.
These tests cover both the API path (where ``PatrolsView.post`` runs inside an
outer ``transaction.atomic``) and the model-level concurrency path.
"""

import logging
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from django.contrib.auth import get_user_model
from django.db import connections
from django.db.transaction import TransactionManagementError
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from activity.models import Patrol
from core.models import DASTenant

User = get_user_model()
logger = logging.getLogger(__name__)

PatrolSerialNumberCounter = Patrol.serial_number_counter_model


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant")
class TestPatrolSerialNumberAllocation(TransactionTestCase):
    """Verify per-tenant serial number allocation through the patrol API."""

    def setUp(self):
        self.tenant = DASTenant.objects.first()

        self.user, _ = User.objects.get_or_create(
            username="testuser_api",
            defaults={
                "email": "testapi@example.com",
                "first_name": "Test",
                "last_name": "User",
                "password": "testpassword123",
                "is_superuser": True,
                "is_staff": True,
            },
        )
        self.user.set_password("testpassword123")
        self.user.save()

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.patrols_url = reverse("patrols")

    def _create_patrol(self, title, objective="objective"):
        response = self.client.post(
            self.patrols_url,
            {"title": title, "state": "open", "objective": objective},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Patrol.objects.get(title=title)

    def _counter(self):
        return PatrolSerialNumberCounter.objects.get(das_tenant_id=self.tenant.id)

    def test_first_insert_seeds_counter_and_assigns_value(self):
        """The first patrol for a tenant should get serial_number = previous max + 1."""
        baseline = (
            self._counter().last_value
            if PatrolSerialNumberCounter.objects.filter(das_tenant_id=self.tenant.id).exists()
            else 0
        )

        patrol = self._create_patrol(f"first-{int(time.time() * 1000)}")

        self.assertEqual(patrol.serial_number, baseline + 1)
        self.assertEqual(self._counter().last_value, baseline + 1)

    def test_sequential_inserts_increment_counter_in_lockstep(self):
        """Each insert advances the counter by exactly one."""
        timestamp = int(time.time() * 1000)
        patrols = [self._create_patrol(f"seq-{timestamp}-{i}") for i in range(5)]

        serial_numbers = [p.serial_number for p in patrols]
        self.assertEqual(serial_numbers, sorted(serial_numbers))
        for earlier, later in zip(serial_numbers, serial_numbers[1:]):
            self.assertEqual(later - earlier, 1)
        self.assertEqual(self._counter().last_value, serial_numbers[-1])

    def test_concurrent_inserts_produce_unique_sequential_serial_numbers(self):
        """20 concurrent API inserts must all succeed with unique, sequential serial numbers."""
        timestamp = int(time.time() * 1000)
        worker_count = 20

        def create(i):
            try:
                response = self.client.post(
                    self.patrols_url,
                    {"title": f"conc-{timestamp}-{i}", "state": "open", "objective": "x"},
                    format="json",
                )
                return response.status_code, response.data
            finally:
                # Each thread holds its own DB connection; release it so the
                # outer test transaction can reset cleanly.
                connections.close_all()

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(create, range(worker_count)))

        for status_code, body in results:
            self.assertEqual(status_code, status.HTTP_201_CREATED, body)

        created = Patrol.objects.filter(das_tenant=self.tenant, title__startswith=f"conc-{timestamp}-").order_by(
            "serial_number"
        )
        serial_numbers = [p.serial_number for p in created]
        self.assertEqual(len(serial_numbers), worker_count)
        self.assertEqual(len(set(serial_numbers)), worker_count, "duplicate serial numbers detected")
        for earlier, later in zip(serial_numbers, serial_numbers[1:]):
            self.assertEqual(later - earlier, 1, f"gap between {earlier} and {later}")
        self.assertEqual(self._counter().last_value, serial_numbers[-1])

    def test_concurrent_insert_latency_has_no_retry_outliers(self):
        """
        Regression test: assert the latency distribution of concurrent inserts
        stays tight (p95 ≤ 5x median).

        The previous retry-based implementation slept 100-600 ms per
        IntegrityError, which would push collided inserts ~100x past the
        median. The counter-based implementation queues briefly on the row
        lock, so all inserts complete within a narrow band regardless of
        machine speed (this assertion is machine-independent).
        """
        timestamp = int(time.time() * 1000)
        worker_count = 20

        def create_and_time(i):
            started = time.perf_counter()
            try:
                response = self.client.post(
                    self.patrols_url,
                    {"title": f"lat-{timestamp}-{i}", "state": "open", "objective": "x"},
                    format="json",
                )
                assert response.status_code == status.HTTP_201_CREATED, response.data
            finally:
                connections.close_all()
            return time.perf_counter() - started

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            durations = sorted(executor.map(create_and_time, range(worker_count)))

        median = statistics.median(durations)
        # statistics.quantiles(..., n=20)[18] gives the 95th percentile.
        p95 = statistics.quantiles(durations, n=20)[18]

        logger.info("concurrent insert latencies: median=%.4fs p95=%.4fs", median, p95)
        self.assertLess(
            p95,
            5 * median,
            f"p95 latency ({p95:.4f}s) exceeds 5x median ({median:.4f}s) — "
            "suggests a retry/sleep regression in serial number allocation",
        )

    def test_first_insert_reconciles_with_preexisting_rows(self):
        """No counter row + existing rows → new insert lands at MAX(serial_number) + 1."""
        patrol = self._create_patrol(f"legacy-{int(time.time() * 1000)}")
        # Simulate a legacy row written without the counter being seeded:
        # bump its serial_number out of band and drop the counter row.
        Patrol.objects.filter(pk=patrol.pk).update(serial_number=9999)
        PatrolSerialNumberCounter.objects.filter(das_tenant_id=self.tenant.id).delete()

        created = self._create_patrol(f"after-legacy-{int(time.time() * 1000)}")

        self.assertEqual(created.serial_number, 10000)
        self.assertEqual(self._counter().last_value, 10000)

    def test_drift_is_healed_on_next_call(self):
        """last_value below MAX(serial_number) is reconciled on the next insert."""
        patrol = self._create_patrol(f"drift-{int(time.time() * 1000)}")
        Patrol.objects.filter(pk=patrol.pk).update(serial_number=500)
        counter = self._counter()
        counter.last_value = 1
        counter.save(update_fields=["last_value"])

        created = self._create_patrol(f"after-drift-{int(time.time() * 1000)}")

        self.assertEqual(created.serial_number, 501)
        self.assertEqual(self._counter().last_value, 501)

    def test_no_transaction_management_error_on_create(self):
        """The API path must not raise TransactionManagementError."""
        try:
            self._create_patrol(f"basic-{int(time.time() * 1000)}")
        except TransactionManagementError as exc:  # pragma: no cover - regression guard
            self.fail(f"TransactionManagementError raised by patrol create: {exc}")

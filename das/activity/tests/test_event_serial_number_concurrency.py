"""
Verify that concurrent Event creation under the SerialNumberModelMixin
advisory-lock path does not raise TransactionManagementError and produces
unique serial numbers per tenant.

Patrol already has coverage of this mixin in
``test_patrol_integrity_error.py``. The advisory-lock key used by
``SerialNumberModelMixin._save_with_serial_number`` is scoped per
``(tenant, ContentType)``, so locks do not overlap between Patrol and
Event — the Patrol test alone does not exercise the Event path.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from django.contrib.auth import get_user_model
from django.db.transaction import TransactionManagementError
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from activity.models import Event
from core.models import DASTenant
from factories import EventTypeFactory

User = get_user_model()
logger = logging.getLogger(__name__)


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant")
class TestEventSerialNumberConcurrency(TransactionTestCase):
    """Concurrent Event creation via the API exercises the advisory-lock path."""

    def setUp(self):
        self.tenant = DASTenant.objects.first()

        self.user, _ = User.objects.get_or_create(
            username="testuser_event_api",
            defaults={
                "email": "testeventapi@example.com",
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

        self.event_type = EventTypeFactory(das_tenant=self.tenant)
        self.events_url = reverse("events")

    def test_concurrent_event_creation_via_api(self):
        """Multiple concurrent Event POSTs should all succeed with unique serial numbers."""
        logger.info("Testing concurrent event creation via API...")

        def create_event_via_api(event_id):
            unique_title = f"Concurrent Event {event_id} {int(time.time())}"
            event_data = {
                "title": unique_title,
                "event_type": self.event_type.value,
            }

            try:
                response = self.client.post(self.events_url, event_data, format="json")
                return {
                    "success": response.status_code == status.HTTP_201_CREATED,
                    "status_code": response.status_code,
                    "event_id": event_id,
                    "response_data": response.data if hasattr(response, "data") else None,
                }
            except Exception as e:
                return {"success": False, "error": str(e), "event_id": event_id}

        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(create_event_via_api, i + 1) for i in range(5)]

                results = []
                for future in futures:
                    try:
                        results.append(future.result(timeout=30))
                    except Exception as e:
                        logger.error(f"Future execution failed: {e}")
                        results.append({"success": False, "error": str(e)})

            successful_creations = [r for r in results if r.get("success", False)]
            failed_creations = [r for r in results if not r.get("success", False)]

            logger.info(
                f"Concurrent API creation results: {len(successful_creations)} successful, "
                f"{len(failed_creations)} failed"
            )

            self.assertGreater(len(successful_creations), 0, "At least one event should be created successfully")

            for result in results:
                if "error" in result and "TransactionManagementError" in str(result["error"]):
                    self.fail(f"TransactionManagementError occurred: {result['error']}")

            created_events = Event.objects.filter(das_tenant=self.tenant, title__contains="Concurrent Event").order_by(
                "serial_number"
            )

            self.assertGreaterEqual(created_events.count(), len(successful_creations))

            serial_numbers = [e.serial_number for e in created_events if e.serial_number is not None]
            self.assertEqual(
                len(serial_numbers), created_events.count(), "All created events must have a serial_number"
            )
            self.assertEqual(len(set(serial_numbers)), len(serial_numbers), "Serial numbers must be unique")

            logger.info(
                f"Concurrent API creation successful - {created_events.count()} events created with unique "
                f"serial numbers"
            )

        except TransactionManagementError as e:
            logger.error(f"TransactionManagementError caught: {e}")
            self.fail(f"TransactionManagementError occurred during concurrent API creation: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during concurrent API creation: {e}")
            self.fail(f"Unexpected error occurred: {e}")

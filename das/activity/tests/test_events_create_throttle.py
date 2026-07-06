"""Tests for per-tenant event-create rate limiting and concurrency cap (ERA-13461).

Design notes
------------
* Cache must be cleared between test runs; the ``clear_throttle_cache``
  fixture below handles this.
* Throttle rates are overridden via ``monkeypatch`` so tests run
  deterministically without touching wall-clock time.
* Tenant isolation is verified by confirming that the cache keys for two
  different tenant IDs are distinct.
* Concurrency guard tests mock ``get_redis_connection`` with a ``fakeredis``
  server so sorted-set logic can be exercised without a running Redis instance.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
import redis
from django_multitenant.utils import set_current_tenant

from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.fields import DateTimeField

from activity.models import Event
from activity.tests.events import ET_OTHER
from activity.throttles import (
    _CONCURRENCY_SLOT_TTL_SECONDS,
    EventCreateThrottle,
    _concurrency_redis_key,
    _event_create_concurrency_slot,
    _get_concurrency_limit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_payload(**overrides) -> dict:
    base = dict(
        title="Throttle Test Event",
        time=DateTimeField().to_representation(datetime.now(tz=timezone.utc)),
        provenance=Event.PC_SYSTEM,
        event_type=ET_OTHER,
        priority=Event.PRI_REFERENCE,
        location=dict(longitude=40.1353, latitude=-1.891517),
    )
    base.update(overrides)
    return base


def _set_events_create_rate(tenant_settings, monkeypatch, rate: str | None) -> None:
    """Patch the throttle's get_tenant_settings to return a tenant with the given rate."""
    tenant_settings.env_settings.events_create_throttle_rate = rate
    monkeypatch.setattr("activity.throttles.get_tenant_settings", lambda: tenant_settings)


@pytest.fixture
def clear_throttle_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# Unit tests for the throttle class itself (no HTTP layer needed)
# ---------------------------------------------------------------------------


class TestEventCreateThrottleUnit:
    def test_get_rate_returns_rate_string(self, tenant_settings):
        tenant_settings.env_settings.events_create_throttle_rate = "100/min"
        throttle = EventCreateThrottle()
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            assert throttle.get_rate() == "100/min"

    def test_get_rate_returns_none_for_empty_string(self, tenant_settings):
        tenant_settings.env_settings.events_create_throttle_rate = ""
        throttle = EventCreateThrottle()
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            assert throttle.get_rate() is None

    def test_get_rate_returns_none_for_none(self, tenant_settings):
        tenant_settings.env_settings.events_create_throttle_rate = None
        throttle = EventCreateThrottle()
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            assert throttle.get_rate() is None

    def test_get_rate_returns_none_for_sentinel_string(self, tenant_settings):
        tenant_settings.env_settings.events_create_throttle_rate = "none"
        throttle = EventCreateThrottle()
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            assert throttle.get_rate() is None

    def test_get_rate_returns_none_for_none_uppercase(self, tenant_settings):
        tenant_settings.env_settings.events_create_throttle_rate = "NONE"
        throttle = EventCreateThrottle()
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            assert throttle.get_rate() is None

    def test_get_cache_key_returns_none_for_get(self, rf):
        request = rf.get("/")
        from rest_framework.request import Request

        drf_request = Request(request)
        throttle = EventCreateThrottle()
        throttle.rate = "10/min"
        throttle.num_requests = 10
        throttle.duration = 60
        assert throttle.get_cache_key(drf_request, view=None) is None

    def test_get_cache_key_returns_string_for_post(self, rf):
        request = rf.post("/")
        from rest_framework.request import Request

        drf_request = Request(request)
        throttle = EventCreateThrottle()
        throttle.rate = "10/min"
        throttle.num_requests = 10
        throttle.duration = 60
        key = throttle.get_cache_key(drf_request, view=None)
        assert key is not None
        assert "tenant" in key

    def test_cache_key_uses_constant_ident_not_user(self, rf, create_user):
        """All users of the same tenant share one bucket (constant ident)."""
        request1 = rf.post("/")
        request2 = rf.post("/")
        from rest_framework.request import Request

        drf_request1 = Request(request1)
        drf_request2 = Request(request2)
        throttle = EventCreateThrottle()
        throttle.rate = "10/min"
        throttle.num_requests = 10
        throttle.duration = 60
        key1 = throttle.get_cache_key(drf_request1, view=None)
        key2 = throttle.get_cache_key(drf_request2, view=None)
        assert key1 == key2

    def test_batch_size_for_single_event(self):
        # Avoid parsing real JSON through the DRF parser stack; mock request.data directly.
        request = MagicMock()
        request.data = {"title": "x"}
        throttle = EventCreateThrottle()
        assert throttle._batch_size(request) == 1

    def test_batch_size_for_list_of_events(self):
        request = MagicMock()
        request.data = [{"title": "a"}, {"title": "b"}, {"title": "c"}]
        throttle = EventCreateThrottle()
        assert throttle._batch_size(request) == 3

    def test_batch_size_for_empty_list_returns_one(self):
        request = MagicMock()
        request.data = []
        throttle = EventCreateThrottle()
        assert throttle._batch_size(request) == 1

    def test_get_rate_returns_none_when_kill_switch_disabled(self, tenant_settings):
        """EVENTS_CREATE_THROTTLE_ENABLED=False overrides any per-tenant rate."""
        tenant_settings.env_settings.events_create_throttle_rate = "600/min"
        throttle = EventCreateThrottle()
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            with patch("activity.throttles.settings") as mock_settings:
                mock_settings.EVENTS_CREATE_THROTTLE_ENABLED = False
                assert throttle.get_rate() is None

    def test_get_rate_returns_rate_when_kill_switch_enabled(self, tenant_settings):
        """EVENTS_CREATE_THROTTLE_ENABLED=True does not suppress the rate."""
        tenant_settings.env_settings.events_create_throttle_rate = "600/min"
        throttle = EventCreateThrottle()
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            with patch("activity.throttles.settings") as mock_settings:
                mock_settings.EVENTS_CREATE_THROTTLE_ENABLED = True
                assert throttle.get_rate() == "600/min"

    def test_wait_for_batch_is_at_least_as_large_as_single_entry_wait(self):
        """wait() for a batch of N returns a Retry-After >= the single-entry wait.

        DRF's default wait() returns the time for the oldest single entry to
        expire.  When a batch of N is rejected, the client needs N slots to free
        up, so the advised wait must cover the N-th oldest entry's expiry — which
        is always >= the oldest single-entry expiry.
        """
        throttle = EventCreateThrottle()
        throttle.rate = "3/min"
        throttle.num_requests = 3
        throttle.duration = 60
        throttle.now = 1_000_000.0

        # Fill the bucket: 3 entries at t=now, t=now-10, t=now-20 (newest-first).
        throttle.history = [throttle.now, throttle.now - 10, throttle.now - 20]

        # Single-entry wait: time until the oldest entry (now-20) expires.
        throttle._batch = 1
        wait_single = throttle.wait()

        # Batch-of-3 wait: must wait for the 3rd oldest entry (now-20 in this case,
        # same as single — all 3 are filled) to expire.
        throttle._batch = 3
        wait_batch = throttle.wait()

        assert wait_single is not None
        assert wait_batch is not None
        assert wait_batch >= wait_single

    def test_wait_for_batch_larger_than_single_returns_longer_wait(self):
        """A larger batch requires waiting longer when older entries span a wider spread."""
        throttle = EventCreateThrottle()
        throttle.rate = "3/min"
        throttle.num_requests = 3
        throttle.duration = 60
        throttle.now = 1_000_000.0

        # 3 entries spread out: newest at now, middle at now-10, oldest at now-50.
        throttle.history = [throttle.now, throttle.now - 10, throttle.now - 50]

        # Single-entry wait: time until history[-1] (now-50) expires = 60 - 50 = 10 s.
        throttle._batch = 1
        wait_single = throttle.wait()

        # Batch-of-2 wait: wait until history[-2] (now-10) expires = 60 - 10 = 50 s.
        throttle._batch = 2
        wait_batch_2 = throttle.wait()

        # Batch-of-3 wait: wait until history[-3] (now) expires = 60 - 0 = 60 s.
        throttle._batch = 3
        wait_batch_3 = throttle.wait()

        assert wait_single is not None
        assert wait_batch_2 is not None
        assert wait_batch_3 is not None
        assert wait_batch_2 > wait_single
        assert wait_batch_3 >= wait_batch_2
        # Verify concrete values.
        assert abs(wait_single - 10.0) < 0.001
        assert abs(wait_batch_2 - 50.0) < 0.001
        assert abs(wait_batch_3 - 60.0) < 0.001

    def test_wait_returns_none_when_batch_exceeds_bucket(self):
        """A batch larger than num_requests can never fit, so wait() returns None.

        DRF emits no Retry-After header when wait() is None, which avoids
        misleading the client into retrying an unsatisfiable request.
        """
        throttle = EventCreateThrottle()
        throttle.rate = "3/min"
        throttle.num_requests = 3
        throttle.duration = 60
        throttle.now = 1_000_000.0
        throttle.history = []

        # Batch of 4 against a bucket of 3 can never succeed.
        throttle._batch = 4
        assert throttle.wait() is None

    def test_wait_returns_value_when_batch_equals_bucket(self):
        """A batch exactly equal to num_requests can fit once the window clears."""
        throttle = EventCreateThrottle()
        throttle.rate = "3/min"
        throttle.num_requests = 3
        throttle.duration = 60
        throttle.now = 1_000_000.0
        throttle.history = [throttle.now, throttle.now - 10, throttle.now - 20]

        throttle._batch = 3
        wait = throttle.wait()
        assert wait is not None

    def test_wait_falls_back_to_drf_default_when_history_is_empty(self):
        """Defensive fallback: an empty history with a satisfiable batch matches
        DRF's default wait() formula, duration / (num_requests + 1).

        This branch is unreachable in practice — a rejection with an empty
        history implies batch > num_requests, which returns None earlier in
        wait() — but it is covered here to guard the explicit fallback value.
        """
        throttle = EventCreateThrottle()
        throttle.rate = "3/min"
        throttle.num_requests = 3
        throttle.duration = 60
        throttle.now = 1_000_000.0
        throttle.history = []

        throttle._batch = 1
        wait = throttle.wait()
        assert wait is not None
        assert abs(wait - (60 / 4.0)) < 0.001


# ---------------------------------------------------------------------------
# Integration tests (HTTP layer)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "clear_throttle_cache")
class TestEventCreateThrottleIntegration:
    @pytest.fixture(autouse=True)
    def _setup_data(self, das_tenant):
        set_current_tenant(das_tenant)
        call_command("loaddata_with_tenant", "initial_eventdata")
        call_command("loaddata_with_tenant", "event_data_model")
        call_command("loaddata_with_tenant", "test_events_schema")

    def test_single_post_returns_201_within_limit(self, superuser_client, tenant_settings, monkeypatch):
        _set_events_create_rate(tenant_settings, monkeypatch, "10/min")
        url = reverse("events")
        response = superuser_client.post(url, _event_payload(), format="json")
        assert response.status_code == status.HTTP_201_CREATED

    def test_post_returns_429_after_limit_exceeded(self, superuser_client, tenant_settings, monkeypatch):
        _set_events_create_rate(tenant_settings, monkeypatch, "1/min")
        url = reverse("events")
        r1 = superuser_client.post(url, _event_payload(), format="json")
        r2 = superuser_client.post(url, _event_payload(), format="json")
        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_429_response_includes_retry_after_header(self, superuser_client, tenant_settings, monkeypatch):
        _set_events_create_rate(tenant_settings, monkeypatch, "1/min")
        url = reverse("events")
        superuser_client.post(url, _event_payload(), format="json")
        r2 = superuser_client.post(url, _event_payload(), format="json")
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in r2

    def test_throttled_rejection_emits_metric_with_batch_size_tag(self, superuser_client, tenant_settings, monkeypatch):
        """A rate-throttle rejection emits ``events_create.throttled`` with a
        tenant tag and the batch size that was rejected."""
        _set_events_create_rate(tenant_settings, monkeypatch, "1/min")
        url = reverse("events")
        with patch("activity.throttles.stats.increment") as mock_increment:
            superuser_client.post(url, _event_payload(), format="json")
            r2 = superuser_client.post(url, _event_payload(), format="json")
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        mock_increment.assert_any_call(
            "events_create.throttled",
            tags={"tenant": str(tenant_settings.id), "batch_size": "1"},
        )

    def test_get_list_is_never_throttled(self, superuser_client, tenant_settings, monkeypatch):
        """GET requests must be exempt from the events-create throttle."""
        # Use a tiny rate; if GET were evaluated it would immediately 429.
        _set_events_create_rate(tenant_settings, monkeypatch, "1/min")
        # First POST exhausts the budget.
        url = reverse("events")
        superuser_client.post(url, _event_payload(), format="json")
        # Subsequent GETs must still return 200.
        r1 = superuser_client.get(url)
        r2 = superuser_client.get(url)
        r3 = superuser_client.get(url)
        assert r1.status_code == status.HTTP_200_OK
        assert r2.status_code == status.HTTP_200_OK
        assert r3.status_code == status.HTTP_200_OK

    def test_batch_post_consumes_n_units(self, superuser_client, tenant_settings, monkeypatch):
        """A batch of N events must consume N units, not 1."""
        # Limit = 3.  Batch of 2 consumes 2, leaving 1.
        # Single POST uses the last unit.  Third POST is rejected.
        _set_events_create_rate(tenant_settings, monkeypatch, "3/min")
        url = reverse("events")
        batch_of_two = [_event_payload(), _event_payload()]
        r1 = superuser_client.post(url, batch_of_two, format="json")
        assert r1.status_code == status.HTTP_201_CREATED

        r2 = superuser_client.post(url, _event_payload(), format="json")
        assert r2.status_code == status.HTTP_201_CREATED

        r3 = superuser_client.post(url, _event_payload(), format="json")
        assert r3.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_batch_larger_than_limit_is_rejected(self, superuser_client, tenant_settings, monkeypatch):
        """A single batch that exceeds the entire remaining budget is rejected."""
        _set_events_create_rate(tenant_settings, monkeypatch, "1/min")
        url = reverse("events")
        batch_of_two = [_event_payload(), _event_payload()]
        response = superuser_client.post(url, batch_of_two, format="json")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_batch_larger_than_bucket_omits_retry_after(self, superuser_client, tenant_settings, monkeypatch):
        """A batch larger than the whole bucket can never succeed, so the 429
        response must omit the Retry-After header (no point in retrying)."""
        _set_events_create_rate(tenant_settings, monkeypatch, "1/min")
        url = reverse("events")
        batch_of_two = [_event_payload(), _event_payload()]
        response = superuser_client.post(url, batch_of_two, format="json")
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" not in response

    def test_disabled_when_rate_is_none(self, superuser_client, tenant_settings, monkeypatch):
        """Setting rate to None disables throttling."""
        _set_events_create_rate(tenant_settings, monkeypatch, None)
        url = reverse("events")
        for _ in range(5):
            r = superuser_client.post(url, _event_payload(), format="json")
            assert r.status_code == status.HTTP_201_CREATED

    def test_disabled_when_rate_is_empty_string(self, superuser_client, tenant_settings, monkeypatch):
        """An empty rate string disables throttling (env-level opt-out)."""
        _set_events_create_rate(tenant_settings, monkeypatch, "")
        url = reverse("events")
        for _ in range(5):
            r = superuser_client.post(url, _event_payload(), format="json")
            assert r.status_code == status.HTTP_201_CREATED

    def test_disabled_when_rate_is_sentinel_none_string(self, superuser_client, tenant_settings, monkeypatch):
        """The string 'none' disables throttling."""
        _set_events_create_rate(tenant_settings, monkeypatch, "none")
        url = reverse("events")
        for _ in range(5):
            r = superuser_client.post(url, _event_payload(), format="json")
            assert r.status_code == status.HTTP_201_CREATED

    def test_rate_configurable_per_tenant(self, superuser_client, tenant_settings, monkeypatch):
        """Changing the tenant rate from the default is respected."""
        _set_events_create_rate(tenant_settings, monkeypatch, "2/min")
        url = reverse("events")
        r1 = superuser_client.post(url, _event_payload(), format="json")
        r2 = superuser_client.post(url, _event_payload(), format="json")
        r3 = superuser_client.post(url, _event_payload(), format="json")
        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_201_CREATED
        assert r3.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_kill_switch_disabled_allows_requests_past_tenant_limit(
        self, superuser_client, tenant_settings, monkeypatch, settings
    ):
        """EVENTS_CREATE_THROTTLE_ENABLED=False bypasses throttling even when a
        tenant rate is configured — including rates that would normally come from TMS."""
        _set_events_create_rate(tenant_settings, monkeypatch, "1/min")
        settings.EVENTS_CREATE_THROTTLE_ENABLED = False
        url = reverse("events")
        # Without the kill-switch, the second POST would 429.
        r1 = superuser_client.post(url, _event_payload(), format="json")
        r2 = superuser_client.post(url, _event_payload(), format="json")
        r3 = superuser_client.post(url, _event_payload(), format="json")
        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_201_CREATED
        assert r3.status_code == status.HTTP_201_CREATED

    def test_kill_switch_enabled_default_still_throttles(
        self, superuser_client, tenant_settings, monkeypatch, settings
    ):
        """Explicitly setting EVENTS_CREATE_THROTTLE_ENABLED=True preserves throttling."""
        _set_events_create_rate(tenant_settings, monkeypatch, "1/min")
        settings.EVENTS_CREATE_THROTTLE_ENABLED = True
        url = reverse("events")
        r1 = superuser_client.post(url, _event_payload(), format="json")
        r2 = superuser_client.post(url, _event_payload(), format="json")
        assert r1.status_code == status.HTTP_201_CREATED
        assert r2.status_code == status.HTTP_429_TOO_MANY_REQUESTS


# ---------------------------------------------------------------------------
# Tenant isolation test
# ---------------------------------------------------------------------------


class TestEventCreateThrottleTenantIsolation:
    """Two tenants must have independent rate-limit buckets.

    The throttle emits the same cache-key string (``throttle_events_create_tenant``)
    for every request.  Isolation comes from the ``default`` cache alias
    ``KEY_FUNCTION = utils.tenant.cache.make_cache_key``, which prepends the
    thread-local tenant id so each tenant's key is unique at the storage level.

    We verify this by calling ``make_cache_key`` directly with two different
    tenant IDs and asserting the resulting keys differ.
    """

    def test_make_cache_key_differs_across_tenant_ids(self):
        """make_cache_key produces distinct keys for different tenant IDs."""
        import datetime
        import uuid

        from utils.tenant.cache import make_cache_key
        from utils.tenant.dataclass import EnvironmentSettings, FeatureFlags, Tenant

        def _make_mock_tenant(tenant_id: uuid.UUID) -> Tenant:
            return Tenant(
                id=tenant_id,
                name="Test",
                slug_name="test",
                cluster_name=None,
                cluster_namespace=None,
                permissions_custom_sequence_start=None,
                permissions_custom_sequence_end=None,
                domain=f"test-{tenant_id.hex[:8]}.example.com",
                url=f"https://test-{tenant_id.hex[:8]}.example.com",
                created_at=datetime.datetime.now(tz=datetime.timezone.utc),
                updated_at=datetime.datetime.now(tz=datetime.timezone.utc),
                feature_flags=FeatureFlags(),
                env_settings=EnvironmentSettings(),
                services=None,
            )

        id_a = uuid.uuid4()
        id_b = uuid.uuid4()
        tenant_a = _make_mock_tenant(id_a)
        tenant_b = _make_mock_tenant(id_b)

        base_key = "throttle_events_create_tenant"

        with patch("utils.tenant.cache.get_tenant_settings", return_value=tenant_a):
            key_a = make_cache_key(base_key, "", 1)

        with patch("utils.tenant.cache.get_tenant_settings", return_value=tenant_b):
            key_b = make_cache_key(base_key, "", 1)

        assert key_a != key_b
        assert str(id_a) in key_a
        assert str(id_b) in key_b


# ---------------------------------------------------------------------------
# Unit tests for the concurrency guard helper functions
# ---------------------------------------------------------------------------


class TestConcurrencyRedisKey:
    def test_key_contains_tenant_id(self):
        tid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        key = _concurrency_redis_key(tid)
        assert str(tid) in key

    def test_key_for_different_tenant_ids_are_distinct(self):
        key_a = _concurrency_redis_key(uuid.uuid4())
        key_b = _concurrency_redis_key(uuid.uuid4())
        assert key_a != key_b


class TestGetConcurrencyLimit:
    def test_returns_none_when_kill_switch_disabled(self, tenant_settings):
        with patch("activity.throttles.settings") as mock_settings:
            mock_settings.EVENTS_CREATE_THROTTLE_ENABLED = False
            assert _get_concurrency_limit() is None

    def test_returns_none_when_limit_is_zero(self, tenant_settings):
        tenant_settings.env_settings.events_create_max_concurrency = 0
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            with patch("activity.throttles.settings") as mock_settings:
                mock_settings.EVENTS_CREATE_THROTTLE_ENABLED = True
                mock_settings.EVENTS_CREATE_MAX_CONCURRENCY = 0
                assert _get_concurrency_limit() is None

    def test_returns_none_when_limit_is_negative(self, tenant_settings):
        tenant_settings.env_settings.events_create_max_concurrency = -1
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            with patch("activity.throttles.settings") as mock_settings:
                mock_settings.EVENTS_CREATE_THROTTLE_ENABLED = True
                mock_settings.EVENTS_CREATE_MAX_CONCURRENCY = -1
                assert _get_concurrency_limit() is None

    def test_returns_tenant_limit_from_env_settings(self, tenant_settings):
        tenant_settings.env_settings.events_create_max_concurrency = 7
        with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
            with patch("activity.throttles.settings") as mock_settings:
                mock_settings.EVENTS_CREATE_THROTTLE_ENABLED = True
                mock_settings.EVENTS_CREATE_MAX_CONCURRENCY = 10
                assert _get_concurrency_limit() == 7


# ---------------------------------------------------------------------------
# Unit tests for the context manager (_event_create_concurrency_slot)
# ---------------------------------------------------------------------------


def _make_post_request():
    """Return a minimal MagicMock that looks like a DRF POST request."""
    req = MagicMock()
    req.method = "POST"
    return req


def _make_get_request():
    req = MagicMock()
    req.method = "GET"
    return req


@pytest.fixture
def fake_redis_conn():
    """An in-memory fakeredis server connection for testing sorted-set logic."""
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server)


@pytest.fixture
def patch_concurrency_redis(fake_redis_conn):
    """Patch get_redis_connection to return the fake redis conn."""
    with patch("activity.throttles.get_redis_connection", return_value=fake_redis_conn):
        yield fake_redis_conn


class TestEventCreateConcurrencySlot:
    def _get_settings_patch(self, enabled=True, limit=10):
        mock_settings = MagicMock()
        mock_settings.EVENTS_CREATE_THROTTLE_ENABLED = enabled
        mock_settings.EVENTS_CREATE_MAX_CONCURRENCY = limit
        return mock_settings

    def test_get_request_passes_through_without_redis(self):
        """GET requests bypass concurrency guard — no Redis interaction."""
        request = _make_get_request()
        with _event_create_concurrency_slot(request) as rejection:
            assert rejection is None

    def test_allows_request_within_limit(self, tenant_settings, patch_concurrency_redis):
        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)
        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request) as rejection:
                    assert rejection is None

    def test_slot_is_in_sorted_set_during_execution(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        """While inside the context manager the entry is present in the sorted set."""
        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)
        key = _concurrency_redis_key(tenant_settings.id)
        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request):
                    assert fake_redis_conn.zcard(key) == 1

    def test_slot_is_released_after_success(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        """After a successful request the sorted set is empty."""
        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)
        key = _concurrency_redis_key(tenant_settings.id)
        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request):
                    pass
        assert fake_redis_conn.zcard(key) == 0

    def test_slot_is_released_on_exception(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        """Slot is released even when the body raises an exception."""
        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)
        key = _concurrency_redis_key(tenant_settings.id)
        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                try:
                    with _event_create_concurrency_slot(request):
                        raise ValueError("simulated view failure")
                except ValueError:
                    pass
        assert fake_redis_conn.zcard(key) == 0

    def test_exception_raised_after_rejection_propagates_and_is_not_mislogged(
        self, tenant_settings, patch_concurrency_redis, fake_redis_conn, caplog
    ):
        """Regression test for the generator landmine: when the caller's
        with-body raises after receiving a 429 rejection, the exception must
        propagate unchanged — not be mis-caught by the Redis-error handling
        and mislogged as "failing open"."""
        import logging

        request = _make_post_request()
        limit = 1
        tenant_settings.env_settings.events_create_max_concurrency = limit
        mock_settings = self._get_settings_patch(enabled=True, limit=limit)
        key = _concurrency_redis_key(tenant_settings.id)
        fake_redis_conn.zadd(key, {"existing-req": time.time()})

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with caplog.at_level(logging.WARNING, logger="activity.throttles"):
                    with pytest.raises(ValueError, match="simulated view failure"):
                        with _event_create_concurrency_slot(request) as rejection:
                            assert rejection is not None
                            raise ValueError("simulated view failure")

        assert not any("failing open" in record.message for record in caplog.records)

    def test_rejects_at_limit_plus_one(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        """When the sorted set already has `limit` live entries, the next request is rejected."""
        request = _make_post_request()
        limit = 2
        tenant_settings.env_settings.events_create_max_concurrency = limit
        mock_settings = self._get_settings_patch(enabled=True, limit=limit)
        key = _concurrency_redis_key(tenant_settings.id)

        # Pre-seed `limit` live entries with scores in the present window.
        now_ts = time.time()
        for i in range(limit):
            fake_redis_conn.zadd(key, {f"req-{i}": now_ts})

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request) as rejection:
                    assert rejection is not None
                    assert rejection.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_rejected_request_does_not_leave_entry_in_sorted_set(
        self, tenant_settings, patch_concurrency_redis, fake_redis_conn
    ):
        """A rejected request must not consume a slot (its own entry is removed on reject)."""
        request = _make_post_request()
        limit = 1
        tenant_settings.env_settings.events_create_max_concurrency = limit
        mock_settings = self._get_settings_patch(enabled=True, limit=limit)
        key = _concurrency_redis_key(tenant_settings.id)

        now_ts = time.time()
        fake_redis_conn.zadd(key, {"existing-req": now_ts})

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request) as rejection:
                    assert rejection is not None

        # Only the pre-seeded entry remains; our rejected entry was cleaned up.
        assert fake_redis_conn.zcard(key) == 1

    def test_retry_after_header_present_on_429(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        request = _make_post_request()
        limit = 1
        tenant_settings.env_settings.events_create_max_concurrency = limit
        mock_settings = self._get_settings_patch(enabled=True, limit=limit)
        key = _concurrency_redis_key(tenant_settings.id)
        fake_redis_conn.zadd(key, {"existing-req": time.time()})

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request) as rejection:
                    assert rejection is not None
                    assert "Retry-After" in rejection

    def test_stale_entries_are_evicted_and_not_counted(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        """An entry older than the TTL is evicted during the next enter and does not count.

        The stale entry fills the entire budget (limit=1).  Without eviction a new
        request would be rejected.  With eviction the stale entry disappears and the
        new request is allowed.
        """
        request = _make_post_request()
        limit = 1
        tenant_settings.env_settings.events_create_max_concurrency = limit
        mock_settings = self._get_settings_patch(enabled=True, limit=limit)
        key = _concurrency_redis_key(tenant_settings.id)

        # Pre-seed a stale entry (score well beyond the TTL window).
        stale_score = time.time() - _CONCURRENCY_SLOT_TTL_SECONDS - 10
        fake_redis_conn.zadd(key, {"stale-req": stale_score})

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request) as rejection:
                    # Should be allowed — stale entry evicted, only our new entry present.
                    assert rejection is None

    def test_fails_open_when_redis_unavailable(self, tenant_settings):
        """If Redis raises an exception the guard allows the request (fail-open)."""
        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)

        def _raise(*args, **kwargs):
            raise redis.exceptions.ConnectionError("Redis is down")

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with patch("activity.throttles.get_redis_connection", side_effect=_raise):
                    with _event_create_concurrency_slot(request) as rejection:
                        assert rejection is None

    def test_fails_open_logs_warning_on_redis_error(self, tenant_settings, caplog):
        """A Redis failure is logged at WARNING level."""
        import logging

        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with patch(
                    "activity.throttles.get_redis_connection",
                    side_effect=redis.exceptions.ConnectionError("Redis is down"),
                ):
                    with caplog.at_level(logging.WARNING, logger="activity.throttles"):
                        with _event_create_concurrency_slot(request):
                            pass
        assert any("failing open" in record.message for record in caplog.records)

    def test_rejection_emits_concurrency_rejected_metric(
        self, tenant_settings, patch_concurrency_redis, fake_redis_conn
    ):
        """A concurrency-cap rejection emits ``events_create.concurrency_rejected``
        tagged with the tenant, batch size, and configured limit."""
        request = _make_post_request()
        limit = 1
        tenant_settings.env_settings.events_create_max_concurrency = limit
        mock_settings = self._get_settings_patch(enabled=True, limit=limit)
        key = _concurrency_redis_key(tenant_settings.id)
        fake_redis_conn.zadd(key, {"existing-req": time.time()})

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with patch("activity.throttles.stats.increment") as mock_increment:
                    with _event_create_concurrency_slot(request) as rejection:
                        assert rejection is not None

        mock_increment.assert_any_call(
            "events_create.concurrency_rejected",
            tags={"tenant": str(tenant_settings.id), "batch_size": "1", "limit": str(limit)},
        )

    def test_fail_open_on_redis_error_emits_metric_with_reason(self, tenant_settings):
        """A genuine Redis failure emits ``events_create.fail_open`` tagged
        with reason ``"redis_error"``."""
        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with patch(
                    "activity.throttles.get_redis_connection",
                    side_effect=redis.exceptions.ConnectionError("Redis is down"),
                ):
                    with patch("activity.throttles.stats.increment") as mock_increment:
                        with _event_create_concurrency_slot(request) as rejection:
                            assert rejection is None

        mock_increment.assert_any_call(
            "events_create.fail_open",
            tags={"tenant": str(tenant_settings.id), "reason": "redis_error"},
        )

    def test_non_redis_backend_warning_logged_once_and_both_requests_fail_open(
        self, tenant_settings, monkeypatch, caplog
    ):
        """When the default cache is not a django-redis backend,
        ``get_redis_connection`` raises ``NotImplementedError`` on every call.
        The resulting WARNING must be logged only once per process, while both
        requests still fail open."""
        import logging

        # Reset the log-once flag so test order doesn't matter.
        monkeypatch.setattr("activity.throttles._non_redis_backend_warning_logged", False)

        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with patch(
                    "activity.throttles.get_redis_connection",
                    side_effect=NotImplementedError("This backend does not support this feature"),
                ):
                    with caplog.at_level(logging.WARNING, logger="activity.throttles"):
                        with _event_create_concurrency_slot(request) as rejection1:
                            assert rejection1 is None
                        with _event_create_concurrency_slot(request) as rejection2:
                            assert rejection2 is None

        warning_records = [r for r in caplog.records if "does not support raw Redis connections" in r.message]
        assert len(warning_records) == 1

    def test_leaked_zadd_entry_is_cleaned_up_when_pipeline_execute_fails(self, tenant_settings, fake_redis_conn):
        """A pipeline failure that occurs after the ZADD has already landed
        server-side must not leak the slot until the stale-eviction TTL — the
        guard should best-effort ``zrem`` its own entry before failing open."""
        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=True, limit=5)
        key = _concurrency_redis_key(tenant_settings.id)
        fixed_request_id = uuid.uuid4()

        real_pipeline = fake_redis_conn.pipeline

        def _pipeline(*args, **kwargs):
            pipe = real_pipeline(*args, **kwargs)
            original_execute = pipe.execute

            def _execute(*a, **kw):
                # The ZADD (and subsequent queued commands) land on the fake
                # server before the pipeline call itself fails, simulating a
                # mid/post-pipeline error after ZADD has already applied.
                original_execute(*a, **kw)
                raise redis.exceptions.ConnectionError("simulated failure after ZADD landed")

            pipe.execute = _execute
            return pipe

        with patch.object(fake_redis_conn, "pipeline", side_effect=_pipeline):
            with patch.object(fake_redis_conn, "zrem", wraps=fake_redis_conn.zrem) as mock_zrem:
                with patch("activity.throttles.settings", mock_settings):
                    with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                        with patch("activity.throttles.get_redis_connection", return_value=fake_redis_conn):
                            with patch("activity.throttles.uuid.uuid4", return_value=fixed_request_id):
                                with _event_create_concurrency_slot(request) as rejection:
                                    assert rejection is None  # fails open

        mock_zrem.assert_any_call(key, str(fixed_request_id))
        assert fake_redis_conn.zcard(key) == 0

    def test_disabled_when_kill_switch_off(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        """EVENTS_CREATE_THROTTLE_ENABLED=False disables the concurrency guard entirely."""
        request = _make_post_request()
        mock_settings = self._get_settings_patch(enabled=False, limit=1)
        key = _concurrency_redis_key(tenant_settings.id)

        # Pre-seed to simulate limit reached.
        fake_redis_conn.zadd(key, {"existing-req": time.time()})

        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request) as rejection:
                    assert rejection is None

    def test_disabled_when_limit_is_zero(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        """EVENTS_CREATE_MAX_CONCURRENCY=0 disables the concurrency guard."""
        request = _make_post_request()
        tenant_settings.env_settings.events_create_max_concurrency = 0
        mock_settings = self._get_settings_patch(enabled=True, limit=0)
        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request) as rejection:
                    assert rejection is None

    def test_two_tenants_have_independent_sorted_sets(self, tenant_settings, patch_concurrency_redis, fake_redis_conn):
        """Each tenant has its own Redis key — one tenant's inflight does not affect the other."""
        import datetime

        from utils.tenant.dataclass import EnvironmentSettings, FeatureFlags, Tenant

        tenant_id_b = uuid.uuid4()
        tenant_b = Tenant(
            id=tenant_id_b,
            name="Tenant B",
            slug_name="tenant-b",
            cluster_name=None,
            cluster_namespace=None,
            permissions_custom_sequence_start=None,
            permissions_custom_sequence_end=None,
            domain=f"tenant-b-{tenant_id_b.hex[:8]}.example.com",
            url=f"https://tenant-b-{tenant_id_b.hex[:8]}.example.com",
            created_at=datetime.datetime.now(tz=datetime.timezone.utc),
            updated_at=datetime.datetime.now(tz=datetime.timezone.utc),
            feature_flags=FeatureFlags(),
            env_settings=EnvironmentSettings(events_create_max_concurrency=1),
            services=None,
        )

        # Saturate tenant A (limit=1) by pre-seeding its sorted set.
        key_a = _concurrency_redis_key(tenant_settings.id)
        fake_redis_conn.zadd(key_a, {"tenant-a-req": time.time()})

        limit = 1
        tenant_settings.env_settings.events_create_max_concurrency = limit
        mock_settings = self._get_settings_patch(enabled=True, limit=limit)
        request = _make_post_request()

        # Tenant A: should be rejected (saturated).
        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_settings):
                with _event_create_concurrency_slot(request) as rejection_a:
                    assert rejection_a is not None

        # Tenant B: should be allowed (independent sorted set is empty).
        with patch("activity.throttles.settings", mock_settings):
            with patch("activity.throttles.get_tenant_settings", return_value=tenant_b):
                with _event_create_concurrency_slot(request) as rejection_b:
                    assert rejection_b is None


# ---------------------------------------------------------------------------
# Integration tests for the concurrency guard at the HTTP layer
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "clear_throttle_cache")
class TestEventCreateConcurrencyIntegration:
    @pytest.fixture(autouse=True)
    def _setup_data(self, das_tenant):
        set_current_tenant(das_tenant)
        call_command("loaddata_with_tenant", "initial_eventdata")
        call_command("loaddata_with_tenant", "event_data_model")
        call_command("loaddata_with_tenant", "test_events_schema")

    @pytest.fixture
    def fake_redis(self):
        """Fake redis server used for all integration-level concurrency tests."""
        server = fakeredis.FakeServer()
        conn = fakeredis.FakeRedis(server=server)
        with patch("activity.throttles.get_redis_connection", return_value=conn):
            yield conn

    def test_single_post_allowed_within_concurrency_limit(
        self, superuser_client, tenant_settings, monkeypatch, settings, fake_redis
    ):
        _set_events_create_rate(tenant_settings, monkeypatch, None)  # disable rate throttle
        settings.EVENTS_CREATE_MAX_CONCURRENCY = 5
        url = reverse("events")
        r = superuser_client.post(url, _event_payload(), format="json")
        assert r.status_code == status.HTTP_201_CREATED

    def test_get_list_unaffected_by_concurrency_guard(
        self, superuser_client, tenant_settings, monkeypatch, settings, fake_redis
    ):
        """GET requests are never blocked by the concurrency cap."""
        _set_events_create_rate(tenant_settings, monkeypatch, None)
        settings.EVENTS_CREATE_MAX_CONCURRENCY = 1
        # Saturate the sorted set.
        key = _concurrency_redis_key(tenant_settings.id)
        fake_redis.zadd(key, {"pre-existing-req": time.time()})

        url = reverse("events")
        r = superuser_client.get(url)
        assert r.status_code == status.HTTP_200_OK

    def test_concurrency_cap_disabled_by_kill_switch(
        self, superuser_client, tenant_settings, monkeypatch, settings, fake_redis
    ):
        """EVENTS_CREATE_THROTTLE_ENABLED=False disables the concurrency guard."""
        _set_events_create_rate(tenant_settings, monkeypatch, None)
        settings.EVENTS_CREATE_THROTTLE_ENABLED = False
        settings.EVENTS_CREATE_MAX_CONCURRENCY = 1
        # Would be rejected if guard active (limit=1, set saturated).
        key = _concurrency_redis_key(tenant_settings.id)
        fake_redis.zadd(key, {"pre-existing-req": time.time()})

        url = reverse("events")
        r = superuser_client.post(url, _event_payload(), format="json")
        assert r.status_code == status.HTTP_201_CREATED

    def test_concurrency_cap_disabled_when_limit_is_zero(
        self, superuser_client, tenant_settings, monkeypatch, settings, fake_redis
    ):
        """EVENTS_CREATE_MAX_CONCURRENCY=0 disables the concurrency guard."""
        _set_events_create_rate(tenant_settings, monkeypatch, None)
        settings.EVENTS_CREATE_MAX_CONCURRENCY = 0
        tenant_settings.env_settings.events_create_max_concurrency = 0
        monkeypatch.setattr("activity.throttles.get_tenant_settings", lambda: tenant_settings)

        url = reverse("events")
        r = superuser_client.post(url, _event_payload(), format="json")
        assert r.status_code == status.HTTP_201_CREATED

    def test_post_returns_429_when_concurrency_cap_exceeded(
        self, superuser_client, tenant_settings, monkeypatch, settings, fake_redis
    ):
        """POSTing when the concurrency cap is already saturated returns 429 with Retry-After.

        This test exercises the HTTP-layer path through EventCreateConcurrencyMixin.post
        → ListCreateAPIView.post → EventsView.create.  It fails without Fix 1 (renaming
        EventsView.post to EventsView.create) because the mixin's post() wrapper is
        bypassed when the view defines its own post().
        """
        # Disable rate throttle so only the concurrency guard is under test.
        _set_events_create_rate(tenant_settings, monkeypatch, None)

        # Set concurrency limit to 1 via both the Django setting and the tenant setting.
        settings.EVENTS_CREATE_MAX_CONCURRENCY = 1
        tenant_settings.env_settings.events_create_max_concurrency = 1
        monkeypatch.setattr("activity.throttles.get_tenant_settings", lambda: tenant_settings)

        # Pre-seed the tenant's sorted set with one live entry to saturate the cap.
        key = _concurrency_redis_key(tenant_settings.id)
        fake_redis.zadd(key, {"pre-existing-req": time.time()})

        url = reverse("events")
        r = superuser_client.post(url, _event_payload(), format="json")

        assert r.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in r

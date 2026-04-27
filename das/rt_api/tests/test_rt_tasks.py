import datetime
import json
import random
from unittest import mock
from unittest.mock import MagicMock

import pytest
from django_multitenant.utils import set_current_tenant
from pytz import UTC

from django.core.management import call_command
from django.test import TestCase

from core.tests import BaseAPITest, User, fake_get_pool
from observations.serializers import ObservationSerializer
from observations.views import SubjectStatusView
from rt_api.client import LIVE_SOCKETIO_QUEUE_HEARTBEAT_PREFIX
from rt_api.rest_api_interface.dummy_request import (
    DummyRequest,
    wrap_dummy_request_with_drf_request,
)
from rt_api.tasks import (
    SOCKETIO_BINDING_KEY,
    get_subjectstatus_view,
    get_username_sids_map,
    sweep_orphan_socketio_queues,
)
from utils.tenant.managers import UnsetDASTenantContextManager


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class RTUtils(BaseAPITest):
    def test_dummy_request_authorization(self):
        user = self.app_user
        tok = self.create_access_token(user)
        dummy_request = DummyRequest(headers={"HTTP_AUTHORIZATION": f"Bearer {tok}"})
        drf_request = wrap_dummy_request_with_drf_request(dummy_request)
        # Accessing .user triggers DRF's authentication workflow
        auth_user = drf_request.user if drf_request.user.is_authenticated else None
        self.assertEqual(auth_user, user)


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class RTTasksTestCase(TestCase):
    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_contain_last_voice(self):
        call_command("loaddata_with_tenant", "test/sourceprovider.yaml"),
        call_command("loaddata_with_tenant", "test/rt_api_source.json"),
        call_command("loaddata_with_tenant", "test/rt_api_subject.json"),
        call_command("loaddata_with_tenant", "test/rt_api_subject_source.json"),
        call_command("loaddata_with_tenant", "test/rt_api_observation.json"),
        call_command("loaddata_with_tenant", "initial_admin.yaml")

        user = User.objects.get(username="admin")
        subject_id = "a51d6901-4ece-484f-b0a6-baf1e44d2108"
        source_id = "43d22e4d-debf-402d-b49b-efdc67dddb93"

        # Generate some random data for the observation.
        observation_time = UTC.localize(datetime.datetime.now())
        fixed_latitude = float(random.randint(3000, 3000)) / 100
        fixed_longitude = float(random.randint(2800, 4000)) / 100

        fixed_location = dict(longitude=fixed_longitude, latitude=fixed_latitude)

        observation = {
            "location": fixed_location,
            "recorded_at": observation_time,
            "source": source_id,
            "additional": {
                "last_voice_call_start_at": "2018-06-22T04:57:57.058000+00:00",
                "received_time": "2018-05-09T04:55:16.000000Z",
                "state": "offline",
            },
        }

        serializer = ObservationSerializer(data=observation)

        self.assertTrue(serializer.is_valid(), msg="Observation is not valid.")

        if serializer.is_valid():
            serializer.save()

        result = get_subjectstatus_view(SubjectStatusView.as_view(), user, subject_id)

        self.assertIn("last_voice_call_start_at", result["properties"])


@pytest.mark.django_db
class TestUsernameSidMap:
    def test_get_username_sid_map(self, monkeypatch, five_tenants):
        tenant = five_tenants[0]
        connections = {
            b"xxLSSE8pJyXjB-YgAAAH": bytes(
                json.dumps(
                    {
                        "username": "admin",
                        "sid": "xxLSSE8pJyXjB-YgAAAH",
                        "bbox": None,
                        "tenantId": "c0973be2-8e11-4cb8-8463-897fb96391d0",
                        "domain": "localhost",
                    }
                ),
                "utf-8",
            ),
            b"68rT86c1Xq_-u6ziAAAF": bytes(
                json.dumps(
                    {
                        "username": "admin",
                        "sid": "68rT86c1Xq_-u6ziAAAF",
                        "bbox": None,
                        "tenantId": str(tenant.id),
                        "domain": tenant.domain,
                    }
                ),
                "utf-8",
            ),
            b"AAF68r86c1Xqzi_-u6TA": bytes(
                json.dumps(
                    {
                        "username": "admin",
                        "sid": "AAF68r86c1Xqzi_-u6TA",
                        "bbox": None,
                        "tenantId": str(tenant.id),
                        "domain": tenant.domain,
                    }
                ),
                "utf-8",
            ),
        }
        monkeypatch.setattr("rt_api.tasks.client.get_all_connections_list", MagicMock(return_value=connections))

        with UnsetDASTenantContextManager():
            set_current_tenant(tenant)
            username_sid_map = get_username_sids_map()

        assert username_sid_map == {"admin": {"AAF68r86c1Xqzi_-u6TA", "68rT86c1Xq_-u6ziAAAF"}}


class TestSweepOrphanSocketioQueues:
    HEARTBEAT_PREFIX = LIVE_SOCKETIO_QUEUE_HEARTBEAT_PREFIX.encode()

    @staticmethod
    def _binding_member(queue_name: bytes) -> bytes:
        # Mirrors kombu.transport.redis.Channel._queue_bind: empty
        # routing_key + empty pattern + queue name, joined by \x06\x16.
        return b"\x06\x16\x06\x16" + queue_name

    def _heartbeat_key(self, queue_name: bytes) -> bytes:
        return self.HEARTBEAT_PREFIX + queue_name

    def _make_redis_mock(self, queue_keys, binding_members, live_queue_names):
        rc = MagicMock()
        rc.smembers.return_value = set(binding_members)

        heartbeat_keys = {self._heartbeat_key(q) for q in live_queue_names}
        all_scannable = list(queue_keys) + list(heartbeat_keys)

        # The sweep calls scan_iter once per queue prefix and once for the
        # heartbeat prefix; return only the keys whose name starts with the
        # requested prefix so each scan sees its own slice (matching what
        # real Redis MATCH would do).
        def fake_scan_iter(match, count=None):
            prefix = match.rstrip("*").encode()
            return iter([k for k in all_scannable if k.startswith(prefix)])

        rc.scan_iter.side_effect = fake_scan_iter
        return rc

    def test_deletes_orphan_queue_and_removes_its_binding(self, monkeypatch):
        live_queue = b"python-socketio.alive"
        orphan_queue = b"python-socketio.dead"
        rc = self._make_redis_mock(
            queue_keys=[live_queue, orphan_queue],
            binding_members=[
                self._binding_member(live_queue),
                self._binding_member(orphan_queue),
            ],
            live_queue_names=[live_queue],
        )
        monkeypatch.setattr("rt_api.tasks.client.redis_client", rc)

        sweep_orphan_socketio_queues.run()

        rc.delete.assert_called_once_with(orphan_queue)
        rc.srem.assert_called_once_with(SOCKETIO_BINDING_KEY, self._binding_member(orphan_queue))

    def test_preserves_live_queues(self, monkeypatch):
        live_queue = b"python-socketio.alive"
        rc = self._make_redis_mock(
            queue_keys=[live_queue],
            binding_members=[self._binding_member(live_queue)],
            live_queue_names=[live_queue],
        )
        monkeypatch.setattr("rt_api.tasks.client.redis_client", rc)

        sweep_orphan_socketio_queues.run()

        rc.delete.assert_not_called()
        rc.srem.assert_not_called()

    def test_skips_when_no_heartbeats_present(self, monkeypatch):
        # Defense in depth: never run with an empty live set, otherwise a
        # broken heartbeat infrastructure would nuke every queue including
        # live ones.
        orphan = b"python-socketio.suspect"
        rc = self._make_redis_mock(
            queue_keys=[orphan],
            binding_members=[self._binding_member(orphan)],
            live_queue_names=[],
        )
        monkeypatch.setattr("rt_api.tasks.client.redis_client", rc)

        sweep_orphan_socketio_queues.run()

        rc.delete.assert_not_called()
        rc.srem.assert_not_called()

    def test_sweeps_legacy_flask_socketio_orphans(self, monkeypatch):
        # python-socketio < 5.12.0 named consumer queues "flask-socketio.<uuid>"
        # but bound them to the same "socketio" exchange. The current code
        # only writes "python-socketio.*" queues, so any flask-socketio.*
        # entry is by definition orphaned and must be cleaned on both
        # prefixes.
        flask_orphan = b"flask-socketio.dead"
        live_python = b"python-socketio.alive"
        rc = self._make_redis_mock(
            queue_keys=[flask_orphan, live_python],
            binding_members=[
                self._binding_member(flask_orphan),
                self._binding_member(live_python),
            ],
            live_queue_names=[live_python],
        )
        monkeypatch.setattr("rt_api.tasks.client.redis_client", rc)

        sweep_orphan_socketio_queues.run()

        rc.delete.assert_called_once_with(flask_orphan)
        rc.srem.assert_called_once_with(SOCKETIO_BINDING_KEY, self._binding_member(flask_orphan))

    def test_priority_suffixed_key_matches_base_queue_binding(self, monkeypatch):
        # Kombu's Redis transport stores priority queues under suffixed keys
        # "<queue>\x06\x16<step>". The binding registry — and the heartbeat
        # — both reference the base queue name, so the sweep must strip the
        # suffix before checking liveness, or a priority-suffixed orphan
        # would leak its binding entry forever and a live priority queue
        # would be misidentified as orphan.
        base_queue = b"python-socketio.old"
        suffixed_orphan_key = base_queue + b"\x06\x163"
        rc = self._make_redis_mock(
            queue_keys=[suffixed_orphan_key],
            binding_members=[self._binding_member(base_queue)],
            live_queue_names=[b"python-socketio.alive"],
        )
        monkeypatch.setattr("rt_api.tasks.client.redis_client", rc)

        sweep_orphan_socketio_queues.run()

        rc.delete.assert_called_once_with(suffixed_orphan_key)
        rc.srem.assert_called_once_with(SOCKETIO_BINDING_KEY, self._binding_member(base_queue))

    def test_deletes_key_with_no_matching_binding(self, monkeypatch):
        # If the binding registry has already been cleaned but the key
        # leaked, the key still needs to go.
        orphan = b"python-socketio.orphan"
        rc = self._make_redis_mock(
            queue_keys=[orphan],
            binding_members=[],
            live_queue_names=[b"python-socketio.alive"],
        )
        monkeypatch.setattr("rt_api.tasks.client.redis_client", rc)

        sweep_orphan_socketio_queues.run()

        rc.delete.assert_called_once_with(orphan)
        rc.srem.assert_not_called()

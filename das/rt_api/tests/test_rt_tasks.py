import datetime
import json
import random
from unittest import mock
from unittest.mock import MagicMock

import pytest
from django_multitenant.utils import set_current_tenant
from pytz import UTC

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.test import TestCase

from core.tests import BaseAPITest, User, fake_get_pool
from observations.serializers import ObservationSerializer
from observations.views import SubjectStatusView
from rt_api.rest_api_interface.dummy_request import DummyRequest
from rt_api.tasks import get_subjectstatus_view, get_username_sids_map
from utils.tenant.managers import UnsetDASTenantContextManager


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class RTUtils(BaseAPITest):
    def test_dummy_request_authorization(self):
        user = self.app_user
        tok = self.create_access_token(user)
        request = DummyRequest(headers={"Authorization": f"Bearer {tok}"})
        auth_user = authenticate(**{"request": request})
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
                        "tenantId": tenant.id,
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
                        "tenantId": tenant.id,
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

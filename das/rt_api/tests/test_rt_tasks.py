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
from rt_api.rest_api_interface.dummy_request import (
    DummyRequest,
    wrap_dummy_request_with_drf_request,
)
from rt_api.tasks import (
    get_observations_for_subject,
    get_subjectstatus_view,
    get_username_sids_map,
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


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGetObservationsForSubject:
    def test_returns_none_when_subject_not_found(self):
        user = MagicMock()
        result = get_observations_for_subject(user, "00000000-0000-0000-0000-000000000000", "2024-01-01T00:00:00Z")
        assert result is None

    def test_returns_none_when_user_lacks_permission(self):
        from factories import SubjectFactory

        subject = SubjectFactory.create()
        user = MagicMock()
        user.has_any_perms.return_value = False

        result = get_observations_for_subject(user, str(subject.id), "2024-01-01T00:00:00Z")

        assert result is None
        user.has_any_perms.assert_called_once()

    def test_returns_none_when_created_after_is_none(self):
        from factories import SubjectFactory

        subject = SubjectFactory.create()
        user = MagicMock()
        user.has_any_perms.return_value = True

        result = get_observations_for_subject(user, str(subject.id), None)

        assert result is None

    @mock.patch("rt_api.tasks.get_minimum_allowed_age", return_value=3)
    def test_applies_delay_filter_for_delayed_user(self, mock_min_age):
        """Users with access_ends_* delay should not see recent observations."""
        from factories import SubjectFactory
        from observations.models import Observation

        subject = SubjectFactory.create()
        user = MagicMock()
        user.has_any_perms.return_value = True

        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.exists.return_value = False

        with mock.patch.object(
            type(Observation.objects),
            "get_subject_newly_created_observations",
            return_value=mock_qs,
        ):
            get_observations_for_subject(user, str(subject.id), "2024-01-01T00:00:00Z")

        # delay of 3 days = 72 hours, should filter recorded_at__lt
        mock_qs.filter.assert_called_once()
        call_kwargs = mock_qs.filter.call_args[1]
        assert "recorded_at__lt" in call_kwargs

    @mock.patch("rt_api.tasks.get_minimum_allowed_age", return_value=0)
    def test_no_delay_filter_for_realtime_user(self, mock_min_age):
        """Users with access_ends_0 should see all observations without delay filter."""
        from factories import SubjectFactory
        from observations.models import Observation

        subject = SubjectFactory.create()
        user = MagicMock()
        user.has_any_perms.return_value = True

        mock_qs = MagicMock()
        mock_qs.exists.return_value = False

        with mock.patch.object(
            type(Observation.objects),
            "get_subject_newly_created_observations",
            return_value=mock_qs,
        ):
            get_observations_for_subject(user, str(subject.id), "2024-01-01T00:00:00Z")

        mock_qs.filter.assert_not_called()

    @mock.patch("rt_api.tasks.get_minimum_allowed_age", return_value=0)
    def test_parses_string_created_after_to_datetime(self, mock_min_age):
        """created_after from Redis is a string; it must be parsed to datetime before querying."""
        from factories import SubjectFactory
        from observations.models import Observation

        subject = SubjectFactory.create()
        user = MagicMock()
        user.has_any_perms.return_value = True

        mock_qs = MagicMock()
        mock_qs.exists.return_value = False

        with mock.patch.object(
            type(Observation.objects),
            "get_subject_newly_created_observations",
            return_value=mock_qs,
        ) as mock_get_obs:
            get_observations_for_subject(user, str(subject.id), "2024-01-01T00:00:00Z")

        call_args = mock_get_obs.call_args
        created_after_arg = call_args[0][1]
        assert isinstance(created_after_arg, datetime.datetime)

    def test_db_errors_propagate_to_caller(self):
        """InterfaceError must not be swallowed so TenantTaskMixin can retry."""
        from django.db.utils import InterfaceError

        from factories import SubjectFactory
        from observations.models import Observation

        subject = SubjectFactory.create()
        user = MagicMock()
        user.has_any_perms.return_value = True

        with mock.patch.object(
            type(Observation.objects),
            "get_subject_newly_created_observations",
            side_effect=InterfaceError("connection already closed"),
        ):
            with pytest.raises(InterfaceError):
                get_observations_for_subject(user, str(subject.id), "2024-01-01T00:00:00Z")

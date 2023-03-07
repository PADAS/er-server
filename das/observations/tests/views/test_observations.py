import json
import random
from datetime import datetime, timedelta
from urllib.parse import urlencode

import dateutil.parser
import pytest
import pytz
from django_multitenant.utils import set_current_tenant

from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.urls import reverse
from rest_framework import status

from accounts.models import PermissionSet, User
from core.tests import BaseAPITest
from core.utils import DASTenantManagement
from observations.models import (
    Observation,
    Source,
    Subject,
    SubjectGroup,
    SubjectSource,
)
from observations.views import ObservationsView, ObservationView

das_tenant_management = DASTenantManagement(domain="domain.com")


@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class ObservationViewTestCase(BaseAPITest):
    user_const = dict(last_name="last", first_name="first")

    def setUp(self):
        super().setUp()
        set_current_tenant(self.das_tenant)

        user_const = dict(last_name="last", first_name="first")

        self.user = User.objects.create_user(
            "user", "das_user@vulcan.com", "user", is_superuser=True, is_staff=True, **self.user_const
        )
        self.elephant = Subject.objects.create_subject(
            id="d2ed403e-9419-41aa-8fa9-45a70e5ce2ef", name="Elephant 1", subject_subtype_id="elephant"
        )

        source_args = {
            "subject": {"name": str(self.elephant.id)},
            "provider": "test_provider",
            "manufacturer_id": "best_manufacturer",
        }
        self.collar = Source.objects.ensure_source(**source_args)

        self.fixed_latitude = float(random.randint(3000, 3000)) / 100
        self.fixed_longitude = float(random.randint(2800, 4000)) / 100

        location = Point(x=self.fixed_longitude, y=self.fixed_latitude)
        self.additional = {"Name": "Name"}
        self.observation_time = pytz.UTC.localize(datetime.now())
        self.observation_data = {
            "recorded_at": self.observation_time,
            "location": location,
            "source": self.collar,
            "additional": self.additional,
        }

        self.observation_post_data = {
            "location": {"latitude": self.fixed_latitude, "longitude": self.fixed_longitude},
            "recorded_at": "2020-11-19T04:26:02.968Z",
            "additional": {},
            "source": str(self.collar.id),
        }

        self.observation = Observation.objects.create(**self.observation_data)

        DEFAULT_DATE_RANGE = (
            datetime(2015, 11, 1, tzinfo=pytz.utc),
            dateutil.parser.parse("9999-12-31 23:59:59+0000"),
        )
        SubjectSource.objects.create(
            assigned_range=DEFAULT_DATE_RANGE, source=self.collar, subject=self.elephant, additional={}
        )

        self.ele_group = SubjectGroup.objects.create(name="ele_group")
        self.elephant.groups.add(self.ele_group)

        self.observations_readonly_user = User.objects.create_user(
            "observations_readonly_user",
            None,
            "observations_readonly_user",
            is_superuser=False,
            is_staff=False,
            **user_const,
        )

        self.observations_readwrite_user = User.objects.create_user(
            "observations_readwrite_user",
            "readwrite@test.com",
            "observations_readwrite_user",
            is_superuser=False,
            is_staff=False,
            **user_const,
        )

        self.observation_view_set = PermissionSet.objects.create(name="observation_view_set")
        self.observation_view_set.permissions.add(Permission.objects.get(codename="view_observation"))
        self.observations_readonly_user.permission_sets.add(self.observation_view_set)

        self.observation_readwrite_set = PermissionSet.objects.create(name="observation_readwrite_set")
        self.observation_readwrite_set.permissions.add(Permission.objects.get(codename="add_observation"))
        self.observation_readwrite_set.permissions.add(Permission.objects.get(codename="view_observation"))
        self.observations_readwrite_user.permission_sets.add(self.observation_readwrite_set)

        self.ele_group.permission_sets.add(self.observation_readwrite_set)

    def test_return_observations_by_subjectsource(self):
        subjectsource_id = str(self.elephant.subjectsources.all()[0].id)

        url = reverse("observations-list-view")
        url += "?{}".format(urlencode({"subjectsource_id": subjectsource_id}))

        request = self.factory.get(self.api_base + url)

        self.force_authenticate(request, self.user)

        response = ObservationsView.as_view()(request)
        assert response.status_code == 200
        assert len(response.data)

    def test_include_details_false(self):
        url = reverse("observations-list-view")
        url += "?{}".format(urlencode({"include_details": "false"}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = ObservationsView.as_view()(request)
        results = response.data.get("results", [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(results), 1)

        obs = results[0]
        self.assertNotIn("observation_addtional", obs.keys())

    def test_include_details_true(self):
        url = reverse("observations-list-view")
        url += "?{}".format(urlencode({"include_details": "true"}))

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = ObservationsView.as_view()(request)
        results = response.data.get("results", [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(results), 1)

        obs = results[0]
        self.assertIn("observation_details", obs.keys())
        self.assertEqual(obs.get("observation_details"), self.additional)

    def test_include_details_not_specified(self):
        url = reverse("observations-list-view")

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)

        response = ObservationsView.as_view()(request)
        results = response.data.get("results", [])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(results), 1)

        obs = results[0]
        self.assertNotIn("observation_details", obs.keys())

    def test_filter_observations_by_subject_id(self):
        no_location_observation = Observation.objects.create(
            source=self.collar, recorded_at=datetime.now(pytz.UTC), location=Point(0, 0), additional={}
        )

        filter_params = {"subject_id": self.elephant.id}
        response = self.make_observations_filter_request(filter_params)

        # all records are of the given subject
        assert self.elephant.observations().count() == response.data.get("count")
        # the observation with no location is not included
        assert str(no_location_observation.id) not in [item.get("id") for item in response.data.get("results")]

    def test_filter_observations_by_subject_id_include_empty_location(self):
        # Create an observation with no location
        no_location_observation = Observation.objects.create(
            source=self.collar, recorded_at=datetime.now(pytz.UTC), location=Point(0, 0), additional={}
        )

        filter_params = {"subject_id": self.elephant.id, "include_empty_location": "true"}
        response = self.make_observations_filter_request(filter_params)

        # the observation with no location is included
        self.assertTrue(str(no_location_observation.id) in [item.get("id") for item in response.data.get("results")])

    def test_filter_observations_by_source_id(self):
        source_id = str(self.collar.id)
        filter_params = {"source_id": source_id}
        response = self.make_observations_filter_request(filter_params)

        # all records are of the given source
        self.assertTrue(all(k.get("source") == source_id for k in response.data.get("results")))

    def test_filter_observations_by_source_id_include_empty_location(self):
        no_location_observation = Observation.objects.create(
            source=self.collar, recorded_at=datetime.now(pytz.UTC), location=Point(0, 0), additional={}
        )
        source_id = str(self.collar.id)
        filter_params = {"source_id": source_id}
        response = self.make_observations_filter_request(filter_params)

        assert str(no_location_observation.id) not in [item.get("id") for item in response.data.get("results")]

        filter_params = {"source_id": source_id, "include_empty_location": "true"}
        response = self.make_observations_filter_request(filter_params)

        # all records are of the given source
        self.assertTrue(all(k.get("source") == source_id for k in response.data.get("results")))
        # the observation with no location is included
        assert str(no_location_observation.id) in [item.get("id") for item in response.data.get("results")]

    def test_filter_observations_by_sourceprovider_id(self):
        sourceprovider_id = str(self.collar.provider.id)
        source_id = str(self.collar.id)

        filter_params = {"sourceprovider_id": sourceprovider_id}
        response = self.make_observations_filter_request(filter_params)
        assert response.data.get("count") == 1
        self.assertTrue(all(k.get("source") == source_id for k in response.data.get("results")))

    def test_filter_observations_by_recorded_since(self):
        filter_params = {"since": self.observation_time + timedelta(days=1)}
        response = self.make_observations_filter_request(filter_params)

        # no records 1 days from last observations creation date
        self.assertEqual(response.data.get("count"), 0)

    def test_filter_observations_by_bbox(self):
        # Test with bbox that doesn't contain the existing observation
        filter_params = {"bbox": "0,0,1,1"}
        response = self.make_observations_filter_request(filter_params)

        self.assertEqual(response.data.get("count"), 0)

        # Create an observation within the bbox to test that bbox filtering works
        bbox_observation_data = {
            "recorded_at": datetime.now(pytz.UTC),
            "location": Point(x=0.5, y=0.5),  # Within bbox "0,0,1,1"
            "source": self.collar,
            "additional": self.additional,
        }
        Observation.objects.create(**bbox_observation_data)

        # Test that the new observation is found by the bbox filter
        response = self.make_observations_filter_request(filter_params)
        self.assertEqual(response.data.get("count"), 1)

        # Test with a different bbox that doesn't contain the new observation
        filter_params = {"bbox": "2,2,3,3"}
        response = self.make_observations_filter_request(filter_params)
        self.assertEqual(response.data.get("count"), 0)

    def test_filter_observations_invalid_bbox_returns_400(self):
        """Test that invalid bbox parameters return 400 Bad Request instead of 500."""
        # Test with invalid bbox format (not 4 values)
        filter_params = {"bbox": "0,0,1"}
        response = self.make_observations_filter_request(filter_params, expect_success=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        self.assertIn("Invalid bbox param", response.data["error"])

        # Test with non-numeric values in bbox
        filter_params = {"bbox": "a,b,c,d"}
        response = self.make_observations_filter_request(filter_params, expect_success=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        self.assertIn("Invalid bbox param", response.data["error"])

    def test_filter_observations_multiple_ids_returns_400(self):
        """Test that specifying multiple IDs returns 400 Bad Request instead of 500."""
        # Test with both subject_id and source_id
        filter_params = {"subject_id": str(self.elephant.id), "source_id": str(self.collar.id)}
        response = self.make_observations_filter_request(filter_params, expect_success=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        self.assertIn("Can only specify one of", response.data["error"])

        # Test with all three IDs
        filter_params = {
            "subject_id": str(self.elephant.id),
            "source_id": str(self.collar.id),
            "subjectsource_id": str(self.elephant.subjectsources.all()[0].id),
        }
        response = self.make_observations_filter_request(filter_params, expect_success=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)
        self.assertIn("Can only specify one of", response.data["error"])

    def test_filter_observations_by_recorded_until(self):
        filter_params = {"until": self.observation_time + timedelta(days=1)}
        response = self.make_observations_filter_request(filter_params)

        self.assertEqual(response.data.get("count"), 1)

    def test_filter_observations_by_date_range(self):
        self.observation_data["recorded_at"] = self.observation_time + timedelta(days=4)
        self.observation2 = Observation.objects.create(**self.observation_data)

        filter_params = {"since": self.observation_time, "until": self.observation_time + timedelta(days=5)}
        response = self.make_observations_filter_request(filter_params)

        # self.observation and self.observation both lie in this range
        self.assertEqual(response.data.get("count"), 2)

    def make_observations_filter_request(self, filter_params, expect_success=True):
        url = reverse("observations-list-view")
        url += f"?{urlencode(filter_params)}"
        request = self.factory.get(self.api_base + url)

        self.force_authenticate(request, self.user)
        response = ObservationsView.as_view()(request)
        if expect_success:
            self.assertEqual(response.status_code, 200)
        return response

    def test_observation_readonly_can_view(self):
        url = reverse("observations-list-view")

        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.observations_readonly_user)

        response = ObservationsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_observation_readonly_cannot_add(self):
        url = reverse("observations-list-view")

        request = self.factory.post(self.api_base + url, self.observation_post_data)
        self.force_authenticate(request, self.observations_readonly_user)

        response = ObservationsView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_observation_can_add(self):
        url = reverse("observations-list-view")

        request = self.factory.post(self.api_base + url, self.observation_post_data)
        self.force_authenticate(request, self.observations_readwrite_user)

        response = ObservationsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

    def test_observation_can_patch_exclusion_flag(self):
        url = reverse("observations-list-view")

        request = self.factory.post(self.api_base + url, self.observation_post_data)
        self.force_authenticate(request, self.observations_readwrite_user)

        response = ObservationsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        observation_data = response.data
        assert observation_data["exclusion_flags"] == 0
        observation_data["exclusion_flags"] = 1

        url = reverse("observation-view", kwargs={"id": observation_data["id"]})
        request = self.factory.patch(self.api_base + url, observation_data)
        self.force_authenticate(request, self.observations_readwrite_user)

        response = ObservationView.as_view()(request, id=str(observation_data["id"]))
        assert response.status_code == 200
        assert response.data["exclusion_flags"] == observation_data["exclusion_flags"]

    def _get_tenant(self):
        return das_tenant_management.get_or_create_tenant()


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestObservationsFilterView:
    def test_filter_by_subject_ascending(
        self, five_observations, superuser_client, subject_source, tenant_response, tenant_document_cache_client_mock
    ):
        subject = subject_source.subject
        source = subject_source.source
        url = reverse("observations-list-view") + f"?subject_id={subject.id}"
        observations = Observation.objects.all().order_by("recorded_at")
        observations.update(source=source)
        waited_order_id = [str(observation.id) for observation in five_observations]

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 5
        assert waited_order_id == [str(item.get("id")) for item in response.data["results"]]

    def test_filter_by_subject_descending(
        self, five_observations, superuser_client, subject_source, tenant_response, tenant_document_cache_client_mock
    ):
        subject = subject_source.subject
        source = subject_source.source
        url = reverse("observations-list-view") + f"?subject_id={subject.id}&sort_by=-recorded_at"
        observations = Observation.objects.all().order_by("-recorded_at")
        observations.update(source=source)
        waited_order_id = [str(observation.id) for observation in observations]

        response = superuser_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 5
        assert waited_order_id == [str(item.get("id")) for item in response.data["results"]]

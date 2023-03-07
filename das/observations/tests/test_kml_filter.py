import io
import random
import zipfile
from datetime import datetime, timedelta
from urllib.parse import urlencode

import pytest
import pytz
from fastkml import kml
from pytz import timezone, utc

from django.core.management import call_command

import observations.views as views
from accounts.models import PermissionSet, User
from core.tests import API_BASE, BaseAPITest
from observations.models import Observation, Source, Subject, SubjectGroup
from observations.serializers import ObservationSerializer


@pytest.mark.usefixtures("tenant_settings")
class KmlSubjectViewTest(BaseAPITest):
    def setUp(self):
        super().setUp()
        call_command("loaddata_with_tenant", "new_permission_sets.yaml")
        call_command("loaddata_with_tenant", "subject_types.yaml")
        call_command("loaddata_with_tenant", "test/observations_subject_observation.json")
        user_const = dict(last_name="last", first_name="first")
        self.superuser = User.objects.create_user(
            "super", "super@test.com", "super", is_superuser=True, is_staff=True, **user_const
        )
        self.user = User.objects.create_user(
            "user", "user@test.com", "super", is_superuser=False, is_staff=True, **user_const
        )
        self.subject_group = SubjectGroup.objects.get(name="elephant subjet group")
        self.subject = Subject.objects.get(name="Junkie")
        self.subject_group.permission_sets.add(PermissionSet.objects.get(name="View Tracks Last 7 Days"))
        self.user.permission_sets.add(PermissionSet.objects.get(name="View Tracks Last 7 Days"))

        for i in range(50, 1, -1):
            recorded_at = utc.localize(datetime.now()) - timedelta(hours=i)
            fields = {
                "location": "SRID=4326;POINT(37.7991526330116 -12.28439367309)",
                "created_at": recorded_at,
                "source": Source.objects.get(id="dcf1590e-9b1c-4c4b-91b7-388ef4155064"),
                "additional": {},
                "recorded_at": recorded_at,
                "exclusion_flags": 0,
            }
            Observation.objects.create(**fields)

    @staticmethod
    def get_observations_timestamp(response):
        """
        This will take response(kmz file) as parameter and return back
        list of timestamp(recorded_at) from observations.
        :param response:
        :return list of timestamp:
        """
        kmz = zipfile.ZipFile(io.BytesIO(response.render().content), "r")
        kml_data = ""
        for name in kmz.namelist():
            kml_data = kmz.read(name)
        kml_object = kml.KML.from_string(kml_data)
        timestamps = []

        observations = kml_object.features[0].features[0].features
        for observation in observations:
            timestamps.append(observation.time_stamp.dt)
        return timestamps

    def test_view_without_filter(self):
        subject = Subject.objects.get(name="Junkie")
        kwargs = {"id": str(subject.id)}
        self.request = self.factory.get(API_BASE + "/subject/{0}/kml".format(subject.id))
        self.force_authenticate(self.request, self.superuser)

        response = views.KmlSubjectView.as_view()(self.request, **kwargs)
        self.assertEqual(response.status_code, 200)
        timestamps = self.get_observations_timestamp(response)
        lower = utc.localize(datetime.now() - timedelta(days=60))
        upper = utc.localize(datetime.now())
        self.assertTrue(any(upper >= timestamp >= lower for timestamp in timestamps))

    def test_start_end_filter_with_admin_user(self):
        subject = Subject.objects.get(name="Junkie")
        start_date = "2017-07-18T01:00:00.000Z"
        end_date = "2018-10-07T01:00:00.000Z"
        exclusion_flag = "0"
        kwargs = {"id": str(subject.id)}
        kml_filters = {"start": start_date, "end": end_date, "filter": exclusion_flag}
        self.request = self.factory.get(API_BASE + "/subject/{0}/kml?{1}".format(subject.id, urlencode(kml_filters)))
        self.force_authenticate(self.request, self.superuser)

        response = views.KmlSubjectView.as_view()(self.request, **kwargs)
        self.assertEqual(response.status_code, 200)
        timestamps = self.get_observations_timestamp(response)
        if timestamps:
            lower = utc.localize(datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%S.%fZ"))
            upper = utc.localize(datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S.%fZ"))
            self.assertTrue(any(upper >= timestamp >= lower for timestamp in timestamps))

    def test_seven_day_permission_with_filter_for_normal_user(self):
        # Generate some random data for the observation.
        observation_time = utc.localize(datetime.now())
        fixed_latitude = float(random.randint(3000, 3000)) / 100
        fixed_longitude = float(random.randint(2800, 4000)) / 100
        fixed_location = dict(longitude=fixed_longitude, latitude=fixed_latitude)
        observation = {
            "location": fixed_location,
            "recorded_at": observation_time,
            "source": "dcf1590e-9b1c-4c4b-91b7-388ef4155064",
            "additional": {},
            "exclusion_flags": 0,
        }
        serializer = ObservationSerializer(data=observation)
        self.assertTrue(serializer.is_valid(), msg="Observation is not valid.")
        if serializer.is_valid():
            observation = serializer.save()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        exclusion_flag = "0"
        kwargs = {"id": str(self.subject.id)}
        kml_filters = {
            "start": start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "end": end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "filter": exclusion_flag,
        }
        self.request = self.factory.get(
            API_BASE + "/subject/{0}/kml?{1}".format(self.subject.id, urlencode(kml_filters))
        )
        self.force_authenticate(self.request, self.user)

        response = views.KmlSubjectView.as_view()(self.request, **kwargs)
        self.assertEqual(response.status_code, 200)
        timestamps = self.get_observations_timestamp(response)
        if timestamps:
            start_date = utc.localize(start_date)
            end_date = utc.localize(end_date)
            self.assertTrue(any(end_date >= timestamp >= start_date for timestamp in timestamps))
            self.assertTrue(
                observation.recorded_at in timestamps
                or observation.recorded_at.astimezone(timezone("America/Los_Angeles"))
            )

    def test_filter_subject_kml_with_timezone_aware_datetimes(self):
        subject_id = "c25e17d0-0337-4f0c-9274-25e5ae4da7c0"
        Subject.objects.create_subject(
            id=subject_id,
            name="Elephant 5",
            subject_subtype_id="elephant",
            additional={"region": "Region 1", "country": "USA"},
        )

        start_date = pytz.utc.localize(datetime.now() - timedelta(weeks=60))
        end_date = pytz.utc.localize(datetime.now() - timedelta(weeks=50))
        kml_filters = {
            "start": start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "end": end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
        self.request = self.factory.get(API_BASE + "/subject/{0}/kml?{1}".format(subject_id, urlencode(kml_filters)))

        self.force_authenticate(self.request, self.superuser)
        kwargs = {"id": subject_id}

        response = views.KmlSubjectView.as_view()(self.request, **kwargs)
        self.assertEqual(response.status_code, 200)

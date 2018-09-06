import io
import zipfile
import fastkml
import random
from datetime import datetime, timedelta
from pytz import utc,timezone
from django.contrib.auth.models import Permission
from urllib.parse import urlencode
from core.tests import BaseAPITest
from observations.models import Observation, SubjectGroup, Subject, Source
from accounts.models import User, PermissionSet
from observations.serializers import ObservationSerializer

import observations.views as views

API_BASE = '/api/v1.0'


class KmlSubjectViewTest(BaseAPITest):
    fixtures = [
        'new_permission_sets.yaml',
        'subject_types.yaml',
        'test/observations_subject_observation.json',
    ]

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.superuser = User.objects.create_user(
            'super', 'super@test.com', 'super', is_superuser=True,
            is_staff=True, **user_const)
        self.user = User.objects.create_user(
            'user', 'user@test.com', 'super', is_superuser=False,
            is_staff=True, **user_const)
        self.subject_group = SubjectGroup.objects.get(
            name='elephant subjet group')
        self.subject = Subject.objects.get(name='Junkie')
        self.subject_group.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks Last 7 Days')
        )
        self.user.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks Last 7 Days')
        )

    def get_observations(self, response):
        kmz = zipfile.ZipFile(io.BytesIO(response.render().content), 'r')
        for name in kmz.namelist():
            kml_data = kmz.read(name)
        kml_object = fastkml.kml.KML()
        kml_object.from_string(kml_data)
        timestamps = []
        kml_subject = list(kml_object.features())
        kml_subject_details = list(kml_subject[0].features())
        for point_type in kml_subject_details:
            if 'points' in point_type.name:
                observation_details = point_type
                break
        observations = list(observation_details.features())
        for observation in observations:
            timestamps.append(observation.timeStamp)
        return timestamps

    def test_view_without_filter(self):
        subject = Subject.objects.get(name='Junkie')
        kwargs = {'id': str(subject.id)}
        self.request = self.factory.get(
            API_BASE + '/subject/{0}/kml'.format(subject.id))
        self.force_authenticate(self.request, self.superuser)

        response = views.KmlSubjectView.as_view()(self.request, **kwargs)
        self.assertEqual(response.status_code, 200)
        timestamps = self.get_observations(response)
        lower = utc.localize(datetime.now() - timedelta(days=60))
        upper = utc.localize(datetime.now())
        self.assertTrue(
            any(upper >= timestamp >= lower for timestamp in timestamps)
        )

    def test_start_end_filter_with_admin_user(self):
        subject = Subject.objects.get(name='Junkie')
        start_date = '2017-07-18'
        end_date = '2018-10-07'
        exclusion_flag = '0'
        kwargs = {'id': str(subject.id)}
        kml_filters = {'start': start_date, 'end': end_date,
                       'filter': exclusion_flag}
        self.request = self.factory.get(
            API_BASE + '/subject/{0}/kml?{1}'.format(
                subject.id, urlencode(kml_filters)))
        self.force_authenticate(self.request, self.superuser)

        response = views.KmlSubjectView.as_view()(self.request, **kwargs)
        self.assertEqual(response.status_code, 200)
        timestamps = self.get_observations(response)
        if timestamps:
            lower = utc.localize(datetime.strptime(start_date, '%Y-%m-%d'))
            upper = utc.localize(datetime.strptime(end_date, '%Y-%m-%d'))
            self.assertTrue(
                any(upper >= timestamp >= lower for timestamp in timestamps))

    def test_seven_day_permission_with_filter_for_normal_user(self):
        # Generate some random data for the observation.
        observation_time = utc.localize(datetime.now())
        fixed_latitude = float(random.randint(3000, 3000)) / 100
        fixed_longitude = float(random.randint(2800, 4000)) / 100
        fixed_location = dict(longitude=fixed_longitude,
                              latitude=fixed_latitude)
        observation = {
            'location': fixed_location,
            'recorded_at': observation_time,
            'source': "dcf1590e-9b1c-4c4b-91b7-388ef4155064",
            'additional': {},
            'exclusion_flags': 0
        }
        serializer = ObservationSerializer(data=observation)
        self.assertTrue(serializer.is_valid(), msg='Observation is not valid.')
        if serializer.is_valid():
            observation = serializer.save()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        exclusion_flag = '0'
        kwargs = {'id': str(self.subject.id)}
        kml_filters = {'start': start_date, 'end': end_date,
                       'filter': exclusion_flag}
        self.request = self.factory.get(
            API_BASE + '/subject/{0}/kml?{1}'.format(
                self.subject.id, urlencode(kml_filters)))
        self.force_authenticate(self.request, self.user)

        response = views.KmlSubjectView.as_view()(self.request, **kwargs)
        self.assertEqual(response.status_code, 200)
        timestamps = self.get_observations(response)
        if timestamps:
            start_date = utc.localize(start_date)
            end_date = utc.localize(end_date)
            self.assertTrue(
                any(end_date >= timestamp >= start_date for timestamp in timestamps)
            )
            self.assertTrue(observation.recorded_at in timestamps or
                            observation.recorded_at.astimezone(timezone('US/Pacific')))
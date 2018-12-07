import random
import pytz
from datetime import datetime
from urllib.parse import urlencode

from dateutil import tz
from pytz import utc
from django.utils import timezone

from accounts.models import User, PermissionSet
from core.tests import BaseAPITest
from observations.models import Observation, SubjectGroup
from observations.serializers import ObservationSerializer
from observations.views import TrackingMetaDataExportView, TrackingDataCsvView

API_BASE = '/api/v1.0'

current_tz_name = timezone.get_current_timezone_name()
current_tz = pytz.timezone(current_tz_name)
current_date = datetime.utcnow().astimezone(current_tz)
tz_difference = current_date.utcoffset().total_seconds() / 60 / 60
tz_offset = 'GMT' + ('+' if tz_difference >= 0 else '') + str(
    int(tz_difference)) + ':' + str(
    int((tz_difference - int(tz_difference)) * 60)
)


class TrackingMetaDataExportViewTest(BaseAPITest):
    fixtures = [
        'new_permission_sets.yaml',
        'subject_types.yaml',
        'test/observations_subject_meta_and_track_data.json',
    ]

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.superuser = User.objects.create_user(
            'super', 'super@test.com', 'super', is_superuser=True,
            is_staff=True, **user_const)
        new_user_const = dict(last_name='Joe', first_name='Don')
        self.user = User.objects.create_user(
            'new', 'user@test.com', 'user', is_superuser=False,
            is_staff=True, **new_user_const)
        self.user.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks Last 60 Days')
        )
        self.subject_group = SubjectGroup.objects.get(
            name='Indian elephant subjet group')
        self.subject_group.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks Last 60 Days')
        )

    def test_csv_metadata(self):
        self.request = self.factory.get(API_BASE + '/trackingmetadata/export/')
        self.force_authenticate(self.request, self.superuser)
        response = TrackingMetaDataExportView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)

    def test_csv_metadata_with_simple_user(self):
        self.request = self.factory.get(API_BASE + '/trackingmetadata/export/')
        self.force_authenticate(self.request, self.user)
        response = TrackingMetaDataExportView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)
        csv_file_data = response.content.decode("utf-8").split('\r\n')

        # Header from first line of csv file data
        header = csv_file_data[0].split(',')

        # Remove header and empty line from csv_data to get actual values
        csv_data = [row.split(',') for row in csv_file_data[1:-1]]
        metadatas = [dict(zip(header, data)) for data in csv_data]
        subject_names = [
            subject.name for subject in self.subject_group.get_all_subjects(
                self.user)
        ]
        metadata_subject_names = [metadata['name'] for metadata in metadatas]
        self.assertEqual(subject_names, metadata_subject_names)


class TrackingDataCsvViewTest(BaseAPITest):
    fixtures = [
        'new_permission_sets.yaml',
        'subject_types.yaml',
        'test/observations_subject_meta_and_track_data.json',
    ]

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.superuser = User.objects.create_user(
            'super', 'super@test.com', 'super', is_superuser=True,
            is_staff=True, **user_const)
        new_user_const = dict(last_name='Joe', first_name='Don')
        self.user = User.objects.create_user(
            'new', 'user@test.com', 'user', is_superuser=False,
            is_staff=True, **new_user_const)
        self.user.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks Last 60 Days')
        )
        self.subject_group = SubjectGroup.objects.get(
            name='Indian elephant subjet group')
        self.subject_group.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks Last 60 Days')
        )

    # Basic CSV read, admin is able to access all data (exclusion flag = 0)
    def test_csv_observation_data(self):
        self.request = self.factory.get(API_BASE + '/tracking_data/')
        self.force_authenticate(self.request, self.superuser)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)
        csv_data = response.content.decode("utf-8").split('\r\n')
        # Remove header and empty line from csv_data to get actual values
        csv_data = csv_data[1:-1]
        self.assertEqual(
            Observation.objects.filter(
                exclusion_flags=0).count(), len(csv_data)
        )

    def test_csv_observation_data_with_exclusion_flag(self):
        observation_filter = {'filter': 1}
        self.request = self.factory.get(API_BASE + '/tracking_data/?{0}'.format(
            urlencode(observation_filter)
        ))
        self.force_authenticate(self.request, self.superuser)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)
        csv_data = response.content.decode("utf-8").split('\r\n')

        # Remove header and empty line from csv_data to get actual values
        csv_data = csv_data[1:-1]
        self.assertEqual(
            Observation.objects.filter(
                exclusion_flags=1).count(), len(csv_data)
        )

    def test_normal_user_access_subject_observation_data(self):
        # Generate random observation date & link with source.
        observation_time = utc.localize(datetime.now())
        fixed_latitude = float(random.randint(3000, 3000)) / 100
        fixed_longitude = float(random.randint(2800, 4000)) / 100
        fixed_location = dict(longitude=fixed_longitude,
                              latitude=fixed_latitude)
        sample_observation_data = {
            'location': fixed_location,
            'recorded_at': observation_time,
            'source': "bac7c1bf-fe59-4d8c-a4d0-bad7a5bce59d",
            'additional': {},
            'exclusion_flags': 0
        }

        serializer = ObservationSerializer(data=sample_observation_data)
        self.assertTrue(serializer.is_valid(), msg='Observation is not valid.')
        if serializer.is_valid():
            sample_observation = serializer.save()

        # Get observation for subjects linked with user
        self.request = self.factory.get(API_BASE + '/tracking_data/')
        self.force_authenticate(self.request, self.user)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)

        csv_file_data = response.content.decode("utf-8").split('\r\n')

        # Header from first line of csv file data
        header = csv_file_data[0].split(',')

        # Remove header and empty line from csv_data to get actual values
        csv_data = [row.split(',') for row in csv_file_data[1:-1]]
        observations = [dict(zip(header, data)) for data in csv_data]

        # Add GMT timezone format in fixtime_key & dloadtime_key
        fixtime_key = 'fixtime ({})'.format(tz_offset)
        dloadtime_key = 'dloadtime ({})'.format(tz_offset)
        for observation in observations:
            fixtime_key = next(key for key in observation.keys()
                               if key.startswith('fixtime'))
            dloadtime_key = next(key for key in observation.keys() if
                                 key.startswith('dloadtime'))
            break

        # Get list of fixtime(recorded_at from observations.Observation model)
        recorded_at_timestamps = [observation[fixtime_key]
                                  for observation in observations]
        recorded_time = sample_observation.recorded_at.astimezone(
            tz.gettz(timezone.get_current_timezone_name())).strftime('%m/%d%Y %H:%M:%S')
        self.assertIn(recorded_time, recorded_at_timestamps)

    def test_different_chronofile_values_for_same_subject(self):
        # check if we are getting different chronofile values for single
        # subject
        self.subject_group.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks All Time')
        )
        self.user.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks All Time')
        )
        self.request = self.factory.get(API_BASE + '/tracking_data/')
        self.force_authenticate(self.request, self.user)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)

        csv_file_data = response.content.decode("utf-8").split('\r\n')

        # Header from first line of csv file data
        header = csv_file_data[0].split(',')

        # Remove header and empty line from csv_data to get actual values
        csv_data = [row.split(',') for row in csv_file_data[1:-1]]
        observations = [dict(zip(header, data)) for data in csv_data]

        # Get list of chronofile
        chrono_files = [observation['chronofile']
                        for observation in observations]
        unique_chrono_files = list(set(chrono_files))

        self.assertTrue(len(unique_chrono_files) > 1)

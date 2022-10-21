import random
import pytz
from datetime import datetime
from urllib.parse import urlencode

from dateutil import tz, parser
from django.utils import timezone
from django.db.models import F

from accounts.models import User, PermissionSet
from core.tests import BaseAPITest, API_BASE
from observations.models import Observation, SubjectGroup
from observations.serializers import ObservationSerializer
from observations.views import TrackingMetaDataExportView, TrackingDataCsvView


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
        assert all([name in subject_names for name in metadata_subject_names])

        chronofiles = (474, 256)
        chronofiles_in_meta = [int(metadata['chronofile'])
                               for metadata in metadatas]

        assert len(chronofiles) == len(chronofiles_in_meta)
        assert all([chrono in chronofiles for chrono in chronofiles_in_meta])

    def test_csv_metadata_with_inactive_subject(self):
        inactive_subject_name = ''
        for subject in self.subject_group.get_all_subjects(self.user):
            subject.is_active = False
            subject.save()
            inactive_subject_name = subject.name
            break
        self.request = self.factory.get(
            API_BASE + '/trackingmetadata/export/?include_inactive=True')
        self.force_authenticate(self.request, self.user)
        response = TrackingMetaDataExportView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)
        csv_file_data = response.content.decode("utf-8").split('\r\n')

        # Header from first line of csv file data
        header = csv_file_data[0].split(',')

        # Remove header and empty line from csv_data to get actual values
        csv_data = [row.split(',') for row in csv_file_data[1:-1]]
        metadatas = [dict(zip(header, data)) for data in csv_data]
        metadata_subject_names = [metadata['name'] for metadata in metadatas]
        # Check inactive_subject_name in subject's name list from metadata
        self.assertIn(inactive_subject_name, metadata_subject_names)


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
        self.request = self.factory.get(API_BASE + '/trackingdata/export/')
        self.force_authenticate(self.request, self.superuser)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)
        csv_data = response.content.decode("utf-8").split('\r\n')
        # Remove header and empty line from csv_data to get actual values
        csv_data = csv_data[1:-1]
        self.assertEqual(
            Observation.objects.filter(source__subjectsource__assigned_range__contains=F('recorded_at'),
                                       exclusion_flags=0).count(), len(csv_data)
        )

    def filter_observations_with_exclusion_flag(self, observation_filter):
        self.request = self.factory.get(
            API_BASE + '/trackingdata/export/?{0}'.format(
                urlencode(observation_filter)
            ))
        self.force_authenticate(self.request, self.superuser)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)
        csv_data = response.content.decode("utf-8").split('\r\n')

        # Remove header and empty line from csv_data to get actual values
        csv_data = csv_data[1:-1]
        return csv_data

    def test_csv_observation_data_with_exclusion_flag(self):
        # filter1, returns all observations with exclusion flag 1
        observation_filter = {'filter': 1}
        csv_data = self.filter_observations_with_exclusion_flag(
            observation_filter)

        self.assertEqual(
            Observation.objects.filter(source__subjectsource__assigned_range__contains=F('recorded_at'),
                                       exclusion_flags=1).count(), len(csv_data)
        )

    def test_csv_observation_data_with_exclusion_flag_set_to_3(self):
        observation_filter = {'filter': 3}
        csv_data = self.filter_observations_with_exclusion_flag(
            observation_filter)

        # All observations are returned (1 or 2), excluding observations with flag 0
        self.assertEqual(
            Observation.objects.filter(source__subjectsource__assigned_range__contains=F(
                'recorded_at')).exclude(exclusion_flags=0).count(), len(csv_data)
        )

    def test_csv_observation_data_with_exclusion_flag_set_to_null(self):
        observation_filter = {'filter': 'null'}
        csv_data = self.filter_observations_with_exclusion_flag(
            observation_filter)

        # All observations are returned
        self.assertEqual(
            Observation.objects.filter(source__subjectsource__assigned_range__contains=F('recorded_at')).count(), len(csv_data))

    def test_normal_user_access_subject_observation_data(self):
        # Generate random observation date & link with source.
        observation_time = datetime.now(tz=timezone.utc)
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
            tz.gettz(timezone.get_current_timezone_name())).strftime('%m/%d/%Y %H:%M:%S')
        self.assertIn(recorded_time, recorded_at_timestamps)

    def exportrecords(self, url):
        self.subject_group.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks All Time')
        )
        self.user.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks All Time')
        )
        self.request = self.factory.get(API_BASE + url)
        self.force_authenticate(self.request, self.user)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)

        csv_file_data = response.content.decode("utf-8").split('\r\n')

        # Header from first line of csv file data
        header = csv_file_data[0].split(',')

        # Remove header and empty line from csv_data to get actual values
        csv_data = [row.split(',') for row in csv_file_data[1:-1]]
        observations = [dict(zip(header, data)) for data in csv_data]
        return observations

    def test_different_chronofile_values_for_same_subject(self):
        # check if we are getting different chronofile values for single
        # subject

        observations = self.exportrecords('/trackingdata/export/')

        # Get list of chronofile
        chrono_files = [observation['chronofile']
                        for observation in observations]
        unique_chrono_files = list(set(chrono_files))

        self.assertTrue(len(unique_chrono_files) > 1)

    def test_csv_export_with_observation_addition_null(self):
        self.request = self.factory.get(API_BASE + '/trackingdata/export/')
        self.force_authenticate(self.request, self.superuser)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertEqual(response.status_code, 200)

    def test_tracking_data_for_specific_subject(self):
        observations = self.exportrecords(
            '/trackingdata/export/?subject_id=0fa8ec9a-7e92-4575-9575-df202d5dde25')

        # Get subject_idsreturned
        unique_subject_ids = list(set([observation['subject_id']
                                       for observation in observations]))

        self.assertTrue(len(unique_subject_ids) == 1)

    def test_tracking_data_current_status_for_specific_subject(self):
        request = self.factory.get(
            API_BASE + '/trackingdata/export/?current_status=true&format=json&subject_id=0fa8ec9a-7e92-4575-9575-df202d5dde25?')
        self.force_authenticate(request, self.user)
        response = TrackingDataCsvView.as_view()(request)
        self.assertEquals(response.status_code, 200)
        self.assertEquals(len(response.data), 1)

    def test_tracking_data_for_specific_subject_with_invalid_uuid(self):
        self.request = self.factory.get(
            API_BASE + '/trackingdata/export/?subject_id=1')
        self.force_authenticate(self.request, self.user)
        response = TrackingDataCsvView.as_view()(self.request)
        self.assertIn('1 is not a valid UUID', response.data['Error'])
        self.assertEquals(response.status_code, 400)

    def test_csv_observation_with_inactive_subject(self):
        inactive_subject_observation_fix_times = []
        csv_observation_ids = []
        self.subject_group.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks All Time')
        )
        self.user.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks All Time')
        )
        # Make all subjects as inactive subject, get their observation's ids
        for subject in self.subject_group.get_all_subjects(self.user):
            subject.is_active = False
            subject.save()
            for obs in Observation.objects.get_subject_observations(subject):
                inactive_subject_observation_fix_times.append(obs.recorded_at)
        africa_subject_group = SubjectGroup.objects.get(
            name='African elephant subjet group')
        africa_subject_group.permission_sets.add(PermissionSet.objects.get(
            name='View Tracks All Time')
        )
        for subject in africa_subject_group.get_all_subjects(self.user):
            subject.is_active = False
            subject.save()
            for obs in Observation.objects.get_subject_observations(subject):
                inactive_subject_observation_fix_times.append(obs.recorded_at)

        request = self.factory.get(
            API_BASE + '/trackingdata/export/?include_inactive=True')
        self.force_authenticate(request, self.user)
        response = TrackingDataCsvView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        csv_file_data = response.content.decode("utf-8").split('\r\n')
        # Header from first line of csv file data
        header = csv_file_data[0].split(',')

        # Remove header and empty line from csv_data to get actual values
        csv_data = [row.split(',') for row in csv_file_data[1:-1]]
        observations = [dict(zip(header, data)) for data in csv_data]

        fixtime_key = 'fixtime ({})'.format(tz_offset)
        # Get list of observation ids
        csv_observation_ids = [observation[fixtime_key]
                               for observation in observations]

        observation_filter = {'filter': 1}
        request = self.factory.get(
            API_BASE + '/trackingdata/export/?{0}'.format(
                urlencode(observation_filter)
            ))
        self.force_authenticate(request, self.user)
        response = TrackingDataCsvView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        csv_data = response.content.decode("utf-8").split('\r\n')

        # Header from first line of csv file data
        header = csv_data[0].split(',')

        # Remove header and empty line from csv_data to get actual values
        csv_data = [row.split(',') for row in csv_data[1:-1]]
        observations = [dict(zip(header, data)) for data in csv_data]

        # Get list of observation ids
        fixtime_key = 'fixtime ({})'.format(tz_offset)
        csv_observation_ids.extend([observation[fixtime_key]
                                    for observation in observations])
        unique_csv_observation_ids = list(set(csv_observation_ids))
        unique_csv_observation_ids = [current_tz.localize(
            parser.parse(obs_time)) for obs_time in unique_csv_observation_ids]
        self.assertTrue(any([obs_time.astimezone(current_tz) in unique_csv_observation_ids
                             for obs_time in inactive_subject_observation_fix_times])
                        )

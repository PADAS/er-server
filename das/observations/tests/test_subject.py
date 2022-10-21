import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import dateutil.parser as dateparser
import pytest
import pytz
from pytz import UTC

import django.contrib.auth
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.contrib.messages.storage.cookie import CookieStorage
from django.core.files import File
from django.db import transaction
from django.http import QueryDict
from django.test import RequestFactory, override_settings
from django.urls import reverse

from accounts.models import PermissionSet
from client_http import HTTPClient
from core.tests import BaseAPITest
from observations.admin import GPXAdmin
from observations.models import (GPXTrackFile, Observation, Source, Subject,
                                 SubjectSource, SubjectStatus, SubjectSubType)
from observations.tasks import process_trackpoints
from observations.utils import calculate_track_range
from observations.views import GPXFileUploadView, SubjectsView

User = django.contrib.auth.get_user_model()
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          'tests')


class SubjectTestCase(BaseAPITest):
    fixtures = [
        'test/user_and_usergroup.yaml',
        'test/source_group.json',
        'test/observations_source.json',
        'test/observations_subject.json',
        'test/observations_subject_source.json',
        'test/observations_observation.json',
    ]

    def setUp(self):
        super().setUp()
        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **user_const)
        self.no_perms_user = User.objects.create_user('no_perms_user',
                                                      'das_no_perms@vulcan.com',
                                                      'noperms',
                                                      **user_const)
        self.site = AdminSite()
        self.request = RequestFactory()
        self.admin = GPXAdmin(model=GPXTrackFile, admin_site=self.site)

    def test_empty_point_not_included_in_subject_tracks(self):
        from django.contrib.gis.geos import Point
        coordinates = self.get_coordinates_returned()
        # Existing trackpoint from fixtures
        monitored_location = Point(50.7586930900307, 40.3297162190965)
        self.assertEqual(3, len(coordinates))
        self.assertIn(monitored_location.coords, coordinates)

        # Update one coordinate to an empty point
        Observation.objects.filter(
            location=monitored_location).update(location=Point(0, 0))
        new_coordinates = self.get_coordinates_returned()
        self.assertNotIn(monitored_location.coords, new_coordinates)
        # Track not included in tracks
        self.assertEqual(2, len(new_coordinates))

    def get_coordinates_returned(self):
        from observations import views
        self.satellite_user = User.objects.get(username='satellite-user')
        self.henry = Subject.objects.get(name='Henry')

        request = self.factory.get(
            self.api_base + '/subject/{}/tracks/'.format(self.henry.id))
        self.force_authenticate(request, self.satellite_user)
        response = views.SubjectTracksView.as_view()(request, subject_id=self.henry.id)
        return response.data['features'][0]['geometry']['coordinates']

    def test_subject_observations(self):
        subject = Subject.objects.get(name='Topsy')
        actual = len(subject.observations())
        expected = 1

        self.assertEqual(actual, expected)

    def test_subject_observations_last_days(self):
        subject = Subject.objects.get(name='Topsy')
        point = Point((0.000001, 0.000001))  # really close to Null Island
        t1 = datetime.now(tz=UTC) - timedelta(days=2)
        t2 = datetime.now(tz=UTC) - timedelta(days=20)

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
        )

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t2,
            additional={}
        )

        actual = len(subject.observations(last_hours=3*24))
        expected = 1

        self.assertEqual(actual, expected)

        actual = len(subject.observations(last_hours=30*24))
        expected = 2

        self.assertEqual(actual, expected)

    def test_add_subject(self):
        data = {
            "name": "testCheetah",
            "subject_type": "wildlife",
            "subject_subtype": "cheetah",
            "additional": {},
            "is_active": True
        }
        url = reverse('subjects-list-view')
        request = self.factory.post(url, data)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

    def test_call_subject_api(self):
        url = reverse('subjects-list-view')
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        # no paging by default
        assert "next" not in response.data

    def test_filter_subject_api_updated_since(self):
        url = reverse('subjects-list-view')
        url += '?updated_since=2019-02-03'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_filter_subject_api_using_updated_until_param(self):
        url = reverse('subjects-list-view')
        url += '?updated_since=2019-04-02'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_filter_subject_api_using_updated_since_and_updated_until_param(self):
        url = reverse('subjects-list-view')
        url += '?updated_since=2019-04-02&updated_until=2019-03-02'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(SHOW_STATIONARY_SUBJECTS_ON_MAP=True)
    @override_settings(SHOW_TRACK_DAYS=16)
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_date_range_filter_works(self):
        url = reverse('subjects-list-view')

        subject = Subject.objects.get(name='Topsy')
        subject2 = Subject.objects.get(name='Turvey')

        point = Point((-122.334, 47.598))
        t2 = datetime.now(tz=UTC)
        t1 = datetime.now(tz=UTC) - timedelta(days=3)

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
        )

        Observation.objects.create(
            source=subject2.source,
            location=point,
            recorded_at=t2,
            additional={}
        )

        updated_since = t1.date().isoformat()
        updated_until = t2.date().isoformat()
        url += f'?updated_since={updated_since}&updated_until={updated_until}'
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        actual = len(response.data)
        expected = 2
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actual, expected)

        last_positon_date_subject = json.loads(response.render().content.decode())[
            'data'][0]['last_position_date']
        last_positon_date_subject2 = json.loads(response.render().content.decode())[
            'data'][1]['last_position_date']

        last_positon_date_subject = dateparser.parse(
            last_positon_date_subject).date().isoformat()
        last_positon_date_subject2 = dateparser.parse(
            last_positon_date_subject2).date().isoformat()

        t1 = updated_since
        t2 = updated_until

        self.assertEqual(
            {t1, t2}, {last_positon_date_subject, last_positon_date_subject2})

        # Use url above together with bbox param
        # the 'point' lies within this bbox.
        bbox = '-122.49866134971379, 47.40051600277377, -122.225591570732, 47.67666096382156'
        url += '&bbox={}'.format(bbox)
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        actual_size = len(response.data)
        expected_size = 1
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actual_size, expected_size)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @override_settings(SHOW_TRACK_DAYS=16)
    def test_date_range_filter_works_with_bbox(self):
        url = reverse('subjects-list-view')

        subject = Subject.objects.get(name='Topsy')
        subject2 = Subject.objects.get(name='Turvey')

        point = Point((-122.334, 47.598))
        t1 = datetime.now(tz=UTC)
        t2 = datetime.now(tz=UTC) + timedelta(days=3)

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
        )

        Observation.objects.create(
            source=subject2.source,
            location=point,
            recorded_at=t2,
            additional={}
        )

        day = timedelta(days=1)
        updated_since = (t1.date() - day).isoformat()
        updated_until = (t2.date() + day).isoformat()
        url += f'?updated_since={updated_since}&updated_until={updated_until}'

        bbox = '-122.49866134971379, 47.40051600277377, -122.225591570732, 47.67666096382156'
        url += '&bbox={}'.format(bbox)
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        actual_size = len(response.data)
        expected_size = 2
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actual_size, expected_size)

    @property
    def additional_data_for_user(self):
        """Additional user data that sets the mou expiry to 5 days ago.

        Returns:
            [type]: [description]
        """
        expiry_date = (datetime.now(tz=UTC) -
                       timedelta(days=5)).date().isoformat()
        mou_datesigned = (datetime.now(tz=UTC) -
                          timedelta(days=50)).date().isoformat()
        additional_data = {
            'notes': 'Testing Notes',
            'expiry': expiry_date,
            'moudatesigned': mou_datesigned,
            'moutype': 'Sample MoU Type',
            'tech': ['iOS'],
            'organization': 'KWS',
        }
        return additional_data

    @override_settings(SHOW_TRACK_DAYS=16)
    def test_subject_api_returning_last_position_per_MOU_expiry(self):
        url = reverse('subjects-list-view')

        password = User.objects.make_random_password()
        extra_fields = dict(additional=self.additional_data_for_user)
        user = User.objects.create_user(username='Capt.America',
                                        email='Capt.American@avenger.com',
                                        password=password,
                                        is_superuser=True,
                                        is_staff=True,
                                        **extra_fields)

        subject = Subject.objects.get(name='Topsy')
        subject2 = Subject.objects.get(name='Turvey')
        subject3 = Subject.objects.get(name='StatusGuy')

        point = Point((-122.334, 47.598))
        t1 = datetime.now(tz=UTC) - timedelta(days=10)
        t2 = datetime.now(tz=UTC) - timedelta(days=7)
        t3 = datetime.now(tz=UTC) - timedelta(days=4)

        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
        )

        Observation.objects.create(
            source=subject2.source,
            location=point,
            recorded_at=t2,
            additional={}
        )

        Observation.objects.create(
            source=subject3.source,
            location=point,
            recorded_at=t3,
            additional={}
        )
        request = self.factory.get(url)

        self.force_authenticate(request, user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        response_data = json.loads(response.render().content.decode())['data']
        extracted_data = {}
        for o in response_data:
            if o['id'] == str(subject.id):
                extracted_data['subject_last_position'] = o['last_position_date']
            elif o['id'] == str(subject2.id):
                extracted_data['subject2_last_position'] = o['last_position_date']
            elif o['id'] == str(subject3.id):
                # Past MOU expiry date, should not retrieve observation past mou expiry date.
                assert 'last_position' not in o
                assert not o['tracks_available']

        # subject1 and subject2 are within MOU expiry date.
        subject_last_position = dateparser.parse(
            extracted_data.get('subject_last_position')).date().isoformat()
        subject2_last_postion = dateparser.parse(
            extracted_data.get('subject2_last_position')).date().isoformat()
        self.assertEqual(t1.date().isoformat(), subject_last_position)
        self.assertEqual(t2.date().isoformat(), subject2_last_postion)

    @override_settings(SHOW_TRACK_DAYS=16)
    def test_return_no_last_position_past_mou_expiry(self):
        url = reverse('subjects-list-view')

        password = User.objects.make_random_password()
        extra_fields = dict(additional=self.additional_data_for_user)
        user = User.objects.create_user(username='Capt.America',
                                        email='Capt.American@avenger.com',
                                        password=password,
                                        is_superuser=True,
                                        is_staff=True,
                                        **extra_fields)

        subject = Subject.objects.get(name='StatusGuy')
        point = Point((-122.334, 47.598))
        t1 = datetime.now(tz=UTC)

        # this observation is past mou date
        Observation.objects.create(
            source=subject.source,
            location=point,
            recorded_at=t1,
            additional={}
        )

        request = self.factory.get(url)

        self.force_authenticate(request, user)
        response = SubjectsView.as_view()(request)
        response_data = json.loads(response.render().content.decode())['data']

        for o in response_data:
            if o['id'] == str(subject.id):
                assert 'last_postion' not in o
                assert not o['tracks_available']

    def test_gpx_file_model(self):

        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        data = File(
            open(os.path.join(TESTS_PATH, 'testdata/gpsmap_data.gpx'), 'rb'))
        GPXTrackFile.objects.create(
            data=data, source_assignment=subject_source)

        self.assertEqual(GPXTrackFile.objects.count(), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_gpxfile_upload_on_adminpage(self):

        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        data = File(
            open(os.path.join(TESTS_PATH, 'testdata/gpsmap_data.gpx'), 'rb'))

        url = reverse('admin:observations_gpxtrackfile_add')
        url += f'?subject_id={subject.id}'
        request = self.factory.post(
            url, data={'source_assignment': subject_source.id, '_save': 'Save'})

        self.force_authenticate(request, self.user)
        query_dict = QueryDict('', mutable=True)
        post_data = {'source_assignment': subject_source.id, '_save': 'Save',
                     'csrfmiddlewaretoken': 'y3WZXVzvwNlEAYd76nA4MvdvVKSaGSiS91Q2HGwV8ag99etBRgAXs2FgLO49XU3e',
                     'description': ''}
        query_dict.update(post_data)

        request.FILES['data'] = data
        request.POST = query_dict
        request.META['CSRF_COOKIE'] = 'y3WZXVzvwNlEAYd76nA4MvdvVKSaGSiS91Q2HGwV8ag99etBRgAXs2FgLO49XU3e'

        messages = CookieStorage(request)
        setattr(request, '_messages', messages)

        self.assertFalse(GPXTrackFile.objects.all())  # No gpx on database.

        with patch('django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block',
                   lambda a: False):

            template_response = self.admin.changeform_view(request)
            transaction.get_connection().run_and_clear_commit_hooks()

            gpx_object = GPXTrackFile.objects.all()
            processed_status = gpx_object.values('processed_status')
            self.assertEqual(template_response.status_code, 302)
            self.assertTrue(
                "was successfully uploaded for processing" in messages._queued_messages[0].message)
            self.assertEqual(gpx_object.count(), 1)
            self.assertEqual(processed_status[0].get(
                'processed_status'), 'success')

            # This is an example of trackpoint that we expect to be saved in the observation table.
            # <trkpt lat="-2.573374444618821" lon="37.896002875640988">
            #     <ele>1244.769999999999982</ele>
            #     <time>2020-06-06T05:17:26Z</time>
            #  </trkpt>

            trkpoint_lat = '-2.573374444618821'
            trkpoint_lon = '37.896002875640988'
            trkpoint_time = dateparser.parse('2020-06-06T05:17:26Z')

            # trackpoint saved in observation table.
            trkpoint_obs = Observation.objects.filter(
                recorded_at=trkpoint_time, source__id=subject_source.source_id)
            self.assertTrue(trkpoint_obs.exists())

            obs_latitude = trkpoint_obs[0].location.y
            obs_longitude = trkpoint_obs[0].location.x
            self.assertEqual(float(trkpoint_lat), obs_latitude)
            self.assertEqual(float(trkpoint_lon), obs_longitude)

    @pytest.mark.skip(msg="After migration to Django 3.1 this test is not working anymore.")
    def test_gpx_upload_fails(self):
        # TODO FIXME: find a way to fix it.
        # It works on Django 2.2 but not on Django 3.1
        # It expect that the method GPXAdmin.changeform_view catch the exception,
        # but the exception doesn't happened in V3.0
        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        data = File(
            open(os.path.join(TESTS_PATH, 'testdata/gpsmap_data.gpx'), 'rb'))

        url = reverse('admin:observations_gpxtrackfile_add')
        request = self.factory.post(
            url, data={'source_assignment': subject_source.id, '_save': 'Save'})
        self.force_authenticate(request, self.user)
        query_ = QueryDict('', mutable=True)
        post_data = {'source_assignment': subject_source.id, '_save': 'Save',
                     'csrfmiddlewaretoken': ['y3WZXVzvwNlEAYd76nA4MvdvVKSaGSiS91Q2HGwV8ag99etBRgAXs2FgLO49XU3e'],
                     'description': ''}
        query_.update(post_data)

        # with ContexT() as c:
        request.FILES['data'] = data
        request.POST = query_
        request.META['CSRF_COOKIE'] = 'y3WZXVzvwNlEAYd76nA4MvdvVKSaGSiS91Q2HGwV8ag99etBRgAXs2FgLO49XU3e'

        messages = CookieStorage(request)
        setattr(request, '_messages', messages)

        gpx_object = GPXTrackFile.objects.all()
        processed_status = gpx_object.values('processed_status')
        template_response = self.admin.changeform_view(request)
        self.assertEqual(template_response.status_code, 302)
        self.assertTrue(
            "failed to be processed" in messages._queued_messages[0].message)
        self.assertEqual(processed_status[0].get(
            'processed_status'), 'failure')

    def test_calculate_track_range_fn(self):
        user = self.user
        t1 = datetime.now(tz=UTC) - timedelta(days=3, hours=2, minutes=30)
        since, until, limit = calculate_track_range(
            user=user, since=t1, until=None, limit=None)

        expected_since = t1.replace(microsecond=0, second=0).isoformat()
        returned_since = since.replace(microsecond=0, second=0).isoformat()
        self.assertEqual(returned_since, expected_since)

        # when since greater than today
        t2 = datetime.now(tz=UTC) + timedelta(days=3, hours=7, minutes=30)
        since, until, limit = calculate_track_range(
            user=user, since=t2, until=None, limit=None)

        expected_since = t2.replace(microsecond=0, second=0).isoformat()
        returned_since = since.replace(microsecond=0, second=0).isoformat()
        self.assertEqual(returned_since, expected_since)

    def test_calculate_track_range_fn_today(self):
        t1 = datetime.combine(datetime.today(), datetime.min.time()).replace(
            tzinfo=UTC)  # midnight
        since, until, limit = calculate_track_range(
            user=self.user, since=t1, until=None, limit=None)

        expected_since = t1.replace(microsecond=0, second=0).isoformat()
        returned_since = since.replace(microsecond=0).isoformat()
        self.assertEqual(returned_since, expected_since)

        t2 = t1.replace(hour=5, minute=45, second=0,
                        microsecond=0)  # past midnight
        since, until, limit = calculate_track_range(
            user=self.user, since=t2, until=None, limit=None)

        expected_since = t2.isoformat()
        returned_since = since.replace(microsecond=0, second=0).isoformat()
        self.assertEqual(returned_since, expected_since)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_process_gpx_file_upload_via_api(self):
        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        file = File(
            open(os.path.join(TESTS_PATH, 'testdata/gpsmap_data.gpx'), 'rb'))

        data = dict(gpx_file=file)

        url = reverse(
            'gpx-upload', kwargs={'id': str(subject_source.source_id)})
        request = self.factory.post(url, data, format='multipart')
        self.force_authenticate(request, self.user)

        response = GPXFileUploadView.as_view()(
            request, id=str(subject_source.source_id))
        self.assertEqual(response.status_code, 201)

        # This is an example of trackpoint that we expect to be saved in the observation table.
        # <trkpt lat="-2.573374444618821" lon="37.896002875640988">
        #     <ele>1244.769999999999982</ele>
        #     <time>2020-06-06T05:17:26Z</time>
        #  </trkpt>

        trkpoint_lat = '-2.573374444618821'
        trkpoint_lon = '37.896002875640988'
        trkpoint_time = dateparser.parse('2020-06-06T05:17:26Z')

        # trackpoint saved in observation table.
        trkpoint_obs = Observation.objects.filter(
            recorded_at=trkpoint_time, source__id=subject_source.source_id)
        self.assertTrue(trkpoint_obs.exists())

        obs_latitude = trkpoint_obs[0].location.y
        obs_longitude = trkpoint_obs[0].location.x
        self.assertEqual(float(trkpoint_lat), obs_latitude)
        self.assertEqual(float(trkpoint_lon), obs_longitude)

    def test_process_gpx_file_upload_with_no_trackpoints_time(self):
        source = Source.objects.first()
        trkpoints = [
            {'@lat': '-2.86950624063618', '@lon': '38.968550268933178',
                'ele': '506.110000000000018', 'time': '2020-06-06T04:17:28Z'},
            {'@lat': '-2.76951453872028', '@lon': '38.268555130437018', 'ele': '503.029999999999978'}]  # No trackpoints time
        file_name = "test_file.gpx"
        _, obs_errors = process_trackpoints(
            source, source.id, trkpoints, file_name)
        assert obs_errors == 'Points are missing timestamps in GPX file test_file.gpx'

    def test_process_gpx_upload_nopermission(self):
        # user that does not have permissions to create Observations records
        # cant import gpx file.
        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        file = File(
            open(os.path.join(TESTS_PATH, 'testdata/gpsmap_data.gpx'), 'rb'))

        data = dict(gpx_file=file)

        url = reverse(
            'gpx-upload', kwargs={'id': str(subject_source.source_id)})
        request = self.factory.post(url, data, format='multipart')

        self.force_authenticate(request, self.no_perms_user)
        response = GPXFileUploadView.as_view()(
            request, id=str(subject_source.source_id))
        self.assertEqual(response.status_code, 403)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_process_gpx_upload_with_create_observation_perm(self):
        # give user with no permission, permission to create observation.
        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        file = File(
            open(os.path.join(TESTS_PATH, 'testdata/gpsmap_data.gpx'), 'rb'))
        data = dict(gpx_file=file)

        observation_permission = ('add_observation',)
        permset = PermissionSet.objects.create(name='observation Permission')
        for perm in observation_permission:
            permset.permissions.add(Permission.objects.get(codename=perm))
        self.no_perms_user.permission_sets.add(permset)

        url = reverse(
            'gpx-upload', kwargs={'id': str(subject_source.source_id)})
        request = self.factory.post(url, data, format='multipart')

        self.force_authenticate(request, self.no_perms_user)
        response = GPXFileUploadView.as_view()(
            request, id=str(subject_source.source_id))
        self.assertTrue(self.no_perms_user.has_perm(
            'observations.add_observation'))
        self.assertEqual(response.status_code, 201)


@pytest.mark.django_db
class TestSubjectsView:

    def test_static_sensor_response(self, subject_source):
        now = datetime.now(tz=pytz.utc)
        subject_source.location = Point(-103.6, 20.6)
        subject_source.save()
        subject = subject_source.subject
        subject.name = "Subject test"
        subject.subject_subtype = SubjectSubType.objects.get(
            display="Camera Trap")
        subject.save()
        source_provider = subject_source.source.provider
        source_provider.transforms = [
            {
                "default": False,
                "dest": "temperature",
                "label": "temp",
                "source": "temperature",
                "units": "c"
            },
            {
                "default": True,
                "dest": "speed",
                "label": "speed",
                "source": "speed",
                "units": "km"
            }
        ]
        source_provider.save()
        Observation.objects.create(source=subject_source.source, location=Point(
            -103.5, 20.5), recorded_at=now, additional={"speed": 50, "temperature": 15})
        for subject_status in SubjectStatus.objects.all():
            subject_status.additional = {"device_status_properties": [
                {"label": "temp", "units": "c", "value": 15}, {"label": "speed", "units": "km", "value": 50}]}
            subject_status.save()

        request = self._get_request()
        response = SubjectsView.as_view()(request)
        data = list(response.data)

        for item in data:
            item = dict(item)
            if item.get("name") == "Subject test":
                last_location = item.get("last_position")
                device_status_properties = item.get("device_status_properties")
                assert last_location.get("geometry").get(
                    "coordinates", {}) == (-103.6, 20.6)
                assert last_location.get("geometry").get("type", {}) == "Point"
                assert item.get("is_static")
                assert not item.get("tracks_available")
                for device_property in device_status_properties:
                    if device_property.get("label") == "speed":
                        assert device_property.get("default")

    def test_response_stationary_subject_without_location(self, subject_source):
        now = datetime.now(tz=pytz.utc)
        subject = subject_source.subject
        subject.name = "Subject test"
        subject.subject_subtype = SubjectSubType.objects.get(
            display="Camera Trap")
        subject.save()

        Observation.objects.create(source=subject_source.source, location=Point(
            -103.5, 20.5), recorded_at=now, additional={"speed": 50, "temperature": 15})

        request = self._get_request()
        response = SubjectsView.as_view()(request)
        data = list(response.data)

        last_position = data[0].get("last_position")
        assert data[0].get("is_static")
        assert last_position.get("geometry").get("coordinates")[0] == -103.5
        assert last_position.get("geometry").get("coordinates")[1] == 20.5

    def test_response_stationary_subject_without_location_and_observation(self, subject_source):
        subject = subject_source.subject
        subject.name = "Subject test"
        subject.subject_subtype = SubjectSubType.objects.get(
            display="Camera Trap")
        subject.save()

        request = self._get_request()
        response = SubjectsView.as_view()(request)
        data = list(response.data)

        last_position = data[0].get("last_position")
        assert data[0].get("is_static")
        assert last_position is None

    def test_static_sensor_response_with_many_observations(self, subject_source):
        now = datetime.now(tz=pytz.utc)
        subject_source.location = Point(-103.6, 20.6)
        subject_source.save()
        subject = subject_source.subject
        subject.name = "Subject test"
        subject.subject_subtype = SubjectSubType.objects.get(
            display="Camera Trap")
        subject.save()
        source_provider = subject_source.source.provider
        source_provider.transforms = [
            {
                "default": False,
                "dest": "temperature",
                "label": "temp",
                "source": "temperature",
                "units": "c"
            },
            {
                "default": True,
                "dest": "speed",
                "label": "speed",
                "source": "speed",
                "units": "km"
            }
        ]
        source_provider.save()
        Observation.objects.create(source=subject_source.source, location=Point(
            -103.5, 20.5), recorded_at=now, additional={"speed": 50, "temperature": 150})
        Observation.objects.create(source=subject_source.source, location=Point(
            -103.4, 20.4), recorded_at=now - timedelta(minutes=5), additional={"speed": 100, "temperature": 200})
        Observation.objects.create(source=subject_source.source, location=Point(
            -103.3, 20.3), recorded_at=now - timedelta(minutes=10), additional={"speed": 150, "temperature": 250})
        for subject_status in SubjectStatus.objects.all():
            subject_status.additional = {"device_status_properties": [
                {"label": "temp", "units": "c", "value": 15}, {"label": "speed", "units": "km", "value": 50}]}
            subject_status.save()

        request = self._get_request()
        response = SubjectsView.as_view()(request)
        data = list(response.data)

        for item in data:
            item = dict(item)
            if item.get("name") == "Subject test":
                last_location = item.get("last_position")
                device_status_properties = item.get("device_status_properties")
                assert last_location.get("geometry").get(
                    "coordinates", {}) == (-103.6, 20.6)
                assert last_location.get("geometry").get("type", {}) == "Point"
                assert item.get("is_static")
                assert not item.get("tracks_available")
                for device_property in device_status_properties:
                    if device_property.get("label") == "speed":
                        assert device_property.get("default")

    def _get_request(self):
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()
        request = client.factory.get(
            client.api_base + f"/subjects"
        )
        client.force_authenticate(request, client.app_user)
        return request


@pytest.mark.django_db
class TestSubjectsViewFilter:
    position_observations = [
        [-103.66424560546874, 20.619288994719977],
        [-103.61000061035156, 20.699600246050323],
        [-103.53652954101562, 20.680329417909377],
        [-103.4857177734375, 20.609648794045192],
        [-103.47885131835938, 20.732997212795915],
    ]

    @pytest.mark.parametrize(
        "status_subjects_position, total",
        [
            (
                [
                    [-103.66424560546874, 20.619288994719977],
                    [-103.61755371093749, 20.551151842360383],
                    [-103.61000061035156, 20.699600246050323],
                    [-103.4857177734375, 20.609648794045192],
                    [-103.47885131835938, 20.732997212795915],
                ],
                5,
            ),
            (
                [
                    [-103.66424560546874, 20.619288994719977],
                    [-103.61755371093749, 20.551151842360383],
                    [-103.61000061035156, 20.699600246050323],
                    [-103.4857177734375, 20.609648794045192],
                    [-103.49807739257812, 20.44245526026025],
                ],
                4,
            ),
        ],
    )
    @pytest.mark.parametrize(
        "subject_group_with_perms",
        [
            [
                "view_subjectgroup,observations,subjectgroup",
                "view_subject,observations,subject",
            ]
        ],
        indirect=True,
    )
    def test_by_bbox_using_last_known_locations(
        self,
        view_subjects_permission_set,
        five_subject_sources,
        status_subjects_position,
        total,
        subject_group_with_perms,
    ):
        bbox = "-103.71599063163262,20.51126608854284,-103.36639645879019,20.780283984574012"
        for position, source in zip(status_subjects_position, Source.objects.all()):
            Observation.objects.create(
                recorded_at=datetime.now(tz=pytz.UTC),
                source=source,
                location=Point(position),
            )
        subject_group_with_perms.subjects.add(*Subject.objects.all())

        client = HTTPClient()
        client.app_user.permission_sets.add(view_subjects_permission_set)
        client.app_user.permission_sets.add(
            subject_group_with_perms.permission_sets.last())
        request = client.factory.get(
            client.api_base + f"/subjects/?bbox={bbox}&use_lkl=true"
        )
        client.force_authenticate(request, client.app_user)
        response = SubjectsView.as_view()(request)

        assert len(response.data) == total

    @pytest.mark.parametrize(
        "subject_group_with_perms",
        [
            [
                "view_subjectgroup,observations,subjectgroup",
                "view_subject,observations,subject",
            ]
        ],
        indirect=True,
    )
    def test_by_bbox_using_last_known_location_not_include_stationary_subjects(
        self,
        view_subjects_permission_set,
        five_subject_sources,
        settings,
        subject_group_with_perms,
    ):
        settings.SHOW_STATIONARY_SUBJECTS_ON_MAP = False
        first_subject_source = SubjectSource.objects.last()
        first_subject_source.location = Point(-103.6, 20.6)
        first_subject_source.save()
        subject_subtype = SubjectSubType.objects.get(display="Camera Trap")
        first_subject = first_subject_source.subject
        first_subject.subject_subtype = subject_subtype
        first_subject.save()
        for position, source in zip(self.position_observations, Source.objects.all()):
            Observation.objects.create(
                recorded_at=datetime.now(tz=pytz.UTC),
                source=source,
                location=Point(position),
            )
        subject_group_with_perms.subjects.add(*Subject.objects.all())

        bbox = "-103.7384033203125,20.52221649818549,-103.39714050292969,20.801694707706137"
        client = HTTPClient()
        client.app_user.permission_sets.add(
            subject_group_with_perms.permission_sets.last())
        client.app_user.permission_sets.add(view_subjects_permission_set)
        request = client.factory.get(
            client.api_base + f"/subjects/?bbox={bbox}&use_lkl=true"
        )
        client.force_authenticate(request, client.app_user)
        response = SubjectsView.as_view()(request)

        assert len(response.data) == 4
        assert first_subject.id not in [
            item.get("id") for item in response.data]

    @pytest.mark.parametrize(
        "subject_group_with_perms",
        [
            [
                "view_subjectgroup,observations,subjectgroup",
                "view_subject,observations,subject",
            ]
        ],
        indirect=True,
    )
    def test_by_bbox_using_last_known_location_include_stationary_subjects(
        self,
        view_subjects_permission_set,
        five_subject_sources,
        settings,
        subject_group_with_perms,
    ):
        settings.SHOW_STATIONARY_SUBJECTS_ON_MAP = True
        first_subject_source = SubjectSource.objects.last()
        first_subject_source.location = Point(-103.6, 20.6)
        first_subject_source.save()
        subject_subtype = SubjectSubType.objects.get(display="Camera Trap")
        first_subject = first_subject_source.subject
        first_subject.subject_subtype = subject_subtype
        first_subject.save()
        for position, source in zip(self.position_observations, Source.objects.all()):
            Observation.objects.create(
                recorded_at=datetime.now(tz=pytz.UTC),
                source=source,
                location=Point(position),
            )
        subject_group_with_perms.subjects.add(*Subject.objects.all())

        bbox = "-103.7384033203125,20.52221649818549,-103.39714050292969,20.801694707706137"
        client = HTTPClient()
        client.app_user.permission_sets.add(
            subject_group_with_perms.permission_sets.last())
        client.app_user.permission_sets.add(view_subjects_permission_set)
        request = client.factory.get(
            client.api_base + f"/subjects/?bbox={bbox}&use_lkl=true"
        )
        client.force_authenticate(request, client.app_user)
        response = SubjectsView.as_view()(request)

        assert len(response.data) == 5
        assert str(first_subject.id) in [item.get("id")
                                         for item in response.data]

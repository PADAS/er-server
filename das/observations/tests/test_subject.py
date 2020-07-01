import json
from datetime import datetime, timedelta
from unittest.mock import patch

import django.contrib.auth
from django.contrib.gis.geos import Point
from django.urls import reverse
from django.conf import settings
from django.test import override_settings
from django.core.files import File
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.http import QueryDict
from django.contrib.messages.storage.cookie import CookieStorage

import dateutil.parser as dateparser
from pytz import UTC

from core.tests import BaseAPITest
from observations.models import Subject, Observation, GPXTrackFile, SubjectSource
from observations.views import SubjectsView
from observations.admin import GPXAdmin

User = django.contrib.auth.get_user_model()


class SubjectTestCase(BaseAPITest):
    fixtures = [
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
        self.site = AdminSite()
        self.request = RequestFactory()
        self.admin = GPXAdmin(model=GPXTrackFile, admin_site=self.site)


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

    def test_call_subject_api(self):
        url = reverse('subjects-list-view')
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

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

        last_positon_date_subject = json.loads(response.render().content.decode())['data'][0]['last_position_date']
        last_positon_date_subject2 = json.loads(response.render().content.decode())['data'][1]['last_position_date']

        last_positon_date_subject = dateparser.parse(last_positon_date_subject).date().isoformat()
        last_positon_date_subject2 = dateparser.parse(last_positon_date_subject2).date().isoformat()

        t1 = updated_since
        t2 = updated_until

        self.assertEqual({t1, t2}, {last_positon_date_subject, last_positon_date_subject2})

        # Use url above together with bbox param
        # the 'point' lies within this bbox.
        bbox = '-122.49866134971379, 47.40051600277377, -122.225591570732, 47.67666096382156'
        url += '&bbox={}'.format(bbox)
        request = self.factory.get(url)

        self.force_authenticate(request, self.user)
        response = SubjectsView.as_view()(request)
        actual_size = len(response.data)
        expected_size = 2
        self.assertEqual(response.status_code, 200)
        self.assertEqual(actual_size, expected_size)

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
        expiry_date = (datetime.now(tz=UTC) + timedelta(days=5)).date().isoformat()
        mou_datesigned = datetime.now(tz=UTC).date().isoformat()
        additional_data = {
            'notes': 'Testing Notes',
            'expiry': expiry_date,
            'moudatesigned': mou_datesigned,
            'moutype': 'Sample MoU Type',
            'tech': ['iOS'],
            'organization': 'KWS',
        }
        return additional_data

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
        t1 = datetime.now(tz=UTC)
        t2 = datetime.now(tz=UTC) + timedelta(days=3)
        t3 = datetime.now(tz=UTC) + timedelta(days=5)


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

        response_data = json.loads(response.render().content.decode())['data']
        extracted_data = {}
        for o in response_data:
            if o['id'] == str(subject.id):
                extracted_data['subject_last_position'] = o['last_position_date']
            elif o['id'] == str(subject2.id):
                extracted_data['subject2_last_position'] = o['last_position_date']
            elif o['id'] == str(subject3.id):
                extracted_data['subject3_last_position'] = o['last_position_date']

        # subject1 and subject2 are within MOU expiry date.
        subject_last_position = dateparser.parse(extracted_data.get('subject_last_position')).date().isoformat()
        subject2_last_postion = dateparser.parse(extracted_data.get('subject2_last_position')).date().isoformat()
        self.assertEqual(t1.date().isoformat(), subject_last_position)
        self.assertEqual(t2.date().isoformat(), subject2_last_postion)

        # Past MOU expiry date, should not retrieve observation past mou expiry date.
        subject3_last_position = extracted_data.get('subject3_last_position')  # return None
        self.assertNotEqual(t3.date().isoformat(), subject3_last_position)
        self.assertEqual(response.status_code, 200)

    def test_gpx_file_model(self):

        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        data = File(open('./observations/tests/testdata/gpsmap_data.gpx', 'rb'))
        GPXTrackFile.objects.create(data=data, source_assignment=subject_source)

        self.assertEqual(GPXTrackFile.objects.count(), 1)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_gpxfile_upload_on_adminpage(self):

        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        data = File(open('./observations/tests/testdata/gpsmap_data.gpx', 'rb'))

        url = reverse('admin:observations_gpxtrackfile_add')
        url += f'?subject_id={subject.id}'
        request = self.factory.post(url, data={'source_assignment': subject_source.id, '_save': 'Save'})

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

        template_response = self.admin.changeform_view(request)
        successful_msg = 'The GPX data file "./observations/tests/testdata/gpsmap_data.gpx" was successfully imported.'
        gpx_object = GPXTrackFile.objects.all()
        processed_status = gpx_object.values('processed_status')
        self.assertEqual(template_response.status_code, 302)
        self.assertEqual(messages._queued_messages[0].message, successful_msg)
        self.assertEqual(gpx_object.count(), 1)
        self.assertEqual(processed_status[0].get('processed_status'), 'success')

        # This is an example of trackpoint that we expect to be saved in the observation table.
        # <trkpt lat="-2.573374444618821" lon="37.896002875640988">
        #     <ele>1244.769999999999982</ele>
        #     <time>2020-06-06T05:17:26Z</time>
        #  </trkpt>

        trkpoint_lat = '-2.573374444618821'
        trkpoint_lon = '37.896002875640988'
        trkpoint_time = dateparser.parse('2020-06-06T05:17:26Z')

        # trackpoint saved in observation table.
        trkpoint_obs = Observation.objects.filter(recorded_at=trkpoint_time, source__id=subject_source.source_id)
        obs_latitude = trkpoint_obs[0].location.y
        obs_longitude = trkpoint_obs[0].location.x

        self.assertTrue(trkpoint_obs.exists())
        self.assertEqual(float(trkpoint_lat), obs_latitude)
        self.assertEqual(float(trkpoint_lon), obs_longitude)

    def test_gpx_upload_fails(self):
        subject = Subject.objects.get(name='Topsy')
        subject_source = SubjectSource.objects.get(subject=subject)
        data = File(open('./observations/tests/testdata/gpsmap_data.gpx', 'rb'))

        url = reverse('admin:observations_gpxtrackfile_add')
        request = self.factory.post(url, data={'source_assignment': subject_source.id, '_save': 'Save'})
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
        fail_msg = 'The GPX data file "./observations/tests/testdata/gpsmap_data.gpx" failed to be processed: expected string or bytes-like object'
        self.assertEqual(template_response.status_code, 302)
        self.assertEqual(messages._queued_messages[0].message, fail_msg)
        self.assertEqual(processed_status[0].get('processed_status'), 'failure')



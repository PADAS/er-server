import datetime
import json
import os
import shutil
import tempfile
from urllib.parse import urlencode

import pytest
import pytz
from drf_extra_fields.geo_fields import PointField
from psycopg2.extras import DateTimeTZRange

import django.contrib.auth
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.urls import reverse
from django.utils import lorem_ipsum, timezone
from rest_framework import status

from accounts.models import PermissionSet
from activity import views
from activity.models import (PC_DONE, PC_OPEN, Event, EventRelationship,
                             EventType, Patrol, PatrolConfiguration,
                             PatrolNote, PatrolSegment, PatrolType,
                             StateFilters)
from activity.serializers.patrol_serializers import PatrolSerializer
from client_http import HTTPClient
from core.tests import BaseAPITest
from das_server.celery import app
from observations.materialized_views import patrols_view
from observations.models import Source, Subject, SubjectSource

pytestmark = pytest.mark.django_db
User = django.contrib.auth.get_user_model()
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')
STATIC_IMAGE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                 "mapping", 'static',)


def send_task(name, args=(), kwargs={}, **opts):
    task = app.tasks[name]
    # return task.apply(args, kwargs, **opts)
    return task(*args, **kwargs)


class TestPatrol(BaseAPITest):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'test_patroltype')
        call_command('loaddata', 'event_data_model')

        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_superuser(
            'super_user', 'das_super_user@vulcan.com', 'super_user_pass',
            **user_const)
        self.app_user = User.objects.create_user('app-user2', 'app-user2@test.com',
                                                 'app-user2', is_superuser=True,
                                                 is_staff=True, **user_const)
        self.radio_room_user = User.objects.create_user(
            'radio_room_user', 'das_radio_room@vulcan.com',
            'radio_room_user', **user_const)

        self.sample_patrol_id = "b14bc72f-96d6-4248-9fea-7dd0bbc8c196"
        Patrol.objects.create(id=self.sample_patrol_id, title='Test Patrol',
                              objective='Test Objective'),
        Patrol.objects.create(title='Test Patrol 2',
                              objective='Test Objective 2')

        self.default_test_patrol = Patrol.objects.create(
            title='Default Test Patrol')

        PatrolSegment.objects.create(
            patrol_type=PatrolType.objects.first(), patrol_id=self.default_test_patrol.id)

        self.now = datetime.datetime.now(tz=pytz.utc)
        self.start_of_today = self.now.replace(
            hour=0, minute=0, second=0, microsecond=0)
        self.end_of_today = self.start_of_today + \
            datetime.timedelta(hours=23, minutes=59, seconds=59)

        self.sample_patrol_filter = {
            'filter': json.dumps(
                {
                    "date_range": {
                        "lower": self.start_of_today.isoformat(), "upper": self.end_of_today.isoformat()}})}
        self.temporary_folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temporary_folder)
        app.send_task = app.send_task

    def test_get_all_patroltypes(self):
        patrol_types = PatrolType.objects.all()
        url = reverse('patrol-types')

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolTypesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), len(patrol_types))

    def test_get_one_patroltype_by_id(self):
        dog_patrol_id = 'c84bc72f-96d6-4248-9fea-7dd0bbc8c190'
        url = reverse('patrol-type', kwargs={'id': dog_patrol_id})

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolTypeView.as_view()(request, id=dog_patrol_id)
        self.assertEqual(response.status_code, 200)

    def test_get_all_patrols(self):
        request = self.factory.get(self.api_base + '/patrols/')
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200
        assert response.data.get('count') == 4

    def test_get_one_patrol_by_id(self):
        patrol_id = 'b14bc72f-96d6-4248-9fea-7dd0bbc8c196'
        url = reverse('patrol', kwargs={'id': patrol_id})

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolView.as_view()(request, id=patrol_id)
        assert response.status_code == 200

    def test_create_patrolsegment(self):
        subj = Subject.objects.create(
            name='Heritage', subject_subtype_id='elephant')

        patrolsgm_data = dict(scheduled_start='2020-08-05 02:00:00+00',
                              time_range={
                                  "start_time": "2020-08-05 02:00:00+00", "end_time": "2020-08-06 04:00:00+00"},
                              patrol_type='unique_fence_patrol',
                              leader={
                                  "content_type": "observations.subject",
                                  "id": subj.id,
                                  "name": "The Don Galaxy 5",
                                  "subject_type": "wildlife",
                                  "subject_subtype": "elephant",
                                  "additional": {
                                  },
                                  "created_at": "2020-08-05T01:31:42.474284+03:00",
                                  "updated_at": "2020-08-05T01:31:42.474315+03:00",
                                  "is_active": True,
                                  "tracks_available": False,
                                  "image_url": "/static/elephant-black.svg"
                              },
                              start_location={
                                  'latitude': '-122.334', 'longitude': '47.598'},
                              end_location={'latitude': '-124.54',
                                            'longitude': '38.98'},
                              patrol=self.default_test_patrol.id,
                              )
        url = reverse('patrol-segments')
        request = self.factory.post(url, data=patrolsgm_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

    def test_create_patrol_segment_with_invalid_time_range(self):
        segment_data = dict(time_range={
                            "start_time": "2030-08-05 02:00:00+00", "end_time": "2020-08-06 04:00:00+00"})
        url = reverse('patrol-segments')
        request = self.factory.post(url, data=segment_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn('start_time must be an earlier date than the end_time',
                      response.data.get('time_range'))

    def test_create_patrol_patrolsegment_with_no_leader(self):
        patrol_patrolsg = dict(
            priority=0,
            state="open",
            serial_number=69,
            files=[],
            notes=[],
            patrol_segments=[{
                "patrol_type": "routine_patrol",
                "leader": {},
                "scheduled_start": "2020-08-05 02:00:00+00",
                "time_range": {
                    "start_time": "2020-09-24T07:08:16.711000+03:00",
                    "end_time": "2020-09-26T07:08:16.711000+03:00"
                },
                "start_location": {
                    "longitude": -122.3607072,
                    "latitude": 47.681731199999994
                },
                "end_location": {
                    "longitude": -124.3607072,
                    "latitude": 49.681731199999994
                },
            }]
        )

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

    def test_create_patrol_with_all_properties(self):
        subj = Subject.objects.create(
            name='Heritage', subject_subtype_id='elephant')

        patrol_patrolsg = dict(
            objective="Patrol Management",
            priority=0,
            title="Patrol",
            state="open",
            notes=[{'text': 'New Note..'}],
            patrol_segments=[{
                "patrol_type": "routine_patrol",
                "leader": {
                    "content_type": "observations.subject",
                    "id": subj.id,
                    "name": "The Don Galaxy 5",
                    "subject_type": "wildlife",
                    "subject_subtype": "elephant",
                    "additional": {
                    },
                    "created_at": "2020-08-05T01:31:42.474284+03:00",
                    "updated_at": "2020-08-05T01:31:42.474315+03:00",
                    "is_active": True,
                    "tracks_available": False,
                    "image_url": "/static/elephant-black.svg"
                },
                "scheduled_start": "2020-08-05 02:00:00+00",
                "time_range": {
                    "start_time": "2020-09-24T07:08:16.711000+03:00",
                    "end_time": "2020-09-26T07:08:16.711000+03:00"
                },
                "start_location": {
                    "longitude": -122.3607072,
                    "latitude": 47.681731199999994
                },
                "end_location": {
                    "longitude": -124.3607072,
                    "latitude": 49.681731199999994
                },
            }]
        )

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

    def test_add_note(self):
        note_data = {'text': lorem_ipsum.paragraph()}
        request = self.factory.post(self.api_base
                                    + '/patrols/{0}/notes'.format(
                                        self.sample_patrol_id),
                                    note_data)
        self.force_authenticate(request, self.app_user)

        response = views.PatrolNotesView.as_view()(request,
                                                   id=str(self.sample_patrol_id))
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k: response_data[k] for k in note_data.keys()}
        self.assertDictEqual(response_data, note_data)

        request = self.factory.get(self.api_base
                                   + f'/patrols/{self.sample_patrol_id}/notes/{response.data["id"]}')
        self.force_authenticate(request, self.app_user)

        response = views.PatrolNotesView.as_view()(request,
                                                   id=str(
                                                       self.sample_patrol_id),
                                                   note_id=str(response.data['id']))
        self.assertEqual(response.status_code, 200)

    def test_create_patrol_and_upload_document(self):
        patrol_patrolsg = dict(
            objective="Patrol Management",
            priority=0,
            title="Patrol",
            state="open",
            notes=[{'text': 'New Note..'}],
        )

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        assert response.data['notes'][0]['updates']

        my_patrol_id = response.data['id']

        # Create a simple text file and add it to the patrol.
        filename = os.path.join(self.temporary_folder, 'some-test-file.txt')
        with open(filename, 'w') as f:
            f.write('The quick brown fox jumps over the lazy dog.')

        with open(filename, "rb") as f:
            path = '/'.join((self.api_base, 'activity',
                             'patrols', my_patrol_id, 'files'))
            data = {'filecontent.file': f, "ordernum": 1}
            request = self.factory.post(
                path, data, format='multipart')

            self.force_authenticate(request, self.app_user)
            response = views.PatrolFilesView.as_view()(request, id=my_patrol_id)

        path = '/'.join((self.api_base, 'activity', 'patrols', my_patrol_id))
        request = self.factory.get(path)
        self.force_authenticate(request, self.app_user)

        response = views.PatrolView.as_view()(request, id=my_patrol_id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data['files']) == 1)
        assert response.data['files'][0]['updates']

        file_id = response.data['files'][0]['id']
        file_name = "meta-data"  # response.data['files'][0]['id']
        path = '/'.join((self.api_base, 'activity', 'patrols',
                         my_patrol_id, 'files', file_id, file_name))
        request = self.factory.get(path)
        self.force_authenticate(request, self.app_user)

        response = views.PatrolFileView.as_view()(
            request, id=my_patrol_id, filecontent_id=file_id, filename=file_name)
        self.assertEqual(response.status_code, 200)

    def test_create_patrol_and_upload_image(self):
        patrol_patrolsg = dict(
            objective="Patrol Management",
            priority=0,
            title="Patrol",
            state="open",
            notes=[{'text': 'New Note..'}],
        )

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        assert response.data['notes'][0]['updates']

        my_patrol_id = response.data['id']

        with open(os.path.join(STATIC_IMAGE_PATH, "easterisland.jpg"), "rb") as f:
            path = '/'.join((self.api_base, 'activity',
                             'patrols', my_patrol_id, 'files'))
            data = {'filecontent.file': f, "ordernum": 1}
            request = self.factory.post(
                path, data, format='multipart')

            self.force_authenticate(request, self.app_user)
            response = views.PatrolFilesView.as_view()(request, id=my_patrol_id)

        path = '/'.join((self.api_base, 'activity', 'patrols', my_patrol_id))
        request = self.factory.get(path)
        self.force_authenticate(request, self.app_user)

        response = views.PatrolView.as_view()(request, id=my_patrol_id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data['files']) == 1)
        assert response.data['files'][0]['updates']
        self.assertEqual(response.data['files'][0]['updates'][0].get(
            'type'), 'add_patrolfile')

        file_id = response.data['files'][0]['id']
        file_name = "meta-data"  # response.data['files'][0]['id']
        path = '/'.join((self.api_base, 'activity', 'patrols',
                         my_patrol_id, 'files', file_id, file_name))
        request = self.factory.get(path)
        self.force_authenticate(request, self.app_user)

        response = views.PatrolFileView.as_view()(
            request, id=my_patrol_id, filecontent_id=file_id, filename=file_name)
        self.assertEqual(response.status_code, 200)

    def test_history_updates_patrol_notes(self):
        patrol = dict(title='T-Patrol', notes=[{'text': 'New Note ...'}])

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        assert response.data['notes'][0]['updates']
        self.assertEqual(len(response.data['notes'][0]['updates']), 1)
        self.assertEqual(response.data['notes'][0]['updates'][0].get(
            'type'), 'add_patrolnote')

        note_id = response.data['notes'][0]['id']
        update_patrol = dict(
            notes=[{'id': note_id, 'text': 'New Note ... [updated]'}])
        p = Patrol.objects.get(title='T-Patrol')

        url = reverse('patrol', kwargs={'id': p.id})
        request = self.factory.patch(url, data=update_patrol)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=p.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['notes'][0]['updates']), 2)
        self.assertEqual(response.data['notes'][0]
                         ['updates'][0].get('type'), 'update_note')

    def test_history_updates_patrol(self):
        patrol = dict(title='Alpha-01')

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data['updates']), 1)
        self.assertEqual(response.data['updates'][0].get('type'), 'add_patrol')
        self.assertEqual(response.data['updates']
                         [0].get('message'), 'Patrol Added')

        # Update patrol title
        patrol_id = response.data['id']
        updated_patrol = dict(title='Alpha-01 [Updated]')

        url = reverse('patrol', kwargs={'id': patrol_id})
        request = self.factory.patch(url, data=updated_patrol)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=patrol_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['updates']), 2)
        self.assertEqual(response.data['updates']
                         [0].get('type'), 'update_patrol')

    def test_update_all_patrol_patrolsegment_properties(self):
        su = Subject.objects.create(
            name='Horton', subject_subtype_id='elephant')

        patrol_patrolsegment = dict(
            objective="Patrol Management",
            priority=0,
            title="Patrol XYZ",
            state="open",
            notes=[{'text': 'New Note..'}],
            patrol_segments=[{
                "patrol_type": "routine_patrol",
                "leader": {
                    "content_type": "observations.subject",
                    "id": su.id,
                    "name": "The Don Galaxy 5",
                    "subject_type": "wildlife",
                    "subject_subtype": "elephant",
                    "additional": {
                    },
                    "created_at": "2020-08-05T01:31:42.474284+03:00",
                    "updated_at": "2020-08-05T01:31:42.474315+03:00",
                    "is_active": True,
                    "tracks_available": False,
                    "image_url": "/static/elephant-black.svg"
                },
                "scheduled_start": "2020-08-26T01:14:34.196502+03:00",
                "time_range": {
                    "start_time": "2020-09-24T07:08:16.711000+03:00"
                },
                "start_location": {
                    "longitude": -122.3607072,
                    "latitude": 47.681731199999994
                }
            }]
        )

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_patrolsegment)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        notes = response.data.get('notes')
        note_id = notes[0].get('id')

        patrol_sgs = response.data.get('patrol_segments')
        patrol_sgs_id = patrol_sgs[0].get('id')

        # update all properties
        subject = Subject.objects.create(
            name='Fatu', subject_subtype_id='rhino')

        updated_patrol_patrolsg = dict(
            objective="Lorem Ipsum is simply dummy text of the printing and typesetting industry",
            priority=200,
            title="Dog Patrol",
            state="done",
            notes=[{'id': note_id, 'text': 'New Note2..'}],
            patrol_segments=[{
                "id": patrol_sgs_id,
                "patrol_type": "dog_patrol",
                "leader": {
                    "content_type": "observations.subject",
                    "id": subject.id,
                    "name": "IRI2016-3387",
                    "subject_type": "person",
                    "subject_subtype": "ranger",
                    "additional": {},
                    "created_at": "2020-09-16T10:31:07.220892+03:00",
                    "updated_at": "2020-09-16T10:31:07.220909+03:00",
                    "is_active": True,
                    "tracks_available": False,
                    "image_url": "/static/ranger-black.svg"
                },
                "time_range": {
                    "end_time": self.now.isoformat()
                },
                "end_location": {
                    "longitude": 37.41343018527925,
                    "latitude": 0.17796830457972135
                },
            }]
        )
        p = Patrol.objects.get(title='Patrol XYZ')

        url = reverse('patrol', kwargs={'id': p.id})
        request = self.factory.patch(url, data=updated_patrol_patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=p.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data.get('patrol_segments')), 1)
        self.assertEqual(len(response.data.get('notes')), 1)
        self.assertEqual(len(response.data['updates']), 2)
        self.assertEqual(response.data['patrol_segments'][0]['updates'][0].get(
            'type'), 'update_segment')

    def test_update_patrol(self):
        patrol_update_data = dict(
            title="New updated title",
            notes=[{"text": "New first note"}, {"text": "New second Note"}],
            patrol_segments=[{"patrol_type": "dog_patrol"}]
        )
        patrol = Patrol.objects.get(id=self.sample_patrol_id)
        self.assertEqual(len(patrol.notes.all()), 0)
        self.assertEqual(len(patrol.patrol_segments.all()), 0)

        url = reverse('patrol', kwargs={'id': patrol.id})
        request = self.factory.patch(url, data=patrol_update_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=patrol.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data.get('notes')), 2)
        self.assertEqual(len(response.data.get('patrol_segments')), 1)

        patrol_update_data = dict(
            title="New updated title",
            notes=[{"text": "New third note"}, {
                "text": "Update first note", "id": response.data.get('notes')[0]['id']}],
            patrol_segments=[{
                "id": response.data.get('patrol_segments')[0]['id'],
                "patrol_type": "dog_patrol",
                "time_range": {
                    "start_time": "2020-09-24T02:15:54.312000+03:00",
                    "end_time": "2020-09-25T07:00:00.000Z"
                },
            }]
        )

        request = self.factory.patch(url, data=patrol_update_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=patrol.id)
        self.assertEqual(response.status_code, 200)

        subj = Subject.objects.create(
            name='Heritage', subject_subtype_id='elephant')

        patrol_update_data2 = dict(
            priority=0,
            state="open",
            serial_number=69,
            files=[],
            notes=[],
            patrol_segments=[{
                "id": response.data.get('patrol_segments')[0]['id'],
                "patrol_type": "routine_patrol",
                "leader": {
                    "content_type": "observations.subject",
                    "id": subj.id,
                    "name": "The Don Galaxy 5",
                    "subject_type": "wildlife",
                    "subject_subtype": "elephant",
                    "additional": {
                    },
                    "created_at": "2020-08-05T01:31:42.474284+03:00",
                    "updated_at": "2020-08-05T01:31:42.474315+03:00",
                    "is_active": True,
                    "tracks_available": False,
                    "image_url": "/static/elephant-black.svg"
                },
                "scheduled_start": None,
                "time_range": {
                    "start_time": "2020-09-24T07:08:16.711000+03:00",
                    "end_time": None
                },
                "start_location": None,
                "end_location": {
                    "longitude": -122.3607072,
                    "latitude": 47.681731199999994
                },
                "image_url": "https://develop.pamdas.org/static/generic-black.svg",
                "icon_id": "routine_patrol"
            }]
        )

        request = self.factory.patch(url, data=patrol_update_data2)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=patrol.id)

        self.assertEqual(response.status_code, 200)

    def test_update_patrolsegment(self):
        segment_update_data = dict(
            patrol_type="dog_patrol"
        )
        segment = PatrolSegment.objects.first()
        self.assertEqual(segment.patrol_type.display, "Routine Patrol")

        url = reverse('patrol-segment', kwargs={'id': segment.id})
        request = self.factory.patch(url, data=segment_update_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentView.as_view()(request, id=segment.id)

        patrol_type_value = response.data.get('patrol_type')
        patrol_type = PatrolType.objects.get(value=patrol_type_value)
        self.assertEqual(patrol_type.value, segment_update_data.get(
            'patrol_type'))  # dog_patrol
        self.assertEqual(response.status_code, 200)

    def test_update_patrol_with_new_patrolsegment(self):
        patrol = dict(state="open")
        patrolsg = dict(patrol_type="dog_patrol",
                        patrol=self.default_test_patrol.id)

        # Create a patrol with no patrolsegment
        url = reverse('patrols')
        request = self.factory.post(url, data=patrol)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.data.get('patrol_segments')), 0)
        patrol_id = response.data.get('id')

        # create patrolsegment with no patrol
        url = reverse('patrol-segments')
        request = self.factory.post(url, data=patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(str(response.data.get('patrol')),
                         str(self.default_test_patrol.id))

        patrolsg_id = response.data.get('id')

        # update patrol with new patrolsegment
        data = {"patrol_segments": [{"id": patrolsg_id}]}
        url = reverse('patrol', kwargs={'id': patrol_id})
        request = self.factory.patch(url, data=data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=patrol_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data.get('patrol_segments')), 1)

    def test_get_all_patrolsegments(self):
        url = reverse('patrol-segments')
        request = self.factory.get(url)
        patrolsgm = PatrolSegment.objects.all().count()
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('count'), patrolsgm)

    def test_get_one_patrolsegment_by_id(self):
        patrolsgm = PatrolSegment.objects.first()
        patrolsgm_id = str(patrolsgm.id)
        url = reverse('patrol-segment', kwargs={'id': patrolsgm_id})

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolsegmentView.as_view()(request, id=patrolsgm_id)
        self.assertEqual(response.status_code, 200)

    def test_patrol_filter(self):
        start = self.start_of_today + datetime.timedelta(hours=8)  # 8am
        end = self.start_of_today + datetime.timedelta(hours=9)  # 9 am
        patrol_data = dict(
            title='Test Patrol',
            patrol_segments=[
                {'time_range': {"start_time": start.isoformat(), "end_time": end.isoformat()}}]
        )
        self._create_patrol(patrol_data)
        response = self._filter_patrol(
            self.sample_patrol_filter)  # today's filter
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data.get('results')[
                         0].get('title'), patrol_data.get('title'))

        # filter by only lower
        filter_query = {'filter': json.dumps(
            {"date_range": {"lower": self.start_of_today.isoformat()}})}
        response = self._filter_patrol(filter_query)
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data.get('results')[
                         0].get('title'), patrol_data.get('title'))

        # filter by only upper
        filter_query = {'filter': json.dumps(
            {"date_range": {"upper": self.start_of_today.isoformat()}})}
        response = self._filter_patrol(filter_query)
        self.assertEqual(response.data.get('count'), 0)

    def test_patrol_filter_with_patrols_overlap_daterange_param(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        date_range = {"lower": self.start_of_today.isoformat(
        ), "upper": self.end_of_today.isoformat()}
        date_range_filter = {'filter': json.dumps(
            {"date_range": date_range, "patrols_overlap_daterange": False})}

        start = self.start_of_today + datetime.timedelta(hours=8)  # 8am
        end = self.start_of_today + datetime.timedelta(hours=11)  # 9 am
        patrol_data = dict(
            title='New Patrol',
            patrol_segments=[
                {'time_range': {"start_time": start.isoformat(), "end_time": end.isoformat()}}],
        )
        self._create_patrol(patrol_data)
        response = self._filter_patrol(date_range_filter)  # today's filter

        # patrol's start time within given range
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data.get('results')[
                         0].get('title'), patrol_data.get('title'))

        date_range['lower'] = (self.start_of_today +
                               datetime.timedelta(hours=10)).isoformat()
        new_filter = {'filter': json.dumps(
            {"date_range": date_range, "patrols_overlap_daterange": False})}
        response = self._filter_patrol(new_filter)  # today's filter

        # Patrol start time not within range
        self.assertEqual(response.data.get('count'), 0)

        new_filter = {'filter': json.dumps({"date_range": date_range})}
        response = self._filter_patrol(new_filter)  # today's filter

        # Patrol start to end overlaps
        self.assertEqual(response.data.get('count'), 1)

        # Filter with midnight time in upper bound
        date_range['lower'] = (self.start_of_today -
                               datetime.timedelta(hours=10)).isoformat()
        date_range['upper'] = (self.start_of_today).isoformat()

        patrol = response.data.get('results')[0]
        segment_id = patrol.get('patrol_segments')[0].get('id')

        # update the patrol start time to 00:00
        updated_time_range = DateTimeTZRange(
            lower=self.start_of_today, upper=self.end_of_today)

        PatrolSegment.objects.filter(id=segment_id).update(
            time_range=updated_time_range)
        new_filter = {'filter': json.dumps({"date_range": date_range})}
        response = self._filter_patrol(new_filter)

        # Patrol overlapping timerange
        self.assertEqual(response.data.get('count'), 1)

        new_filter = {'filter': json.dumps(
            {"date_range": date_range, "patrols_overlap_daterange": False})}
        response = self._filter_patrol(new_filter)

        # Skipping patrol ending at 00:00
        self.assertEqual(response.data.get('count'), 0)

    def test_patrol_filter_only_scheduled_start_given(self):
        start = self.start_of_today + \
            datetime.timedelta(days=5)  # 5 days later
        patrol_data = dict(
            title='Scheduled Patrol',
            patrol_segments=[
                {'scheduled_start': start.isoformat()}]
        )
        self._create_patrol(patrol_data)
        response = self._filter_patrol(
            self.sample_patrol_filter)  # today's filter
        self.assertEqual(response.data.get('count'), 0)

        lower = self.start_of_today + \
            datetime.timedelta(days=3)  # 3 days from now
        upper = self.start_of_today + \
            datetime.timedelta(days=7)  # 7 days from now

        patrol_filter = {'filter': json.dumps(
            {"date_range": {"lower": lower.isoformat(), "upper": upper.isoformat()}})}
        response = self._filter_patrol(patrol_filter)
        self.assertEqual(response.data.get('count'), 1)

    def test_patrol_filter_by_state(self):
        start = self.start_of_today + \
            datetime.timedelta(days=5)  # 5 days later
        scheduled_patrol = dict(
            title='Scheduled Patrol', patrol_segments=[{'scheduled_start': start.isoformat()}])
        active_patrol = dict(
            title='Active Patrol',
            patrol_segments=[{'time_range': {"start_time": self.start_of_today.isoformat()}}])
        done_patrol = dict(title='Overdue Patrol', state='done')
        overdue_patrol = dict(
            title='Overdue Patrol',
            patrol_segments=[{'scheduled_start': (self.now - datetime.timedelta(minutes=45)).isoformat()}])
        cancelled_patrol = dict(title='Cancelled Patrol', state='cancelled')
        Patrol.objects.all().delete()

        for patrol in [scheduled_patrol, active_patrol, done_patrol, overdue_patrol, cancelled_patrol]:
            self._create_patrol(patrol)

        for st_filter in [e.value for e in StateFilters]:
            filter_param = {"status": st_filter}
            response = self._filter_patrol(filter_param)
            self.assertEqual(response.data.get('count'), 1)

        url = reverse('patrols') + \
            f'?status=scheduled&status=active&status=done&status=cancelled'
        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.data.get('count'), 4)

    def test_patrol_filter_with_null_end_time(self):
        start = self.start_of_today - datetime.timedelta(days=3)  # 3 days ago
        patrol_data = dict(
            title='Test Patrol',
            patrol_segments=[{'time_range': {"start_time": start.isoformat()}}]
        )
        self._create_patrol(patrol_data)
        response = self._filter_patrol(self.sample_patrol_filter)

        # patrol is still current since it doesnt have an end date
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data.get('results')[
                         0].get('title'), patrol_data.get('title'))

    def test_patrol_filter_with_past_end_time_but_patrol_not_completed(self):
        start = self.start_of_today - datetime.timedelta(days=2, hours=10)
        scheduled_end = self.start_of_today - \
            datetime.timedelta(days=2, hours=5)
        patrol_data = dict(
            title='Test Patrol',
            patrol_segments=[
                {'time_range': {"start_time": start.isoformat()},
                 'scheduled_end': scheduled_end.isoformat()}]
        )
        self._create_patrol(patrol_data)
        response = self._filter_patrol(self.sample_patrol_filter)

        # patrol is still displayed as current since its not marked as done or
        # complete
        self.assertEqual(response.data.get('count'), 1)
        result = response.data.get('results')[0]
        self.assertEqual(result.get('title'), patrol_data.get('title'))

        # update the patrol to completed
        patrol_id = result.get('id')
        url = reverse('patrol', kwargs={'id': patrol_id})
        patrol_update_data = dict(
            state="done",
            patrol_segments=[{
                "id": result.get('patrol_segments')[0]['id'],
                "time_range": {"end_time": scheduled_end.isoformat()}
            }]
        )
        request = self.factory.patch(url, data=patrol_update_data)
        self.force_authenticate(request, self.app_user)
        views.PatrolView.as_view()(request, id=patrol_id)
        response = self._filter_patrol(self.sample_patrol_filter)

        # patrol nolonger returned, completed
        self.assertEqual(response.data.get('count'), 0)

    def test_patrol_filter_cancelled_current_patrols(self):
        start = self.start_of_today + datetime.timedelta(hours=8)  # 8am
        patrol_data = dict(
            title='Patrol To be cancelled',
            patrol_segments=[{'time_range': {"start_time": start.isoformat()}}]
        )
        self._create_patrol(patrol_data)

        # update patrol, cancel
        patrol = Patrol.objects.get(title=patrol_data['title'])
        url = reverse('patrol', kwargs={'id': patrol.id})
        patrol_update_data = dict(state="cancelled")

        self.assertIsNone(patrol.patrol_segments.first().time_range.upper)
        request = self.factory.patch(url, data=patrol_update_data)
        self.force_authenticate(request, self.app_user)
        views.PatrolView.as_view()(request, id=patrol.id)

        response = self._filter_patrol(
            self.sample_patrol_filter)  # current patrols filter
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data.get('results')[
                         0].get('title'), patrol_data.get('title'))

    def _filter_patrol(self, filter_query):
        url = reverse('patrols')
        url += f'?{urlencode(filter_query)}'
        request = self.factory.get(self.api_base + url)
        self.force_authenticate(request, self.user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        return response

    def _create_patrol(self, patrol_data):
        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        return response.data

    def test_sort_patrols(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        now = datetime.datetime.now(tz=pytz.utc)

        active_patrol = dict(title='patrol_active',
                             patrol_segments=[{'time_range': {'start_time': now.isoformat()}}])

        overdue_patrol = dict(title='patrol_overdue',
                              patrol_segments=[{'scheduled_start': (now - datetime.timedelta(hours=2)).isoformat()}])

        cancelled_patrol = dict(title='patrol_cancelled', state='cancelled')

        done_patrol = dict(title='patrol_done', state='done')

        [self._create_patrol(patrol) for patrol in [
            done_patrol, active_patrol,  cancelled_patrol, overdue_patrol]]

        request = self.factory.get(self.api_base + '/patrols/')
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200

        # expected order
        expected = ['patrol_overdue', 'patrol_active',
                    'patrol_done', 'patrol_cancelled']
        results = [p.get('title') for p in response.data['results']]

        for exp, actual in zip(expected, results):
            self.assertEqual(exp, actual)

    def test_sort_patrol_alphabetically(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()

        patro1 = dict(title='C patrol', state='done')
        patrol2 = dict(title='B patrol', state='done')
        patrol3 = dict(title='A patrol', state='done')

        [self._create_patrol(patrol) for patrol in [patro1, patrol2, patrol3]]

        request = self.factory.get(self.api_base + '/patrols/')
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200

        expected = ['A patrol', 'B patrol', 'C patrol']
        results = [p.get('title') for p in response.data['results']]

        for exp, actual in zip(expected, results):
            self.assertEqual(exp, actual)

    def test_overdue_readytostart(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()

        ahead = datetime.datetime.now(
            tz=pytz.utc) + datetime.timedelta(minutes=28)
        lookback = datetime.datetime.now(
            tz=pytz.utc) - datetime.timedelta(minutes=28)

        overdue_patrol = dict(title='overdue',
                              patrol_segments=[{'scheduled_start': lookback.isoformat()}])

        readytostart = dict(title='readytostart',
                            patrol_segments=[{'scheduled_start': ahead.isoformat()}])

        [self._create_patrol(patrol)
         for patrol in [readytostart, overdue_patrol]]

        request = self.factory.get(self.api_base + '/patrols/')
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200

        expected = ['overdue', 'readytostart']
        results = [p.get('title') for p in response.data['results']]

        for exp, actual in zip(expected, results):
            self.assertEqual(exp, actual)

    def test_sort_overdue_readytostart_active(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()

        now = datetime.datetime.now(tz=pytz.utc)
        ahead = now + datetime.timedelta(minutes=28)
        lookback = now - datetime.timedelta(minutes=28)

        overdue_patrol = dict(title='overdue',
                              patrol_segments=[{'scheduled_start': lookback.isoformat()}])

        readytostart = dict(title='readytostart',
                            patrol_segments=[{'scheduled_start': ahead.isoformat()}])

        active_patrol = dict(title='active',
                             patrol_segments=[{'time_range': {'start_time': now.isoformat()}}])

        [self._create_patrol(patrol) for patrol in [
            active_patrol, readytostart, overdue_patrol]]

        request = self.factory.get(self.api_base + '/patrols/')
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200

        expected = ['overdue', 'readytostart', 'active']
        results = [p.get('title') for p in response.data['results']]

        for exp, actual in zip(expected, results):
            self.assertEqual(exp, actual)

    def test_sort_by_state(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()

        now = datetime.datetime.now(tz=pytz.utc)

        lookback = now - datetime.timedelta(minutes=48)
        lookback2 = now - datetime.timedelta(minutes=35)

        future_scheduled = lookback + datetime.timedelta(days=20)

        now = datetime.datetime.now(tz=pytz.utc)
        active_control = now - datetime.timedelta(days=2)

        ahead = now + datetime.timedelta(minutes=28)
        ahead_control = ahead - datetime.timedelta(minutes=20)

        overdue_patrol = dict(title='overdue patrol',
                              patrol_segments=[{'scheduled_start': lookback.isoformat()}])
        overdue_patrol2 = dict(title='my overdue patrol',
                               patrol_segments=[{'scheduled_start': lookback2.isoformat()}])
        future_patrol = dict(title='future patrol',
                             patrol_segments=[{'scheduled_start': future_scheduled.isoformat()}])

        cancel_readytostart = dict(title='cancelled readytostart', state="cancelled",
                                   patrol_segments=[{'scheduled_start': ahead.isoformat()}])
        cancel_readytostart2 = dict(title='cancelled readytostart_control', state="cancelled",
                                    patrol_segments=[{'scheduled_start': ahead_control.isoformat()}])

        active_patrol0 = dict(title='active B',
                              patrol_segments=[{'time_range': {'start_time': now.isoformat()},
                                                'scheduled_start': lookback.isoformat()}])

        active_patrol = dict(title='active',
                             patrol_segments=[{'time_range': {'start_time': now.isoformat()}}])

        active_patrol2 = dict(title='active_control',
                              patrol_segments=[{'time_range': {'start_time': active_control.isoformat()}}])

        done_patrol = dict(title='done A', state="done",
                           patrol_segments=[{'time_range': {'start_time': now.isoformat()}}])
        done_patrol2 = dict(title='done B', state="done",
                            patrol_segments=[{'time_range': {'start_time': active_control.isoformat()}}])

        done_patrol3 = dict(state="done",
                            patrol_segments=[{'time_range': {'start_time': active_control.isoformat()},
                                              "patrol_type": "routine_patrol"}])

        [self._create_patrol(patrol) for patrol in [done_patrol3, done_patrol2, cancel_readytostart, future_patrol, overdue_patrol,
                                                    overdue_patrol2, active_patrol0, active_patrol, done_patrol,  cancel_readytostart2, active_patrol2]]

        request = self.factory.get(self.api_base + '/patrols/')
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200

        expected = ['my overdue patrol', 'overdue patrol', 'future patrol', 'active',  'active B', 'active_control',
                    'done A', 'done B', 'routine_patrol', 'cancelled readytostart', 'cancelled readytostart_control']
        results = [p.get('title') for p in response.data['results']]
        results[8] = response.data['results'][8]['patrol_segments'][0]['patrol_type']

        for exp, actual in zip(expected, results):
            self.assertEqual(exp, actual)

    def test_sort_overdue_readytostart_only_alphabetically(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        subj = Subject.objects.create(
            name='Heritage', subject_subtype_id='elephant')

        now = datetime.datetime.now(tz=pytz.utc)

        lookback = now - datetime.timedelta(minutes=35)
        second_lookback = now - datetime.timedelta(minutes=40)
        third_lookback = now - datetime.timedelta(minutes=50)

        first_scheduled = now + datetime.timedelta(minutes=10)
        second_scheduled = now + datetime.timedelta(hours=6)
        third_scheduled = now + datetime.timedelta(days=1)

        overdue_patrol = dict(title='C overdue',
                              patrol_segments=[{'scheduled_start': lookback.isoformat()}])
        overdue_patrol2 = dict(title='B overdue',
                               patrol_segments=[{'scheduled_start': second_lookback.isoformat()}])
        overdue_patrol3 = dict(title='A overdue',
                               patrol_segments=[{'scheduled_start': third_lookback.isoformat()}])

        overdue_patrol4 = dict(patrol_segments=[{'scheduled_start': third_lookback.isoformat(),
                                                 "patrol_type": "dog_patrol",
                                                 "leader": {
                                                     "content_type": "observations.subject",
                                                     "id": subj.id,
                                                     "name": "The Don Galaxy 5",
                                                     "subject_type": "wildlife",
                                                     "subject_subtype": "elephant",
                                                     "additional": {
                                                     },
                                                     "created_at": "2020-08-05T01:31:42.474284+03:00",
                                                     "updated_at": "2020-08-05T01:31:42.474315+03:00",
                                                     "is_active": True,
                                                     "tracks_available": False,
                                                     "image_url": "/static/elephant-black.svg"

        }}])
        ready_patrol = dict(title='C readytostart',
                            patrol_segments=[{'scheduled_start': first_scheduled.isoformat()}])
        ready_patrol2 = dict(title='B readytostart',
                             patrol_segments=[{'scheduled_start': second_scheduled.isoformat()}])
        ready_patrol3 = dict(title='A readytostart',
                             patrol_segments=[{'scheduled_start': third_scheduled.isoformat()}])

        ready_patrol4 = dict(patrol_segments=[{'scheduled_start': third_scheduled.isoformat(),
                                               "patrol_type": "dog_patrol"}])

        [self._create_patrol(patrol) for patrol in [ready_patrol4, ready_patrol, ready_patrol2,
                                                    ready_patrol3, overdue_patrol4, overdue_patrol, overdue_patrol2, overdue_patrol3]]

        request = self.factory.get(self.api_base + '/patrols/')
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200

        expected = ['A overdue', 'B overdue', 'C overdue', 'Heritage',
                    'A readytostart', 'B readytostart', 'C readytostart', 'dog_patrol']
        results = [p.get('title') for p in response.data['results']]
        results[3] = response.data['results'][3]['patrol_segments'][0]['leader']['name']
        results[7] = response.data['results'][7]['patrol_segments'][0]['patrol_type']
        for exp, actual in zip(expected, results):
            self.assertEqual(exp, actual)

    def test_locations_in_patrolsegment(self):
        # test that start_location or end_location return a float/numeric
        patrolsgm_data = dict(patrol_type='unique_fence_patrol',
                              start_location={
                                  'latitude': '-122.334', 'longitude': '47.598'},
                              end_location={'latitude': '-124.54',
                                            'longitude': '38.98'},
                              patrol=self.default_test_patrol.id,
                              )
        url = reverse('patrol-segments')
        request = self.factory.post(url, data=patrolsgm_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(isinstance(response.data.get(
            'start_location').get('latitude'), float))
        self.assertTrue(isinstance(response.data.get(
            'end_location').get('latitude'), float))

    def test_add_report_to_patrol_segment(self):
        print('default test patrol id: %s' % (self.default_test_patrol.id,))
        patrol_segment = dict(
            patrol_type="routine_patrol",
            patrol=str(self.default_test_patrol.id),
        )

        print('Posting patrol_segment: %s' % (patrol_segment,))
        url = reverse('patrol-segments')
        request = self.factory.post(url, data=patrol_segment)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        self.assertEqual(0, len(response.data.get('events')))

        segment_id = response.data.get('id')
        et = EventType.objects.first()

        # Create an event and view segment
        event_data = dict(
            title="Test Event",
            event_type=et.value,
            location={
                "longitude": -122.3607072,
                "latitude": 47.681731199999994
            },
            patrol_segments=[segment_id]

        )
        events_url = reverse('events')
        request = self.factory.post(events_url, event_data)
        self.force_authenticate(request, self.user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(str(segment_id) in str(
            response.data.get('patrol_segments')))

        location = PointField().to_internal_value({
            "longitude": -122.3607072,
            "latitude": 47.681731199999994
        })
        collection_et = EventType.objects.get_by_value('incident_collection')
        event_collection = Event.objects.create(
            title="incident_collection_event", event_type=collection_et)
        event_child = Event.objects.create(
            title="Event_A", event_type=et, location=location)
        EventRelationship.objects.add_relationship(
            event_collection, event_child, 'contains')

        PatrolSegment.objects.get(id=segment_id).events.add(event_collection)

        # View reports from segment
        url = reverse('patrol-segment', kwargs={'id': segment_id})
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolsegmentView.as_view()(request, id=segment_id)
        self.assertEqual(2, len(response.data.get('events')))
        self.assertEqual(response.data.get('updates')[
                         0].get('message'), 'Report Added')
        self.assertEqual(response.data.get('updates')[
                         1].get('message'), 'Incident Collection Added')

    def test_add_patrol_segment_to_report(self):
        patrol = Patrol.objects.create(title="My Glorius Patrol")

        patrol_segment = dict(
            patrol_type="routine_patrol",
            patrol=patrol.id
        )

        url = reverse('patrol-segments')
        request = self.factory.post(url, data=patrol_segment)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        self.assertEqual(0, len(response.data.get('events')))

        segment_id = response.data.get('id')
        et = EventType.objects.first()

        # Create an event
        event_data = dict(
            title="Test Event",
            event_type=et.value,
        )
        events_url = reverse('events')
        request = self.factory.post(events_url, event_data)
        self.force_authenticate(request, self.user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        event_id = response.data.get('id')

        event_data = dict(
            patrol_segments=[segment_id, ]
        )

        events_url = reverse('event-view', kwargs={'id': event_id})
        request = self.factory.patch(events_url, event_data)
        self.force_authenticate(request, self.user)

        response = views.EventView.as_view()(request, id=event_id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(str(segment_id) in str(
            response.data.get('patrol_segments')))

        # View reports from segment
        url = reverse('patrol-segment', kwargs={'id': segment_id})
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolsegmentView.as_view()(request, id=segment_id)
        self.assertEqual(1, len(response.data.get('events')))
        self.assertEqual(response.data.get('updates')[
                         0].get('message'), 'Report Added')

        url = reverse('patrol', kwargs={'id': patrol.id})
        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolView.as_view()(request, id=patrol.id)
        self.assertEqual(1, len(response.data.get(
            'patrol_segments')[0].get('events')))

    def test_patrolsegment_history_update_endtime(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        now = datetime.datetime.now(tz=pytz.utc)

        patrol_patrolsegment = dict(
            priority=0,
            title="Patrol XYZ",
            patrol_segments=[{
                "patrol_type": "routine_patrol",
                "scheduled_start": "2020-08-26T01:14:34.196502+03:00",
                "time_range": {
                    "start_time": "2020-09-24T07:08:16.711000+03:00",
                    "end_time": "2020-09-26T07:08:16.711000+03:00"
                }
            }]
        )

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_patrolsegment)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        patrol_sgs = response.data.get('patrol_segments')
        patrol_sgs_id = patrol_sgs[0].get('id')

        updated_patrol_patrolsg = dict(
            priority=200,
            patrol_segments=[{
                "id": patrol_sgs_id,
                "patrol_type": "dog_patrol",
                "scheduled_start": "2020-09-26T01:14:34.196502+03:00",
                "time_range": {
                    "start_time": "2020-09-24T07:08:16.711000+03:00",
                    "end_time": "2020-09-29T07:08:16.711000+03:00"
                }
            }]
        )

        p = Patrol.objects.get(title='Patrol XYZ')
        url = reverse('patrol', kwargs={'id': p.id})
        request = self.factory.patch(url, data=updated_patrol_patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=p.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            'End Time' in response.data['patrol_segments'][0]['updates'][0].get('message'))

    def test_patrolsegment_history_autoendtime(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        now = datetime.datetime.now(tz=pytz.utc)

        patrol_patrolsegment = dict(
            priority=0,
            title="Patrol XYZ",
            patrol_segments=[{
                "patrol_type": "routine_patrol",
                "time_range": {
                    "start_time": "2020-09-24T07:08:16.711000+03:00"
                }
            }]
        )

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_patrolsegment)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        patrol_sgs = response.data.get('patrol_segments')
        patrol_sgs_id = patrol_sgs[0].get('id')

        updated_patrol_patrolsg = dict(
            priority=200,
            patrol_segments=[{
                "id": patrol_sgs_id,
                "time_range": {
                    "end_time": self.end_of_today
                }
            }]
        )

        p = Patrol.objects.get(title='Patrol XYZ')
        url = reverse('patrol', kwargs={'id': p.id})
        request = self.factory.patch(url, data=updated_patrol_patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=p.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            'Auto-End Time' in response.data['patrol_segments'][0]['updates'][0].get('message'))

        updated_patrol_patrolsg = dict(
            priority=200,
            patrol_segments=[{
                "id": patrol_sgs_id,
                "scheduled_start": "2020-09-26T01:14:34.196502+03:00",
                "time_range": {
                    "end_time": "2020-09-29T07:08:16.711000+03:00"
                }
            }]
        )

        p = Patrol.objects.get(title='Patrol XYZ')
        url = reverse('patrol', kwargs={'id': p.id})
        request = self.factory.patch(url, data=updated_patrol_patrolsg)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=p.id)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            'End Time' in response.data['patrol_segments'][0]['updates'][0].get('message'))

    def test_maintain_patrol_state(self):
        # Monkey-patch send_task to execute task by blocking; because task_always_eager has no effect on send_task.
        app.send_task = send_task
        from activity.tasks import maintain_patrol_state

        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        set_time = datetime.datetime.now(
            tz=pytz.utc) - datetime.timedelta(minutes=1)

        patrol = dict(title='alpha', patrol_segments=[
                      {"time_range": {"end_time": set_time.isoformat()}}])
        self._create_patrol(patrol)
        maintain_patrol_state()
        p = Patrol.objects.get(title='alpha')
        self.assertEqual(p.state, 'done')

        url = reverse('patrol', kwargs={'id': p.id})
        request = self.factory.get(url)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=p.id)
        self.assertEqual(response.status_code, 200)
        updates = response.data['updates']
        auto_done_message = [
            u for u in updates if "State is done" in u['message']][0]

        assert auto_done_message['user']['first_name'] == 'Auto-end'

        # should not update cancelled patrol
        patrol = dict(title='alpha2',  state='cancelled', patrol_segments=[
                      {"time_range": {"end_time": set_time.isoformat()}}])
        self._create_patrol(patrol)
        maintain_patrol_state()
        self.assertEqual(Patrol.objects.get(title='alpha2').state, 'cancelled')

    def test_update_status(self):
        # server should transition from done to open if the end_time is cleared
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        set_time = datetime.datetime.now(
            tz=pytz.utc) - datetime.timedelta(minutes=1)

        patrol_data = dict(
            title="Sierra-09", state="done",
            patrol_segments=[
                {"time_range": {"end_time": set_time.isoformat()}}]
        )
        self._create_patrol(patrol_data)
        patrol = Patrol.objects.get(title='Sierra-09')
        self.assertEqual(patrol.state, 'done')

        patrol_update_data = dict(
            patrol_segments=[{
                "id": str(patrol.patrol_segments.first().id),
                "time_range": {
                    "start_time": "2020-09-24T02:15:54.312000+03:00",
                },
            }]
        )

        url = reverse('patrol', kwargs={'id': patrol.id})
        request = self.factory.patch(url, data=patrol_update_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=patrol.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('state'), 'open')

    def test_dont_update_cancelled_status(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        set_time = datetime.datetime.now(
            tz=pytz.utc) - datetime.timedelta(minutes=1)

        patrol_data = dict(
            title="Sierra-09", state="cancelled",
            patrol_segments=[
                {"time_range": {"end_time": set_time.isoformat()}}]
        )
        self._create_patrol(patrol_data)
        patrol = Patrol.objects.get(title='Sierra-09')
        self.assertEqual(patrol.state, 'cancelled')

        patrol_update_data = dict(
            patrol_segments=[{
                "id": str(patrol.patrol_segments.first().id),
                "time_range": {
                    "start_time": "2020-09-24T02:15:54.312000+03:00",
                },
            }]
        )

        url = reverse('patrol', kwargs={'id': patrol.id})
        request = self.factory.patch(url, data=patrol_update_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolView.as_view()(request, id=patrol.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('state'), 'cancelled')

    def test_no_patrol_permission(self):
        url = reverse('patrols')
        request = self.factory.get(url)
        self.force_authenticate(request, self.radio_room_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 403

        # Patrol-Types.
        url = reverse('patrol-types')
        request = self.factory.get(url)
        self.force_authenticate(request, self.radio_room_user)
        response = views.PatrolTypesView.as_view()(request)
        assert response.status_code == 403

    def test_view_patrol_permission_can_view_patroltype(self):
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        self.radio_room_user.permission_sets.add(view_patrol_permissionset)
        client = Client()
        client.force_login(self.radio_room_user)
        response = client.get(reverse("patrol-types"))
        assert response.status_code == 200
        assert [pt for pt in response.data if pt['value'] == 'routine_patrol']

    def test_view_patrol_permission_no_subject_perm(self):
        PatrolSegment.objects.all().delete()
        Patrol.objects.all().delete()
        su = Subject.objects.create(
            name='Horton', subject_subtype_id='elephant')

        patrol_patrolsegment = dict(
            objective="Patrol Management",
            priority=0,
            title="Patrol",
            state="open",
            notes=[{'text': 'New Note..'}],
            patrol_segments=[{
                "patrol_type": "dog_patrol",
                "leader": {
                    "content_type": "observations.subject",
                    "id": su.id,
                    "name": "Radio-5",
                    "subject_type": "wildlife",
                    "subject_subtype": "elephant",
                    "additional": {
                    },
                    "created_at": "2020-08-05T01:31:42.474284+03:00",
                    "updated_at": "2020-08-05T01:31:42.474315+03:00",
                    "is_active": True,
                    "tracks_available": False,
                    "image_url": "/static/elephant-black.svg"
                },
                "scheduled_start": "2020-08-26T01:14:34.196502+03:00",
                "time_range": {
                    "start_time": "2020-09-24T07:08:16.711000+03:00"
                },
                "start_location": {
                    "longitude": -122.3607072,
                    "latitude": 47.681731199999994
                }
            }]
        )

        url = reverse('patrols')
        request = self.factory.post(url, data=patrol_patrolsegment)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        # give only view patrol permission to radio_room_user.
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        self.radio_room_user.permission_sets.add(view_patrol_permissionset)
        url = reverse('patrols')
        request = self.factory.get(url)
        self.force_authenticate(request, self.radio_room_user)
        response = views.PatrolsView.as_view()(request)
        assert response.status_code == 200
        assert response.data['results'] == []


def test_patrol_admin_page(django_assert_max_num_queries, client):
    user_const = dict(last_name='last', first_name='first')
    user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                    is_staff=True, **user_const)

    client.force_login(user)
    url = reverse('admin:activity_patrol_changelist')
    with django_assert_max_num_queries(15):
        client.get(url)


def test_patrols(django_assert_max_num_queries, client):
    user_const = dict(last_name='last', first_name='first')
    user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                    is_staff=True, **user_const)
    client.force_login(user)
    url = reverse('patrols')
    with django_assert_max_num_queries(35):
        client.get(url)


def test_patrolsegments(django_assert_max_num_queries, client):
    user_const = dict(last_name='last', first_name='first')
    user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                    is_staff=True, **user_const)
    client.force_login(user)
    url = reverse('patrols')
    with django_assert_max_num_queries(35):
        client.get(url)


def test_patrols_materialized_view(django_assert_max_num_queries, client):

    user_const = dict(last_name='last', first_name='first')
    user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                    is_staff=True, **user_const)

    leader = Subject.objects.create(
        name='Aname', subject_subtype_id='ranger')

    patrol_start_at = datetime.datetime.now(
        tz=datetime.timezone.utc) - datetime.timedelta(days=30)
    patrol_end_at = patrol_start_at + datetime.timedelta(days=14)

    patrol = Patrol.objects.create(title='Standard patrol')

    PatrolSegment.objects.create(patrol=patrol,
                                 scheduled_start=patrol_start_at,
                                 time_range=DateTimeTZRange(
                                     patrol_start_at, patrol_end_at),
                                 leader=leader)

    sources = [
        {'model_name': 'Model A', 'manufacturer_id': 'model-a-1', },
        {'model_name': 'Model B', 'manufacturer_id': 'model-b-1', },
    ]

    # Arbitrary ranges that will overlap with the patrol range.
    range_overlaps = [
        ((patrol_start_at - datetime.timedelta(days=5),
         patrol_start_at + datetime.timedelta(days=4))),
        ((patrol_start_at + datetime.timedelta(days=4),
         patrol_start_at + datetime.timedelta(days=21)))
    ]

    for i, s in enumerate(sources):
        src = Source.objects.create(**s)
        SubjectSource.objects.create(**{
            'subject': leader,
            'source': src,
            'assigned_range': range_overlaps[i]
        })

    patrols_view.drop_view()
    patrols_view.refresh_view()

    cursor = connection.cursor().cursor

    cursor.execute('select count(*) from patrols_view;')
    cursor.fetchall()
    # assert data[0] == (1,)


@pytest.mark.django_db
class TestPatrolFilter:
    def test_filter_in_serial_number(self, five_patrols):
        self._arrange_patrol_serial_number_sql()

        filter = {"patrols_overlap_daterange": True, "text": "1000"}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["title", "Title", "TITLE"])
    def test_filter_by_title(self, five_patrols, text):
        patrol = Patrol.objects.first()
        patrol.title = f"This is my {text}"
        patrol.save()
        patrol2 = Patrol.objects.last()
        patrol2.title = f"{text} is my first"
        patrol2.save()

        filter = {'patrols_overlap_daterange': True, 'text': 'title'}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}")
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 2

    def test_filter_by_title_not_include_middle_string(self, five_patrols):
        patrol = Patrol.objects.first()
        patrol.title = "This is my title"
        patrol.save()
        patrol2 = Patrol.objects.last()
        patrol2.title = "Thisismytitle"
        patrol2.save()

        filter = {'patrols_overlap_daterange': True, 'text': 'title'}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}")
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["This is", "is my title", "we are writing"])
    def test_filter_by_title_with_two_or_more_words(self, five_patrols, text):
        patrol = Patrol.objects.first()
        patrol.title = "This is my title"
        patrol.save()
        patrol2 = Patrol.objects.last()
        patrol2.title = "We are writing my title here"
        patrol2.save()

        filter = {'patrols_overlap_daterange': True, 'text': text}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}")
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["message", "Message", "MESSAGE"])
    def test_filter_by_note(self, five_patrol_notes, text):
        patrol_note = PatrolNote.objects.first()
        patrol_note.text = f"This is my {text}"
        patrol_note.save()
        patrol_note_2 = PatrolNote.objects.last()
        patrol_note_2.text = f"{text} This is my"
        patrol_note_2.save()

        filter = {'patrols_overlap_daterange': True, 'text': text}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}")
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 2

    def test_filter_by_note_not_include_middle_string(self, five_patrol_notes):
        patrol_note = PatrolNote.objects.first()
        patrol_note.text = "This is my message"
        patrol_note.save()
        patrol_note_2 = PatrolNote.objects.last()
        patrol_note_2.text = "Thismessageismy"
        patrol_note_2.save()

        filter = {'patrols_overlap_daterange': True, 'text': "message"}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}")
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["here we", "are with another", "Words for this"])
    def test_filter_by_note_with_two_or_more_words(self, five_patrol_notes, text):
        patrol_note = PatrolNote.objects.first()
        patrol_note.text = f"Here we are with another test"
        patrol_note.save()
        patrol_note_2 = PatrolNote.objects.last()
        patrol_note_2.text = "Many words for this note"
        patrol_note_2.save()

        filter = {'patrols_overlap_daterange': True, 'text': text}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}")
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["animal", "Animal", "ANIMAL"])
    def test_by_patrol_type(self, five_patrol_segment, text):
        patrol_segment = PatrolSegment.objects.first()
        patrol_segment.patrol_type.display = f"animal type patrol"
        patrol_segment.patrol_type.save()
        patrol_segment2 = PatrolSegment.objects.last()
        patrol_segment2.patrol_type.display = f"type animal patrol"
        patrol_segment2.patrol_type.save()

        filter = {'patrols_overlap_daterange': True, 'text': text}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 2

    def test_by_patrol_type_not_include_middle_string(self, five_patrol_segment):
        patrol_segment = PatrolSegment.objects.first()
        patrol_segment.patrol_type.display = f"animal type patrol"
        patrol_segment.patrol_type.save()
        patrol_segment2 = PatrolSegment.objects.last()
        patrol_segment2.patrol_type.display = f"patrolanimaltype"
        patrol_segment2.patrol_type.save()

        filter = {'patrols_overlap_daterange': True, 'text': "animal"}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["You will", "a dog patrol", "ninja turtles"])
    def test_by_patrol_type_with_two_or_more_words(self, five_patrol_segment, text):
        patrol_segment = PatrolSegment.objects.first()
        patrol_segment.patrol_type.display = "You will be a dog patrol from right away"
        patrol_segment.patrol_type.save()
        patrol_segment2 = PatrolSegment.objects.last()
        patrol_segment2.patrol_type.display = "The ninja turtles patrol is here"
        patrol_segment2.patrol_type.save()

        filter = {'patrols_overlap_daterange': True, 'text': text}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["good", "Good", "GOOD"])
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
    def test_filter_by_tracked_subject_name(
            self, five_patrol_segment_subject, text, subject_group_with_perms
    ):
        subject = Subject.objects.first()
        subject.name = f"This is my name as a {text} subject"
        subject.save()
        subject2 = Subject.objects.last()
        subject2.name = f"{text} subject this name my is"
        subject2.save()
        subject_group_with_perms.subjects.add(subject, subject2)
        filter = {"patrols_overlap_daterange": True, "text": "good"}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        client.app_user.permission_sets.add(
            subject_group_with_perms.permission_sets.last())
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 2

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
    def test_filter_by_tracked_subject_name_not_include_middle_string(
            self, five_patrol_segment_subject, subject_group_with_perms
    ):
        subject = Subject.objects.first()
        subject.name = "I will be a subject for this test"
        subject.save()
        subject2 = Subject.objects.last()
        subject2.name = "iwillbeasubjectinthistest"
        subject2.save()
        subject_group_with_perms.subjects.add(subject, subject2)
        filter = {"patrols_overlap_daterange": True, "text": "subject"}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        client.app_user.permission_sets.add(
            subject_group_with_perms.permission_sets.last())
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)
        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["i will name", "this subject", "a new subject"])
    @pytest.mark.parametrize(
        "subject_group_with_perms",
        [
            [
                "view_subjectgroup,observations,subjectgroup",
                "view_subject,observations,subject",
            ],
        ],
        indirect=True,
    )
    def test_filter_by_tracked_subject_name_with_two_or_more_words(
            self, five_patrol_segment_subject, text, subject_group_with_perms
    ):
        patrol_segment_subjects = PatrolSegment.objects.first()
        patrol_segment_subjects.leader.name = "I will name this subject"
        patrol_segment_subjects.leader.save()
        patrol_segment_subjects2 = PatrolSegment.objects.last()
        patrol_segment_subjects2.leader.name = "a new subject will be here"
        patrol_segment_subjects2.leader.save()
        subject_group_with_perms.subjects.add(*Subject.objects.all())
        filter = {"patrols_overlap_daterange": True, "text": text}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        client.app_user.permission_sets.add(
            subject_group_with_perms.permission_sets.last())
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)
        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["arnold", "Arnold", "ARNOLD"])
    def test_filter_by_tracked_user(self, five_patrol_segment_user, text):
        patrol_segment_user = PatrolSegment.objects.first()
        patrol_segment_user.leader.first_name = "My name is Arnold"
        patrol_segment_user.leader.save()
        patrol_segment_user2 = PatrolSegment.objects.last()
        patrol_segment_user2.leader.last_name = "Arnold is my name"
        patrol_segment_user2.leader.save()

        filter = {'patrols_overlap_daterange': True, 'text': text}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 2

    def test_filter_by_tracked_user_not_include_middle_string(self, five_patrol_segment_user):
        patrol_segment_user = PatrolSegment.objects.first()
        patrol_segment_user.leader.first_name = "My name is Arnold"
        patrol_segment_user.leader.save()
        patrol_segment_user2 = PatrolSegment.objects.last()
        patrol_segment_user2.leader.last_name = "thisisArnoldisname"
        patrol_segment_user2.leader.save()

        filter = {'patrols_overlap_daterange': True, 'text': "arnold"}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("text", ["spongebob is", "am not a", "is a toon"])
    def test_filter_by_tracked_user_with_two_or_more_words(self, five_patrol_segment_user, text):
        patrol_segment_user = PatrolSegment.objects.first()
        patrol_segment_user.leader.first_name = "SpongeBob is a toon"
        patrol_segment_user.leader.save()
        patrol_segment_user2 = PatrolSegment.objects.last()
        patrol_segment_user2.leader.last_name = "I am not a toon"
        patrol_segment_user2.leader.save()

        filter = {'patrols_overlap_daterange': True, 'text': text}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name='View Patrols Permissions')
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filter)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == 200
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize(
        "subject",
        ["00000000-0000-0000-0000-000000000001",
            "00000000-0000-0000-0000-000000000002"],
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
    def test_filter_by_subject_list_with_one_value(
            self, five_patrol_segment_user_with_leader_uuid, subject, subject_group_with_perms
    ):
        subject_group_with_perms.subjects.add(*Subject.objects.all())
        filters = {"patrols_overlap_daterange": True, "tracked_by": [subject]}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        client.app_user.permission_sets.add(
            subject_group_with_perms.permission_sets.last())
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filters)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)
        assert response.status_code == status.HTTP_200_OK
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize(
        "subjects",
        [
            [
                "00000000-0000-0000-0000-000000000001",
                "00000000-0000-0000-0000-000000000002",
            ],
            [
                "00000000-0000-0000-0000-000000000003",
                "00000000-0000-0000-0000-000000000004",
            ],
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
    def test_filter_by_subject_list_with_many_values(
            self, five_patrol_segment_user_with_leader_uuid, subjects, subject_group_with_perms
    ):
        subject_group_with_perms.subjects.add(*Subject.objects.all())
        filters = {"patrols_overlap_daterange": True, "tracked_by": subjects}
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        client.app_user.permission_sets.add(
            subject_group_with_perms.permission_sets.last())
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filters)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)
        assert response.status_code == status.HTTP_200_OK
        assert data.get("count", 0) == 2

    @pytest.mark.parametrize("patrol_type", ["00000000-0000-0000-0000-000000000001"])
    def test_filter_by_patrol_type_with_one_value(self, five_patrol_segment_patrol_type_uuid, patrol_type):
        filters = {
            "patrols_overlap_daterange": True,
            "patrol_type": [patrol_type]
        }
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filters)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == status.HTTP_200_OK
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("patrol_type",
                             [["00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002"]])
    def test_filter_by_patrol_types_with_many_values(self, five_patrol_segment_patrol_type_uuid, patrol_type):
        filters = {
            "patrols_overlap_daterange": True,
            "patrol_type": patrol_type
        }
        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?filter={json.dumps(filters)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == status.HTTP_200_OK
        assert data.get("count", 0) == 2

    @pytest.mark.parametrize("statuses", [["active"], ["cancelled"]])
    def test_filter_by_patrol_status_list_with_one_value(self, five_patrol_segment, statuses):
        active_patrol = Patrol.objects.first()
        tzr = DateTimeTZRange(timezone.now())
        active_patrol_segment = active_patrol.patrol_segments.first()
        active_patrol_segment.time_range = tzr
        active_patrol_segment.save()

        cancelled_patrol = Patrol.objects.last()
        cancelled_patrol.state = "cancelled"
        cancelled_patrol.save()

        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?status={'&status='.join(statuses)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == status.HTTP_200_OK
        assert data.get("count", 0) == 1

    @pytest.mark.parametrize("statuses", [["active", "scheduled"], ["done", "cancelled"]])
    def test_filter_by_patrol_status_list_with_many_values(self, five_patrol_segment, statuses):
        cancelled_patrol = Patrol.objects.all()[0]
        cancelled_patrol.state = "cancelled"
        cancelled_patrol.save()

        done_patrol = Patrol.objects.all()[1]
        done_patrol.state = "cancelled"
        done_patrol.save()

        active_patrol = Patrol.objects.all()[2]
        tzr = DateTimeTZRange(timezone.now())
        active_patrol_segment = active_patrol.patrol_segments.first()
        active_patrol_segment.time_range = tzr
        active_patrol_segment.save()

        scheduled_patrol = Patrol.objects.all()[3]
        start_date = timezone.now() + timezone.timedelta(days=2)
        end_date = timezone.now() + timezone.timedelta(days=4)
        scheduled_patro_segment = scheduled_patrol.patrol_segments.first()
        scheduled_patro_segment.scheduled_start = start_date
        scheduled_patro_segment.scheduled_end = end_date
        scheduled_patro_segment.save()

        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="View Patrols Permissions"
        )
        client.app_user.permission_sets.add(view_patrol_permissionset)
        request = client.factory.get(
            client.api_base + f"/patrols/?status={'&status='.join(statuses)}"
        )
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert response.status_code == status.HTTP_200_OK
        assert data.get("count", 0) == 2

    def _arrange_patrol_serial_number_sql(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE activity_patrol SET serial_number=1000 WHERE id=(SELECT id FROM activity_patrol LIMIT 1)"
            )
            cursor.execute(
                "UPDATE activity_patrol SET serial_number=1001 WHERE id=(SELECT id FROM activity_patrol LIMIT 1 OFFSET 2)"
            )


@pytest.mark.django_db
class TestPatrolView:
    def test_create_patrol_with_past_end_date(self):
        now = datetime.datetime.now(tz=pytz.utc)
        past_start_date = now - datetime.timedelta(days=6)
        past_end_date = now - datetime.timedelta(days=3)
        patrol_data = {
            "patrol_segments":
                [
                    {
                        "patrol_type": "routine_patrol",
                        "time_range":
                            {
                                "start_time": past_start_date.isoformat(),
                                "end_time": past_end_date.isoformat()
                            },
                    }
                ],
            "title": "Patrol with past date"
        }

        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="Patrols Permissions - No Delete")
        client.app_user.permission_sets.add(view_patrol_permissionset)

        request = client.factory.post(
            client.api_base + f"/patrols/", data=patrol_data)
        client.force_authenticate(request, client.app_user)
        response = views.PatrolsView.as_view()(request)
        data = dict(response.data)

        assert data["state"] == PC_DONE

    def test_update_patrol_with_past_end_date(self, five_patrol_segment):
        now = datetime.datetime.now(tz=pytz.utc)
        past_start_date = now - datetime.timedelta(days=6)
        past_end_date = now - datetime.timedelta(days=3)

        patrol = Patrol.objects.order_by('created_at').last()
        assert patrol.state == PC_OPEN

        segment = patrol.patrol_segments.first()
        segment.time_range = DateTimeTZRange(
            lower=past_start_date, upper=past_end_date)
        segment.save()

        data = PatrolSerializer(patrol).data

        client = HTTPClient()
        view_patrol_permissionset = PermissionSet.objects.get(
            name="Patrols Permissions - No Delete")
        client.app_user.permission_sets.add(view_patrol_permissionset)

        request = client.factory.patch(
            f"{client.api_base}/patrols/{patrol.id}", data=data)
        client.force_authenticate(request, client.app_user)
        response = views.PatrolView.as_view()(request, id=patrol.id)
        data = dict(response.data)

        assert data["state"] == PC_DONE


@pytest.mark.django_db
class TestPatrolModel:
    @pytest.mark.parametrize("patrol_type", ["ff2f7da6-ade4-4dc1-bd7a-c2c5244017fa", "e62ca278-8687-455e-ba76-2c7dfa4d6b5f"])
    def test_create_patrol_with_past_date(self, patrol_type):
        patrol = Patrol(title="Created Patrol through model")
        assert patrol.state == PC_OPEN

        now = datetime.datetime.now(tz=pytz.utc)
        past_start_date = now - datetime.timedelta(days=6)
        past_end_date = now - datetime.timedelta(days=3)

        time_range = DateTimeTZRange(
            lower=past_start_date, upper=past_end_date)
        segment = PatrolSegment.objects.create(
            patrol=patrol, patrol_type_id=patrol_type, time_range=time_range)

        patrol.patrol_segments.add(segment)
        patrol.save()

        assert patrol.state == PC_DONE

    def test_filter_by_patrol_method(self, five_patrol_segment):
        patrol = Patrol.objects.order_by("created_at").last()
        patrol.title = "test"

        segment = patrol.patrol_segments.first()
        start_date = datetime.datetime.now(
            tz=pytz.utc) - datetime.timedelta(days=2)
        segment.time_range = DateTimeTZRange(lower=start_date)

        segment.save()
        patrol.save()

        filters = {
            'date_range': {'lower': start_date.isoformat()},
            'patrols_overlap_daterange': True,
            'patrol_type': [],
            'text': 'test',
            'tracked_by': []
        }
        patrols = Patrol.objects.by_patrol_filter(filters)

        assert patrols.first().id == patrol.id

    def test_by_date_range_method(self, five_patrol_segment):
        patrol = Patrol.objects.order_by("created_at").last()
        segment = patrol.patrol_segments.first()

        start_date = datetime.datetime.now(
            tz=pytz.utc) - datetime.timedelta(days=2)
        segment.time_range = DateTimeTZRange(lower=start_date)
        segment.save()

        filters = {'lower': segment.time_range.lower.isoformat()}
        patrols = Patrol.objects.by_date_range(filters, True)

        assert patrols.first().id == patrol.id


@pytest.mark.django_db
class TestPatrolTrackedBySchemaView:
    def test_trackedby_permissions_for_a_subjectgroup_viewer(self, django_assert_max_num_queries, client,
                                                             two_subject_groups, ops_user):
        a_subjectgroup, b_subjectgroup = two_subject_groups
        a_subjectgroup.permission_sets.all()[0].user_set.add(ops_user)
        PatrolConfiguration.objects.first().subject_groups.add(
            *[a_subjectgroup, b_subjectgroup])

        url = reverse('patrol-segments-schema')
        client.force_login(ops_user)

        with django_assert_max_num_queries(18):
            response = client.get(url)
            leaders = response.data["properties"]["leader"]["enum"]
            assert not any(subject.name == leader["name"]
                           for subject in b_subjectgroup.subjects.all() for leader in leaders)

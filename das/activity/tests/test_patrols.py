import datetime
import json
import os
import pytz
from urllib.parse import urlencode

import django.contrib.auth
from django.core.management import call_command
from django.urls import reverse

from activity import views
from activity.models import Patrol, PatrolSegment, PatrolType
from core.tests import BaseAPITest
from observations.models import Subject

User = django.contrib.auth.get_user_model()
TESTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'tests')


class TestPatrol(BaseAPITest):

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'test_patroltype')

        user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('user', 'user@test.com', 'all_perms_user', is_superuser=True,
                                             is_staff=True, **user_const)
        Patrol.objects.bulk_create(
            [
                Patrol(id="b14bc72f-96d6-4248-9fea-7dd0bbc8c196", title='Test Patrol', objective='Test Objective'),
                Patrol(title='Test Patrol 2', objective='Test Objective 2')
            ])
        PatrolSegment.objects.create(patrol_type=PatrolType.objects.first())

        now = datetime.datetime.now(tz=pytz.utc)
        self.start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.end_of_today = self.start_of_today + datetime.timedelta(hours=23, minutes=59, seconds=59)

        self.sample_patrol_filter = {
            'filter': json.dumps(
                {"date_range": {
                    "lower": self.start_of_today.isoformat(), "upper": self.end_of_today.isoformat()}})}


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
        assert response.data.get('count') == 2

    def test_get_one_patrol_by_id(self):
        patrol_id = 'b14bc72f-96d6-4248-9fea-7dd0bbc8c196'
        url = reverse('patrol', kwargs={'id': patrol_id})

        request = self.factory.get(url)
        self.force_authenticate(request, self.user)
        response = views.PatrolView.as_view()(request, id=patrol_id)
        assert response.status_code == 200

    def test_create_patrolsegment(self):
        subj = Subject.objects.create(name='Heritage', subject_subtype_id='elephant')

        patrolsgm_data = dict(scheduled_start='2020-08-05 02:00:00+00',
                              time_range={"start_time": "2020-08-05 02:00:00+00", "end_time": "2020-08-06 04:00:00+00"},
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
                              start_location={'latitude': '-122.334', 'longitude': '47.598'},
                              end_location={'latitude': '-124.54', 'longitude': '38.98'},
                              )
        url = reverse('patrol-segments')
        request = self.factory.post(url, data=patrolsgm_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

    def test_create_patrol_segment_with_invalid_time_range(self):
        segment_data = dict(time_range={"start_time": "2030-08-05 02:00:00+00", "end_time": "2020-08-06 04:00:00+00"})
        url = reverse('patrol-segments')
        request = self.factory.post(url, data=segment_data)
        self.force_authenticate(request, self.app_user)
        response = views.PatrolsegmentsView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn('start_time must be an earlier date than the end_time', response.data.get('time_range'))


    def test_create_patrol_patrolsegment_with_no_leader(self):
        patrol_patrolsg = dict(
            prioity=0,
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
        subj = Subject.objects.create(name='Heritage', subject_subtype_id='elephant')

        patrol_patrolsg = dict(
            objective="Patrol Management",
            prioity=0,
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

    def test_update_all_patrol_patrolsegment_properties(self):
        su = Subject.objects.create(name='Horton', subject_subtype_id='elephant')

        patrol_patrolsegment = dict(
            objective="Patrol Management",
            prioity=0,
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
                    "longitude": -129.3607072,
                    "latitude": 49.681731199999994
                },
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
        subject = Subject.objects.create(name='Fatu', subject_subtype_id='rhino')

        updated_patrol_patrolsg = dict(
            objective= "Lorem Ipsum is simply dummy text of the printing and typesetting industry",
            priority=200,
            title="Dog Patrol",
            state="open",
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
                "scheduled_start": "2020-09-26T01:14:34.196502+03:00",
                "time_range": {
                    "start_time": "2020-09-29T07:09:16.711000+03:00",
                    "end_time": "2020-09-30T07:10:16.711000+03:00"
                },
                "start_location": {
                    "longitude": 37.440896005591924,
                    "latitude": 0.23907934715522572
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

    def test_update_patrol(self):
        patrol_update_data = dict(
            title="New updated title",
            notes=[{"text": "New first note"}, {"text": "New second Note"}],
            patrol_segments=[{"patrol_type": "dog_patrol"}]
        )
        patrol = Patrol.objects.first()
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
            notes=[{"text": "New third note"}, {"text": "Update first note", "id": response.data.get('notes')[0]['id']}],
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

        subj = Subject.objects.create(name='Heritage', subject_subtype_id='elephant')

        patrol_update_data2 = dict(
            prioity=0,
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
        self.assertEqual(patrol_type.value, segment_update_data.get('patrol_type'))  # dog_patrol
        self.assertEqual(response.status_code, 200)

    def test_update_patrol_with_new_patrolsegment(self):
        patrol = dict(state="open")
        patrolsg = dict(patrol_type="dog_patrol")

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
        self.assertEqual(response.data.get('patrol'), None)

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
        response = self._filter_patrol(self.sample_patrol_filter)  # today's filter
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data.get('results')[0].get('title'), patrol_data.get('title'))

        # filter by only lower
        filter_query = {'filter': json.dumps({"date_range": {"lower": self.start_of_today.isoformat()}})}
        response = self._filter_patrol(filter_query)
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data.get('results')[0].get('title'), patrol_data.get('title'))

        # filter by only upper
        filter_query = {'filter': json.dumps({"date_range": {"upper": self.start_of_today.isoformat()}})}
        response = self._filter_patrol(filter_query)
        self.assertEqual(response.data.get('count'), 0)

    def test_patrol_filter_only_scheduled_start_given(self):
        start = self.start_of_today + datetime.timedelta(days=5)  # 5 days later
        patrol_data = dict(
            title='Sheduled Patrol',
            patrol_segments=[
                {'scheduled_start': start.isoformat()}]
        )
        self._create_patrol(patrol_data)
        response = self._filter_patrol(self.sample_patrol_filter)  # today's filter
        self.assertEqual(response.data.get('count'), 0)

        lower = self.start_of_today + datetime.timedelta(days=3)  # 3 days from now
        upper = self.start_of_today + datetime.timedelta(days=7)  # 7 days from now

        patrol_filter = {'filter': json.dumps({"date_range": {"lower": lower.isoformat(), "upper": upper.isoformat()}})}
        response = self._filter_patrol(patrol_filter)
        self.assertEqual(response.data.get('count'), 1)

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
        self.assertEqual(response.data.get('results')[0].get('title'), patrol_data.get('title'))

    def test_patrol_filter_with_past_end_time_but_patrol_not_completed(self):
        start = self.start_of_today - datetime.timedelta(days=2, hours=10)
        end = self.start_of_today - datetime.timedelta(days=2, hours=5)
        patrol_data = dict(
            title='Test Patrol',
            patrol_segments=[{'time_range': {"start_time": start.isoformat(), "end_time": end.isoformat()}}]
        )
        self._create_patrol(patrol_data)
        response = self._filter_patrol(self.sample_patrol_filter)

        # patrol is still displayed as current since its not marked as done or complete
        self.assertEqual(response.data.get('count'), 1)
        result = response.data.get('results')[0]
        self.assertEqual(result.get('title'), patrol_data.get('title'))

        # update the patrol to completed
        patrol_id = result.get('id')
        url = reverse('patrol', kwargs={'id': patrol_id})
        patrol_update_data = dict(
            state="done",
            patrol_segments=[{
                "id": result.get('patrol_segments')[0]['id']
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

        response = self._filter_patrol(self.sample_patrol_filter)  # current patrols filter
        self.assertEqual(response.data.get('count'), 1)
        self.assertEqual(response.data.get('results')[0].get('title'), patrol_data.get('title'))



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

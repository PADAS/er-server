import copy
import collections

import django.contrib.auth
from django.db import transaction
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import Permission
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from core.tests import BaseAPITest
from core.models import Choice
from accounts.models import PermissionSet
from activity.models import Event, EventAttachment, EventType
from activity.models import get_sentinel_user
from activity.serializers import ATTACHMENT_SERIALIZER_MAPPING
from activity import views
from observations.models import Subject
from accounts.serializers import UserDisplaySerializer
from observations.serializers import SubjectSerializer


User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'

class TestSourcePlugin(TestCase):
    def setUp(self):
        super().setUp()

    def test_sentinel_user(self):
        user = get_sentinel_user()
        self.assertEqual('deleted', user.username)

    def test_create_event_with_attachment(self):
        with transaction.atomic():
            e = Event.objects.create_event(message=lorem_ipsum.paragraph(),
                                           provenance=Event.PC_SYSTEM,
                                           event_type=EventType.objects.get_by_value(ET_OTHER),
                                           priority=Event.PRI_URGENT,
                                           attributes={},
                                           )

        self.assertIsNotNone(e.id)


class TestEventView(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('super', 'super@test.com', 'super', is_superuser=True, is_staff=True, **self.user_const)
        self.readonly_user = User.objects.create_user('readonly',
                                                      'readonly@test.com',
                                                      'readonly', **self.user_const)
        self.no_perms_user = User.objects.create_user('noperms',
                                                      'noperms@test.com',
                                                      'noperms', **self.user_const)
        self.user_rep = UserDisplaySerializer().to_representation(self.user)
        self.staff = Subject.objects.create(name='Ranger 2', additional={})
        self.staff_rep = SubjectSerializer().to_representation(self.staff)



        self.event_data = dict(
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517')
            )

        self.sample_event = self.create_event(self.event_data)

        self.event_set = PermissionSet.objects.create(name='eventset')
        self.event_set.permissions.add(
            Permission.objects.get(codename='view_event'))
        self.readonly_user.permission_sets.add(self.event_set)

    def create_event(self, event_data):
        data = copy.deepcopy(event_data)
        if 'time' in event_data:
            data['event_time'] = DateTimeField().to_internal_value(
                event_data['time'])
            del data['time']
        if isinstance(event_data.get('event_type', None), str):
            data['event_type'] = EventType.objects.get_by_value(event_data['event_type'])

        if 'location' in data:
            data['location'] = PointField().to_internal_value(
                data['location'])
        return Event.objects.create_event(**data)

    def test_return_event_details(self):
        request = self.factory.get(self.api_base + '/event/')
        self.force_authenticate(request, self.user)

        response = views.EventView.as_view()(request, id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 200)
        response_data = response.data
        response_data = {k: response_data[k] for k in self.event_data.keys()}
        self.assertDictEqual(response_data, self.event_data)

    def test_create_new_event(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_OTHER
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k:response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_create_matrix_event(self):
        event_data = {'priority': Event.PRI_REFERENCE,
                      }

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_create_new_message_only_event(self):
        event_data = {'message': lorem_ipsum.sentence(),
                      'event_type': ET_OTHER,
                      }
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k:response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_add_note(self):
        note_data = {'text': lorem_ipsum.paragraph()}
        request = self.factory.post(self.api_base
            + '/event/{0}/notes'.format(self.sample_event.id),
                                    note_data)
        self.force_authenticate(request, self.user)

        response = views.EventNotesView.as_view()(request,
                                                  id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k: response_data[k] for k in note_data.keys()}
        self.assertDictEqual(response_data, note_data)

    def test_add_note_view_permission(self):
        note_data = {'text': lorem_ipsum.paragraph()}
        request = self.factory.post(self.api_base
                                    + '/event/{0}/notes'.format(
            self.sample_event.id),
                                    note_data)
        self.force_authenticate(request, self.readonly_user)

        response = views.EventNotesView.as_view()(request,
                                                  id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 403)

    def test_update_message_succeed(self):
        event = self.create_event(self.event_data)

        update_data = copy.deepcopy(self.event_data)
        update_data['id'] = event.id
        update_data['message'] = 'A completely different message'

        request = self.factory.patch(
            self.api_base + '/event/{0}/'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.user)

        response = views.EventView.as_view()(request,
                                             id=str(event.id))
        self.assertEqual(response.status_code, 200)
        response_data = response.data
        self.assertEqual(response_data['message'], update_data['message'])

    def test_validate_serializer_schema(self):
        request = self.factory.get(self.api_base + '/events/schema')
        self.force_authenticate(request, self.user)

        response = views.EventSchemaView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertIn('provenance', response_data['properties'])

    def test_event_count(self):
        request = self.factory.get(self.api_base + '/events/count')
        self.force_authenticate(request, self.user)

        response = views.EventCountView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data['count'], Event.objects.count())

    def test_event_count_no_view_permission(self):
        request = self.factory.get(self.api_base + '/events/count')
        self.force_authenticate(request, self.no_perms_user)

        response = views.EventCountView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 403)

    def test_add_reported_by(self):
        event = self.create_event(self.event_data)
        update_data = {}
        update_data['reported_by'] = self.user_rep
        update_data['provenance'] = Event.PC_STAFF

        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.user)

        response = views.EventView.as_view()(request,
                                             id=str(event.id))
        self.assertEqual(response.status_code, 200)
        response_data = response.data
        self.assertEqual(response_data['reported_by']['id'],
                         update_data['reported_by']['id'])

    def test_update_event_state_active(self):
        event = self.create_event(self.event_data)
        update_data = {'state': 'active'}

        request = self.factory.patch(
            self.api_base + '/event/{0}/state'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.user)

        response = views.EventStateView.as_view()(request,
                                             id=str(event.id))
        self.assertEqual(response.status_code, 200)
        response_data = response.data
        self.assertEqual(response_data['state'], update_data['state'])

    def test_update_event_active(self):
        event = self.create_event(self.event_data)
        update_data = {'state': 'active'}

        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.user)

        response = views.EventStateView.as_view()(request,
                                                  id=str(event.id))
        self.assertEqual(response.status_code, 200)
        response_data = response.data
        self.assertEqual(response_data['state'], update_data['state'])

    def test_update_event_active_no_permission(self):
        event = self.create_event(self.event_data)
        update_data = {'state': 'active'}

        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.readonly_user)

        response = views.EventStateView.as_view()(request,
                                                  id=str(event.id))
        self.assertEqual(response.status_code, 403)


class TestSerializers(TestCase):
    def test_have_all_attachment_serializer_mappings(self):
        for q in EventAttachment.limits.children:
            q = dict(q.children)
            self.assertIn('.'.join((q['app_label'], q['model'])),
                          ATTACHMENT_SERIALIZER_MAPPING)

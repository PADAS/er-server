import copy
import collections

import django.contrib.auth
from django.db import transaction
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from core.tests import BaseAPITest
from activity.models import Event, EventAttachment
from activity.models import get_sentinel_user
from activity.serializers import ATTACHMENT_SERIALIZER_MAPPING
from activity import views
from observations.models import Subject
from accounts.serializers import UserDisplaySerializer
from observations.serializers import SubjectSerializer


User = django.contrib.auth.get_user_model()


class TestSourcePlugin(TestCase):
    def setUp(self):
        pass

    def test_sentinel_user(self):
        user = get_sentinel_user()
        self.assertEqual('deleted', user.username)

    def test_create_event_with_attachment(self):
        with transaction.atomic():
            e = Event.objects.create_event(message=lorem_ipsum.paragraph(),
                                           provenance=Event.PC_COMMUNITY,
                                           event_type=Event.ET_LIVESTOCK_THEFT,
                                           priority=Event.PRI_URGENT,
                                           attributes={},
                                           )

        self.assertIsNotNone(e.id)


class TestEventView(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('super', 'super@test.com', 'super', is_superuser=True, is_staff=True)
        self.user_rep = UserDisplaySerializer().to_representation(self.user)
        self.staff = Subject.objects.create(name='Ranger 2', additional={})
        self.staff_rep = SubjectSerializer().to_representation(self.staff)

        self.event_data = dict(
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_COMMUNITY,
            event_type=Event.ET_OTHER,
            priority=Event.PRI_DEFAULT_VALUE,
            location=dict(longitude='40.1353', latitude='-1.891517')
            )

        self.sample_event = self.create_event(self.event_data)

    def create_event(self, event_data):
        data = copy.deepcopy(event_data)
        if 'time' in event_data:
            data['event_time'] = DateTimeField().to_internal_value(
                event_data['time'])
            del data['time']
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

    def test_update_message_succeed(self):
        event = self.create_event(self.event_data)

        update_data = copy.deepcopy(self.event_data)
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



class TestSerializers(TestCase):
    def test_have_all_attachment_serializer_mappings(self):
        for q in EventAttachment.limits.children:
            q = dict(q.children)
            self.assertIn('.'.join((q['app_label'], q['model'])),
                          ATTACHMENT_SERIALIZER_MAPPING)

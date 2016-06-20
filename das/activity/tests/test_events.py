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
from core.models import Choices
from accounts.models import PermissionSet
from activity.models import Event, EventAttachment
from activity.models import get_sentinel_user
from activity.serializers import ATTACHMENT_SERIALIZER_MAPPING
from activity import views
from observations.models import Subject
from accounts.serializers import UserDisplaySerializer
from observations.serializers import SubjectSerializer


User = django.contrib.auth.get_user_model()


ET_SYSTEM = 'system'
ET_PROXIMITY = 'proximity'
ET_GEOFENCE = 'geofence'
ET_IMMOBILITY = 'immobility'
ET_SPEED = 'speed'

ET_OTHER = 'other'
ET_EXCLUSION_ZONE_BREACH = 'exclusion-zone-breach'
ET_PERIMETER_FENCE_BREACH = 'perimeter-fence-breach'
ET_ELEPHANT_SIGHTING = 'elephant-sighting'
ET_WOUNDED_ANIMAL = 'wounded-animal'
ET_FIRE = 'fire'
ET_LIVESTOCK_THEFT = 'livestock-theft'
ET_CONTAINMENT_BREACH = 'containment-breach'
ET_FOOTPRINTS = 'footprints'
ET_GUNSHOT_HEARD = 'gunshot-heard'
ET_RADIO_TEXT_MESSAGE = 'radio-text-message'

ET_DEFAULT_VALUE = ET_OTHER

EVENT_TYPE_CHOICES = (
    (ET_SYSTEM, 'System'),
    (ET_PROXIMITY, 'Proximity'),
    (ET_GEOFENCE, 'Geofence'),
    (ET_IMMOBILITY, 'Immobility'),
    (ET_SPEED, 'Speed'),
    (ET_EXCLUSION_ZONE_BREACH, 'Exclusion Zone Breach'),
    (ET_PERIMETER_FENCE_BREACH, 'Perimeter Fence Breach'),
    (ET_ELEPHANT_SIGHTING, 'Elephant Sighting'),
    (ET_WOUNDED_ANIMAL, 'Wounded Animal'),
    (ET_LIVESTOCK_THEFT, 'Livestock Theft'),
    (ET_FIRE, 'Fire'),
    (ET_CONTAINMENT_BREACH, 'Containment Breach'),
    (ET_FOOTPRINTS, 'Suspicious Signs'),
    (ET_GUNSHOT_HEARD, 'Gunshot Heard'),
    (ET_RADIO_TEXT_MESSAGE, 'Radio Text Message'),
    (ET_OTHER, 'Other'),
)


def populate_event_types():
    model = Event._meta.label_lower
    field = 'event_type'
    field_sub = 'event_subtype'
    for et, display in EVENT_TYPE_CHOICES:
        parent = Choices.objects.create(model=model,
                                        field=field,
                                        value=et,
                                        display=display)


        sub = Choices.objects.create(model=model,
                               field=field_sub,
                               value=et + '_sub',
                               display=display + ' SubType'
                               )
        sub.sub_choice_of.add(parent)
        sub.save()

class TestSourcePlugin(TestCase):
    def setUp(self):
        populate_event_types()

    def test_sentinel_user(self):
        user = get_sentinel_user()
        self.assertEqual('deleted', user.username)

    def test_create_event_with_attachment(self):
        with transaction.atomic():
            e = Event.objects.create_event(message=lorem_ipsum.paragraph(),
                                           provenance=Event.PC_COMMUNITY,
                                           event_type=ET_LIVESTOCK_THEFT,
                                           priority=Event.PRI_URGENT,
                                           attributes={},
                                           )

        self.assertIsNotNone(e.id)


class TestEventView(BaseAPITest):
    def setUp(self):
        super().setUp()
        populate_event_types()
        self.user = User.objects.create_user('super', 'super@test.com', 'super', is_superuser=True, is_staff=True)
        self.readonly_user = User.objects.create_user('readonly',
                                                      'readonly@test.com',
                                                      'readonly')
        self.no_perms_user = User.objects.create_user('noperms',
                                                      'noperms@test.com',
                                                      'noperms')
        self.user_rep = UserDisplaySerializer().to_representation(self.user)
        self.staff = Subject.objects.create(name='Ranger 2', additional={})
        self.staff_rep = SubjectSerializer().to_representation(self.staff)



        self.event_data = dict(
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_COMMUNITY,
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
        event_data['event_subtype'] = event_data['event_type'] + '_sub'
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k:response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_create_new_event_invalid_subtype(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_subtype'] = 'system_sub'
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_create_new_message_only_event(self):
        event_data = {'message': lorem_ipsum.sentence(),
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

        response = views.EventsCountView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data['count'], Event.objects.count())

    def test_event_count_no_view_permission(self):
        request = self.factory.get(self.api_base + '/events/count')
        self.force_authenticate(request, self.no_perms_user)

        response = views.EventsCountView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 403)


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

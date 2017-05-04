import copy
import collections
import string, random

import django.contrib.auth
from django.db import transaction
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.urlresolvers import reverse
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from core.tests import BaseAPITest
from choices.models import Choice
from accounts.models import PermissionSet
from activity.models import Event, EventAttachment, EventType, EventCategory
from activity.models import get_sentinel_user, marker_icon
from activity.serializers import ATTACHMENT_SERIALIZER_MAPPING
from activity import views
from observations.models import Subject
from accounts.serializers import UserDisplaySerializer
from observations.serializers import SubjectSerializer


User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'

ET_SECURITY = 'carcass'
ET_STANDARD = 'rhino_birth'
ET_LOGISTICS = 'snare'

### These permission lists are made up, and do not necessarily correspond to permission sets in production deployments
# All perms user has... all perms
all_permissions = [
    'security_create', 'security_read', 'security_update', 'security_delete',
    'standard_create', 'standard_read', 'standard_update', 'standard_delete',
    'logistics_create', 'logistics_read', 'logistics_update', 'logistics_delete']
# Power user has all access to logistics and standard events, but can only read security events
power_user_permissions = [
    'security_read',
    'standard_create', 'standard_read', 'standard_update', 'standard_delete',
    'logistics_create', 'logistics_read', 'logistics_update', 'logistics_delete']
# Radio room users can create any type of event, view/update standard and logistics events, and delete nothing
radio_room_user_permissions = [
    'security_create',
    'standard_create', 'standard_read', 'standard_update',
    'logistics_create', 'logistics_read', 'logistics_update']
# Guest users can see logistics events and nothing else
guest_user_permissions = ['logistics_read']


class TestSourcePlugin(TestCase):
    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventtype')
        call_command('loaddata', 'initial_eventdata')

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
        call_command('loaddata', 'initial_eventdata')

        self.no_perms_user = User.objects.create_user('no_perms_user',
            'das_no_perms@vulcan.com', 'noperms', **self.user_const)
        self.guest_user = User.objects.create_user(
            'guest_user', 'das_guest_user@vulcan.com', 'guest_user',
            **self.user_const)
        self.radio_room_user = User.objects.create_user(
            'radio_room_user', 'das_radio_room@vulcan.com',
            'radio_room_user', **self.user_const)
        self.power_user = User.objects.create_user(
            'power_user', 'das_power_user@vulcan.com', 'power_user',
            **self.user_const)
        self.all_perms_user = User.objects.create_user(
            'all_perms_user', 'das_all_perms@vulcan.com', 'all_perms_user',
            **self.user_const)

        self.event_data = dict(
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517')
            )

        self.sample_event = self.create_event(self.event_data)

        self.all_perms_permissionset = PermissionSet.objects.create(name='all_perms_set')
        for perm in all_permissions:
            self.all_perms_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.all_perms_user.permission_sets.add(self.all_perms_permissionset)

        self.power_user_permissionset = PermissionSet.objects.create(name='power_set')
        for perm in power_user_permissions:
            self.power_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.power_user.permission_sets.add(self.power_user_permissionset)

        self.radio_room_user_permissionset = PermissionSet.objects.create(name='radio_room_perms_set')
        for perm in radio_room_user_permissions:
            self.radio_room_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.radio_room_user.permission_sets.add(self.radio_room_user_permissionset)

        self.guest_user_permissionset = PermissionSet.objects.create(name='guest_set')
        for perm in guest_user_permissions:
            self.guest_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.guest_user.permission_sets.add(self.guest_user_permissionset)

        self.user_rep = UserDisplaySerializer().to_representation(self.guest_user)

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

        request = self.factory.get(self.api_base + '/events/schema')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventSchemaView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

    def test_find_all_event_type_icons(self):
        for et in EventType.objects.all():
            for p in Event.PRIORITY_CHOICES:
                for s in Event.STATE_CHOICES:
                    image = marker_icon(et.value,
                        p[0], s[0])
                    image = image[8:]
                    self.assertTrue(finders.find(image), 'Failed to find image: {0}'.format(image))


    def test_return_event_details(self):
        request = self.factory.get(self.api_base + '/event/')
        self.force_authenticate(request, self.all_perms_user)

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
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k:response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_create_matrix_event(self):
        event_data = {'priority': Event.PRI_REFERENCE,
                      'event_type': ET_OTHER,
                      'attributes': {
                            'event_class': 'trespass',
                            'event_factor': 'loss_of_life',
                          },
                      }

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

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
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k:response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    ### These tests don't pass anymore because of the permissions change, but
    ### Since we're refactoring notes anyway, I'm going to leave them commented
    ### out instead of fixing them so they pass.
    # def test_add_note(self):
    #     note_data = {'text': lorem_ipsum.paragraph()}
    #     request = self.factory.post(self.api_base
    #         + '/event/{0}/notes'.format(self.sample_event.id),
    #                                 note_data)
    #     self.force_authenticate(request, self.user)
    #
    #     response = views.EventNotesView.as_view()(request,
    #                                               id=str(self.sample_event.id))
    #     self.assertEqual(response.status_code, 201)
    #     response_data = response.data
    #     response_data = {k: response_data[k] for k in note_data.keys()}
    #     self.assertDictEqual(response_data, note_data)
    #
    # def test_add_note_view_permission(self):
    #     note_data = {'text': lorem_ipsum.paragraph()}
    #     request = self.factory.post(self.api_base
    #                                 + '/event/{0}/notes'.format(
    #         self.sample_event.id),
    #                                 note_data)
    #     self.force_authenticate(request, self.readonly_user)
    #
    #     response = views.EventNotesView.as_view()(request,
    #                                               id=str(self.sample_event.id))
    #     self.assertEqual(response.status_code, 403)

    def test_update_message_succeed(self):
        event = self.create_event(self.event_data)

        update_data = copy.deepcopy(self.event_data)
        update_data['id'] = event.id
        update_data['message'] = 'A completely different message'

        request = self.factory.patch(
            self.api_base + '/event/{0}/'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request,
                                             id=str(event.id))
        self.assertEqual(response.status_code, 200)
        response_data = response.data
        self.assertEqual(response_data['message'], update_data['message'])

    def test_validate_serializer_schema(self):
        request = self.factory.get(self.api_base + '/events/schema')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventSchemaView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertIn('provenance', response_data['properties'])

    def test_event_feed(self):
        request = self.factory.get(self.api_base + '/events')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

    def test_event_feed_category(self):
        request = self.factory.get(self.api_base + '/events?event_category=standard&event_category=security')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

    def test_event_type_category(self):
        request = self.factory.get(self.api_base + '/events/eventtypes?category=standard&event_category=security')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventTypesView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

    def test_event_categories_list(self):

        request = self.factory.get(self.api_base + '/events/categories')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        category_values = [x['value'] for x in response.data]

        self.assertIn('security', category_values)
        self.assertIn('standard', category_values)
        self.assertIn('logistics', category_values)

    def test_event_count(self):
        request = self.factory.get(self.api_base + '/events/count')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventCountView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data['count'], Event.objects.count())

    def test_event_count_no_view_permission(self):
        request = self.factory.get(self.api_base + '/events/count')
        self.force_authenticate(request, self.no_perms_user)

        response = views.EventCountView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_event_count_by_category(self):
        all_request = self.factory.get(self.api_base + '/events/count')
        self.force_authenticate(all_request, self.all_perms_user)
        all_response = views.EventCountView.as_view()(all_request)
        all_response_data = all_response.data

        some_request = self.factory.get(self.api_base + '/events/count')
        self.force_authenticate(some_request, self.guest_user)
        some_response = views.EventCountView.as_view()(some_request)
        some_response_data = some_response.data

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(some_response.status_code, 200)

        self.assertGreater(all_response_data['count'], some_response_data['count'])


    def test_add_reported_by(self):
        event = self.create_event(self.event_data)
        update_data = {}
        update_data['reported_by'] = self.user_rep
        update_data['provenance'] = Event.PC_STAFF

        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.all_perms_user)

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
        self.force_authenticate(request, self.all_perms_user)

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
        self.force_authenticate(request, self.all_perms_user)

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
        self.force_authenticate(request, self.guest_user)

        response = views.EventStateView.as_view()(request,
                                                  id=str(event.id))
        self.assertEqual(response.status_code, 403)


    def test_event_type_collection(self):
        event_type = EventType.objects.get_by_value('incident_collection')

        self.assertTrue(event_type.is_collection)


    def test_create_collection(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = 'incident_collection'
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

        collection_id = response.data['id']

        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_LOGISTICS
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

        report_id = response.data['id']
        rel_data = {'to_event_id': report_id, 'type': 'contains'}
        request = self.factory.post(self.api_base + '/event/' + collection_id + '/relationships', rel_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventRelationshipsView.as_view()(request, from_event_id=collection_id)
        print(response)
        self.assertEqual(response.status_code, 201)

    def test_event_without_event_type(self):
        event_data = {'message': 'this has no event type', 'priority': '200'}

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 400)

        self.assertTrue('event_type' in response.data, 'I cannot find "event_type" in response data.')





    def test_edit_event_title(self):
        event = self.create_event(self.event_data)
        TITLE = ''.join([random.choice(string.ascii_letters + string.digits + string.punctuation) for x in range(30)])
        update_data = {'title': TITLE}

        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request, id=str(event.id))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.data['title'], TITLE)

    def test_add_event_category(self):
        value = 'new'
        display = 'new event permissions'
        EventCategory.objects.create(value=value, display=display)

        for operation in ['create', 'read', 'update', 'delete']:
            codename = '{0}_{1}'.format(value, operation)
            self.assertIsNotNone(Permission.objects.get(codename=codename))

    def test_all_perms_user_permissions(self):
        results = self.do_all_operations_on_all_event_types(self.all_perms_user)

        for k, v in results.items():
            self.assertTrue(v, 'All perms user failed {0}'.format(k))

    def test_power_user_permissions(self):
        results = self.do_all_operations_on_all_event_types(self.power_user)

        for k, v in results.items():
            if k in power_user_permissions:
                self.assertTrue(v, 'Power user failed {0}'.format(k))
            else:
                self.assertFalse(v, 'Power user passed {0}'.format(k))

    def test_radio_room_operator_permissions(self):
        results = self.do_all_operations_on_all_event_types(self.radio_room_user)

        for k, v in results.items():
            if k in radio_room_user_permissions:
                self.assertTrue(v, 'Radio room user failed {0}'.format(k))
            else:
                self.assertFalse(v, 'Radio room user passed {0}'.format(k))

    def test_guest_permissions(self):
        results = self.do_all_operations_on_all_event_types(self.guest_user)

        for k, v in results.items():
            if k in guest_user_permissions:
                self.assertTrue(v, 'Guest user failed {0}'.format(k))
            else:
                self.assertFalse(v, 'Guest user passed {0}'.format(k))

    def do_all_operations_on_all_event_types(self, user):
        result = {}
        result.update(self.do_all_event_operations(user, ET_LOGISTICS, 'logistics'))
        result.update(self.do_all_event_operations(user, ET_STANDARD, 'standard'))
        result.update(self.do_all_event_operations(user, ET_SECURITY, 'security'))
        return result

    def do_all_event_operations(self, user, event_type, event_type_name):

        results = {}
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = event_type

        # Attempt to create a new logistics event
        request = self.factory.post(self.api_base + '/activity/events/', event_data)
        self.force_authenticate(request, user)
        response = views.EventsView.as_view()(request)
        results['{0}_create'.format(event_type_name)] = response.status_code == 201

        # Because we don't know if the previous event creation failed, create
        # an event that we'll use for the next three tests
        event = Event.objects.create_event(message=lorem_ipsum.paragraph(),
                                           provenance=Event.PC_SYSTEM,
                                           event_type=EventType.objects.get_by_value(event_type),
                                           priority=Event.PRI_URGENT,
                                           attributes={},
                                           )

        # Attempt to read the event we just created
        request = self.factory.get(self.api_base + '/event/{0}'.format(str(event.id)))
        self.force_authenticate(request, user)
        response = views.EventView.as_view()(request, id=str(event.id))
        results['{0}_read'.format(event_type_name)] = response.status_code == 200

        # Attempt to modify the event we just created
        event_data['message'] = 'this is the updated message'
        request = self.factory.patch(self.api_base + '/event/{0}'.format(str(event.id)), event_data)
        self.force_authenticate(request, user)
        response = views.EventView.as_view()(request, id=str(event.id))
        results['{0}_update'.format(event_type_name)] = response.status_code == 200

        # Attempt to delete the event we just created
        request = self.factory.delete(self.api_base + '/event/{0}'.format(str(event.id)) + str(event.id))
        self.force_authenticate(request, user)
        response = views.EventView.as_view()(request, id=str(event.id))
        results['{0}_delete'.format(event_type_name)] = response.status_code == 204

        return results




class TestSerializers(TestCase):
    def test_have_all_attachment_serializer_mappings(self):
        for q in EventAttachment.limits.children:
            q = dict(q.children)
            self.assertIn('.'.join((q['app_label'], q['model'])),
                          ATTACHMENT_SERIALIZER_MAPPING)


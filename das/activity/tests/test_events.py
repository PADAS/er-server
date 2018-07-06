import os
import tempfile
import shutil
import logging
import json
import copy
import collections
import string
import random
import io

from datetime import datetime, timedelta
import pytz

import django.contrib.auth
from django.db import transaction
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.urls import reverse
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from core.tests import BaseAPITest
from choices.models import Choice
from accounts.models import PermissionSet
from activity.models import Event, EventAttachment, EventType, EventCategory,\
    EventRelationship, EventRelationshipType, EventNote, EventsourceEvent, EventSource

from activity.models import get_sentinel_user
from activity import views
from observations.models import Subject
from accounts.serializers import UserDisplaySerializer
from observations.serializers import SubjectSerializer
from utils.html import clean_user_text


logger = logging.getLogger(__name__)

User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'

ET_SECURITY = 'carcass_rep'
ET_MONITORING = 'wildlife_sighting_rep'
ET_LOGISTICS = 'all_posts'

# These permission lists are made up, and do not necessarily correspond to permission sets in production deployments
# All perms user has... all perms
all_permissions = [
    'security_create', 'security_read', 'security_update', 'security_delete',
    'monitoring_create', 'monitoring_read', 'monitoring_update', 'monitoring_delete',
    'logistics_create', 'logistics_read', 'logistics_update', 'logistics_delete']
# Power user has all access to logistics and monitoring events, but can only
# read security events
power_user_permissions = [
    'security_read',
    'monitoring_create', 'monitoring_read', 'monitoring_update', 'monitoring_delete',
    'logistics_create', 'logistics_read', 'logistics_update', 'logistics_delete']
# Radio room users can create any type of event, view/update monitoring and
# logistics events, and delete nothing
radio_room_user_permissions = [
    'security_create',
    'monitoring_create', 'monitoring_read', 'monitoring_update',
    'logistics_create', 'logistics_read', 'logistics_update']

eventsource_user_permissions = [
    'security_create',
    'add_eventsource',
    'change_eventsource',
    'delete_eventsource',
    'create_event_for_eventsource',
]
# Guest users can see logistics events and nothing else
guest_user_permissions = ['logistics_read']

reported_by_permission_set_id = 'b5057387-9f6c-4685-8ec1-46ad29684eea'


class TestEventView(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'event_data_model')
        call_command('loaddata', 'test_events_schema')

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

        self.eventsource_user_no1 = User.objects.create_user(
            'eventsource_user_no1', 'eventsource_user_no1@tempuri.org',
            'eventsource_user_no1', **self.user_const)

        self.eventsource_user_no2 = User.objects.create_user(
            'eventsource_user_no2', 'eventsource_user_no2@tempuri.org',
            'eventsource_user_no2', **self.user_const)

        self.notes_line1_prefix = 'note1 text'
        self.notes_line2_prefix = 'note2 text'
        self.notes = [{'text': self.notes_line1_prefix + lorem_ipsum.paragraph()},
                      {'text': self.notes_line2_prefix + lorem_ipsum.paragraph()}]
        self.event_data = dict(
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517'),
        )

        self.event_data_with_notes = copy.deepcopy(self.event_data)
        self.event_data_with_notes['notes'] = self.notes
        self.sample_event = self.create_event(self.event_data_with_notes)

        self.reported_by_permission_set = PermissionSet.objects.get(
            id=reported_by_permission_set_id)

        self.all_perms_permissionset = PermissionSet.objects.create(
            name='all_perms_set')
        for perm in all_permissions:
            logger.info('permission: %s', perm)
            self.all_perms_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.all_perms_user.permission_sets.add(self.all_perms_permissionset)
        self.all_perms_user.permission_sets.add(
            self.reported_by_permission_set)

        self.power_user_permissionset = PermissionSet.objects.create(
            name='power_set')
        for perm in power_user_permissions:
            self.power_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.power_user.permission_sets.add(self.power_user_permissionset)
        self.power_user.permission_sets.add(self.reported_by_permission_set)

        self.radio_room_user_permissionset = PermissionSet.objects.create(
            name='radio_room_perms_set')
        for perm in radio_room_user_permissions:
            self.radio_room_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.radio_room_user.permission_sets.add(
            self.radio_room_user_permissionset)

        self.guest_user_permissionset = PermissionSet.objects.create(
            name='guest_set')
        for perm in guest_user_permissions:
            self.guest_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        self.guest_user.permission_sets.add(self.guest_user_permissionset)

        self.eventsource_user_permissionset = PermissionSet.objects.create(
            name='eventsource_permissionset')
        for perm in eventsource_user_permissions:
            self.eventsource_user_permissionset.permissions.add(
                Permission.objects.get(codename=perm))
        for u in (self.eventsource_user_no1, self.eventsource_user_no2):
            u.permission_sets.add(self.radio_room_user_permissionset)

        self.user_rep = UserDisplaySerializer().to_representation(self.guest_user)

        self.temporary_folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temporary_folder)

    def create_event(self, event_data, created_by_user=None):
        data = copy.deepcopy(event_data)
        if 'time' in event_data:
            data['event_time'] = DateTimeField().to_internal_value(
                event_data['time'])
            del data['time']
        if isinstance(event_data.get('event_type', None), str):
            data['event_type'] = EventType.objects.get_by_value(
                event_data['event_type'])

        if 'location' in data:
            data['location'] = PointField().to_internal_value(
                data['location'])

        notes = None
        if 'notes' in data:
            notes = data['notes']
            del data['notes']

        data['created_by_user'] = created_by_user if created_by_user else self.radio_room_user

        event = Event.objects.create_event(**data)
        if notes:
            for note in notes:
                EventNote.objects.create_note(
                    event=event, created_by_user=event.created_by_user, **note)

        return event

    def test_find_all_event_type_icons(self):

        for et in EventType.objects.all():
            for p in Event.PRIORITY_CHOICES:
                for s in Event.STATE_CHOICES:
                    image = Event.marker_icon(et.value,
                                              p[0], s[0])
                    image = image[8:]
                    self.assertTrue(finders.find(image),
                                    'Failed to find image: {0}'.format(image))

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
        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_fail_with_nan_location(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_OTHER
        event_data['location'] = dict(latitude="nan", longitude="36.1")
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_not_fail_with_no_location(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_OTHER
        if 'location' in event_data:
            del event_data['location']

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

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
        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_add_note(self):
        note_data = {'text': lorem_ipsum.paragraph()}
        request = self.factory.post(self.api_base
                                    + '/event/{0}/notes'.format(self.sample_event.id),
                                    note_data)
        self.force_authenticate(request, self.all_perms_user)

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
        self.force_authenticate(request, self.no_perms_user)

        response = views.EventNotesView.as_view()(request,
                                                  id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 403)

    def test_update_note_using_patch(self):
        existing_notes = self.sample_event.notes.all()
        note_id = existing_notes[0].id
        note_text = lorem_ipsum.paragraph()
        note_data = {'text': note_text, 'id': note_id}
        event_data = {'notes': [note_data, ]}
        request = self.factory.patch(self.api_base
                                     + '/event/{0}'.format(self.sample_event.id),
                                     event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request,
                                             id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 200)
        response_notes = response.data['notes']
        self.assertEqual([note for note in response_notes if note['id'] == str(
            note_id)][0]['text'], note_text)

    def test_add_note_using_patch(self):
        note_data = {'text': lorem_ipsum.paragraph()}
        event_data = {'notes': [note_data, ]}
        request = self.factory.patch(self.api_base
                                     + '/event/{0}'.format(self.sample_event.id),
                                     event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request,
                                             id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 200)
        response_notes = response.data['notes']
        self.assertTrue(len(list(
            filter(lambda note: note['text'] == note_data['text'], response_notes))) == 1)

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

    def test_create_event_with_empty_message(self):
        event_data = dict(priority=0,
                          event_type=ET_OTHER,
                          message='',
                          comment='')

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_create_event_and_upload_document(self):
        event_data = dict(priority=0,
                          event_type=ET_MONITORING,
                          message='',
                          comment='')

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        event_data['id'] = None

        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertTrue(response_data['id'] is not None)

        my_event_id = response_data['id']

        # Create a simple text file and add it to the event.

        filename = os.path.join(self.temporary_folder, 'some-test-file.txt')
        with open(filename, 'w') as f:
            f.write('The quick brown fox jumps over the lazy dog.')

        with open(filename, "rb") as f:
            path = '/'.join((self.api_base, 'activity',
                             'event', my_event_id, 'files'))
            request = self.factory.post(
                path, {'filecontent.file': f}, format='multipart')

            self.force_authenticate(request, self.all_perms_user)
            response = views.EventFilesView.as_view()(request, id=my_event_id)
            logger.debug(response.data)

        # Make request for the new event and assert that it includes a new
        # document.
        path = '/'.join((self.api_base, 'activity', 'event', my_event_id))
        request = self.factory.get(path, event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request, id=my_event_id)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(len(response.data['files']) == 1)
        # logger.debug(response.data)

    def test_create_event_file_with_permissions(self):
        event_data = dict(priority=0,
                          event_type=ET_MONITORING,
                          message='',
                          comment='')

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        event_data['id'] = None

        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertTrue(response_data['id'] is not None)

        my_event_id = response_data['id']

        # Create a simple text file and add it to the event.

        filename = os.path.join(self.temporary_folder, 'some-test-file.txt')
        with open(filename, 'w') as f:
            f.write('The quick brown fox jumps over the lazy dog.')

        with open(filename, "rb") as f:
            path = '/'.join((self.api_base, 'activity',
                             'event', my_event_id, 'files'))
            request = self.factory.post(
                path, {'filecontent.file': f}, format='multipart')

            self.force_authenticate(request, self.all_perms_user)
            response = views.EventFilesView.as_view()(request, id=my_event_id)
            logger.debug(response.data)

        # Make request for the new event and assert that it includes a new
        # document.
        path = '/'.join((self.api_base, 'activity', 'event', my_event_id))
        request = self.factory.get(path, event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request, id=my_event_id)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(len(response.data['files']) == 1)

        # Grab EventFile.id from response
        event_file_id = response.data['files'][0]['id']

        # Assert that an unauthenticated user may not see the EventFile
        path = '/'.join((self.api_base, 'activity', 'event',
                         my_event_id, 'file', event_file_id))
        request = self.factory.get(path)
        response = views.EventFileView.as_view()(
            request, event_id=my_event_id, filecontent_id=event_file_id)
        self.assertEqual(response.status_code, 401)

        # Assert that a user with permissions may see the EventFile
        request = self.factory.get(path)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventFileView.as_view()(
            request, event_id=my_event_id, filecontent_id=event_file_id)
        self.assertEqual(response.status_code, 200)

        # Assert that a user without permissions may not see the EventFile
        request = self.factory.get(path)
        self.force_authenticate(request, self.guest_user)
        response = views.EventFileView.as_view()(
            request, event_id=my_event_id, filecontent_id=event_file_id)
        self.assertEqual(response.status_code, 403)

    def test_create_event_file_with_permissions(self):
        event_data = dict(priority=0,
                          event_type=ET_MONITORING,
                          message='',
                          comment='')

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        event_data['id'] = None

        response_data = {k: response_data[k] for k in event_data.keys()}
        self.assertTrue(response_data['id'] is not None)

        my_event_id = response_data['id']

        # Create a simple text file and add it to the event.

        filename = os.path.join(self.temporary_folder, 'some-test-file.txt')
        with open(filename, 'w') as f:
            f.write('The quick brown fox jumps over the lazy dog.')

        with open(filename, "rb") as f:
            path = '/'.join((self.api_base, 'activity',
                             'event', my_event_id, 'files'))
            request = self.factory.post(
                path, {'filecontent.file': f}, format='multipart')

            self.force_authenticate(request, self.all_perms_user)
            response = views.EventFilesView.as_view()(request, id=my_event_id)
            logger.debug(response.data)

        # Make request for the new event and assert that it includes a new
        # document.
        path = '/'.join((self.api_base, 'activity', 'event', my_event_id))
        request = self.factory.get(path, event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request, id=my_event_id)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(len(response.data['files']) == 1)

        # Grab EventFile.id from response
        event_file_id = response.data['files'][0]['id']

        # Assert that an unauthenticated user may not see the EventFile
        path = '/'.join((self.api_base, 'activity', 'event',
                         my_event_id, 'file', event_file_id))
        request = self.factory.get(path)
        response = views.EventFileView.as_view()(
            request, event_id=my_event_id, filecontent_id=event_file_id)
        self.assertEqual(response.status_code, 401)

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
        request = self.factory.get(
            self.api_base + '/events?event_category=monitoring&event_category=security')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)

    def test_event_feed_filter_contained_events(self):
        incident_data = copy.deepcopy(self.event_data)
        incident_data['event_type'] = 'incident_collection'

        incident = self.create_event(incident_data)
        contained_event = self.create_event(self.event_data)

        EventRelationship.objects.add_relationship(
            from_event=incident, to_event=contained_event,
            type='contains')

        request = self.factory.get(
            self.api_base + '/events?exclude_contained=true')

        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        response_data = response.data
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            ['failed' for r in response_data['results'] if len(r['is_contained_in'])])

    def test_event_type_category(self):
        request = self.factory.get(
            self.api_base + '/events/eventtypes?category=monitoring&event_category=security')
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
        self.assertIn('monitoring', category_values)
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

        self.assertGreater(
            all_response_data['count'], some_response_data['count'])

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
        request = self.factory.post(
            self.api_base + '/event/' + collection_id + '/relationships', rel_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventRelationshipsView.as_view()(
            request, from_event_id=collection_id)
        logger.debug(response.data)
        self.assertEqual(response.status_code, 201)

    def test_return_new_contained_events(self):

        event_data = json.loads(
            """{"priority":0,"event_type":"incident_collection","message":"test parent message","title":"test parent title","contains":[{"message":"test contains message","title":"SIT-REP","event_type":"contact_rep","time":"2017-06-21 14:43","event_details":{},"priority":0,"reported_by":null},{"message":"second test contains message","title":"Other","event_type":"other","time":"2017-06-21 14:44","event_details":{},"priority":0,"reported_by":null}]}""")
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        event = response.data

        self.assertIn('contains', event)
        self.assertEqual(len(event_data['contains']), len(event['contains']))
        self.assertEqual(event_data['contains'][0]['message'],
                         event['contains'][0]['related_event']['message'])

    def test_event_without_event_type(self):
        event_data = {'message': 'this has no event type', 'priority': '200'}

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 400)

        self.assertTrue('event_type' in response.data,
                        'I cannot find "event_type" in response data.')

    def test_edit_event_title(self):
        event = self.create_event(self.event_data)
        TITLE = ''.join([random.choice(string.ascii_letters +
                                       string.digits + string.punctuation) for x in range(30)])
        update_data = {'title': TITLE}

        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request, id=str(event.id))
        self.assertEqual(response.status_code, 200)

        # clean the generated title from above as that is happening in the ORM
        self.assertEqual(response.data['title'], clean_user_text(
            TITLE, 'test_edit_event_title'))

    def test_event_with_search_filter(self):

        title_text = 'Testing search/filter API'
        search_text = title_text[5:-5]

        event = Event.objects.create_event(title=title_text,
                                           provenance=Event.PC_SYSTEM,
                                           event_type=EventType.objects.get_by_value(
                                               'other'),
                                           priority=Event.PRI_URGENT,
                                           attributes={},
                                           )

        request = self.factory.get(self.api_base + '/event/' + str(event.id))
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request, id=str(event.id))
        self.assertEqual(response.status_code, 200)

        # This is a valid filter (for use in query_string.
        query = {'filter': json.dumps({'text': search_text})}
        request = self.factory.get(self.api_base + '/events', data=query)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        # This will be invalid.
        query = {'filter': {'text': search_text}}
        request = self.factory.get(self.api_base + '/events', data=query)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 500)

    def _export_template_response(self, request):
        return views.EventsExportView.as_view(
            content_type='text/csv',
            template_engine='jinja2',
            template_name='event_export_template.html')(request)

    def test_export_csv(self):
        event = self.create_event(self.event_data_with_notes)
        carcass_data = json.loads("""{"event_details":{"sectionArea":["bbbe77a9-f829-47dd-8a6f-bca76920f706","957a8bfa-ad0d-4b94-bc86-983cab105910"],"team":[],"conservancy":"346f5449-52b0-4b52-9d10-b44b8aa313a6","beginning_of_incident":"2017-10-13 12:00","end_of_incident":"2017-10-14 12:00","details":"interesting details","results_and_findings":"very interesting results and findings","species":"ad26adde-1261-4133-8d3f-a22d12ceae1f","sex":"Male","causeOfDeath":"ab468ffc-9745-4c71-a19d-c34b8c9c3b18"},"event_type":"carcass_rep","priority":200,"title":"Carcass","location":{"latitude":47.65636923655089,"longitude":-122.30770111083983}}""")
        request = self.factory.post(self.api_base + '/events/', carcass_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = self._export_template_response(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue('Priority' in response.rendered_content)
        self.assertTrue('Notes' in response.rendered_content)
        self.assertTrue(self.notes_line2_prefix in response.rendered_content)

    def test_export_csv_with_filter(self):
        event = self.create_event(self.event_data)
        carcass_data = json.loads("""{"event_details":{"sectionArea":["bbbe77a9-f829-47dd-8a6f-bca76920f706","957a8bfa-ad0d-4b94-bc86-983cab105910"],"team":[],"conservancy":"346f5449-52b0-4b52-9d10-b44b8aa313a6","beginning_of_incident":"2017-10-13 12:00","end_of_incident":"2017-10-14 12:00","details":"interesting details","results_and_findings":"very interesting results and findings","species":"ad26adde-1261-4133-8d3f-a22d12ceae1f","sex":"Male","causeOfDeath":"ab468ffc-9745-4c71-a19d-c34b8c9c3b18"},"event_type":"carcass_rep","priority":200,"title":"Carcass","location":{"latitude":47.65636923655089,"longitude":-122.30770111083983}}""")
        request = self.factory.post(self.api_base + '/events/', carcass_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export?state=active&filter=%7B%22text%22:%22carcass%22%7D"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = self._export_template_response(request)

        self.assertEqual(response.status_code, 200)

    def test_reported_by_filtering(self):
        reported_by_users = list(Event.objects.get_reported_by_for_provenance(
            Event.PC_STAFF))

        self.assertEquals(2, len(reported_by_users))
        self.assertIn(self.all_perms_user, reported_by_users)
        self.assertIn(self.power_user, reported_by_users)

    def test_add_event_category(self):
        value = 'new'
        display = 'new event permissions'
        EventCategory.objects.create(value=value, display=display)

        for operation in ['create', 'read', 'update', 'delete']:
            codename = '{0}_{1}'.format(value, operation)
            self.assertIsNotNone(Permission.objects.get(codename=codename))

    def test_all_perms_user_permissions(self):
        results = self.do_all_operations_on_all_event_types(
            self.all_perms_user)

        for k, v in results.items():
            self.assertTrue(v, 'All perms user failed {0}'.format(k))

    def test_power_user_permissions(self):
        results = self.do_all_operations_on_all_event_types(self.power_user)

        for k, v in results.items():
            if k in power_user_permissions:
                self.assertTrue(v, 'Power user failed {0}'.format(k))
            else:
                self.assertFalse(v, 'Power user passed {0}'.format(k))

    def test_radio_room_operator_create_but_not_view(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_SECURITY
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.radio_room_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        self.assertDictEqual(response_data, {})

    def test_radio_room_operator_permissions(self):
        results = self.do_all_operations_on_all_event_types(
            self.radio_room_user)

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
        result.update(self.do_all_event_operations(
            user, ET_LOGISTICS, 'logistics'))
        result.update(self.do_all_event_operations(
            user, ET_MONITORING, 'monitoring'))
        result.update(self.do_all_event_operations(
            user, ET_SECURITY, 'security'))
        return result

    def do_all_event_operations(self, user, event_type, event_type_name):

        results = {}
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = event_type

        # Attempt to create a new logistics event
        request = self.factory.post(
            self.api_base + '/activity/events/', event_data)
        self.force_authenticate(request, user)
        response = views.EventsView.as_view()(request)
        results['{0}_create'.format(event_type_name)
                ] = response.status_code == 201

        # Because we don't know if the previous event creation failed, create
        # an event that we'll use for the next three tests
        event = Event.objects.create_event(message=lorem_ipsum.paragraph(),
                                           provenance=Event.PC_SYSTEM,
                                           event_type=EventType.objects.get_by_value(
                                               event_type),
                                           priority=Event.PRI_URGENT,
                                           attributes={},
                                           )

        # Attempt to read the event we just created
        request = self.factory.get(
            self.api_base + '/event/{0}'.format(str(event.id)))
        self.force_authenticate(request, user)
        response = views.EventView.as_view()(request, id=str(event.id))
        results['{0}_read'.format(event_type_name)
                ] = response.status_code == 200

        # Attempt to modify the event we just created
        event_data['message'] = 'this is the updated message'
        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event.id)), event_data)
        self.force_authenticate(request, user)
        response = views.EventView.as_view()(request, id=str(event.id))
        results['{0}_update'.format(event_type_name)
                ] = response.status_code == 200

        # Attempt to delete the event we just created
        request = self.factory.delete(
            self.api_base + '/event/{0}'.format(str(event.id)) + str(event.id))
        self.force_authenticate(request, user)
        response = views.EventView.as_view()(request, id=str(event.id))
        results['{0}_delete'.format(event_type_name)
                ] = response.status_code == 204

        return results

    #
    # EventSource tests.
    def test_add_eventsource(self):

        eventsource_data = {
            'external_event_type': 'carcass',
            'display': 'DAS: Carcass',
            # 'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }
        request = self.factory.post(self.api_base
                                    + '/eventsources', eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourcesView.as_view()(request,)
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        response_data = {k: response_data[k] for k in eventsource_data.keys()}
        self.assertDictEqual(response_data, eventsource_data)

    def test_add_eventsource_twice(self):

        eventsource_data = {
            'external_event_type': 'carcass',
            'display': 'DAS: Carcass',
            # 'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }
        request = self.factory.post(self.api_base
                                    + '/eventsources', eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourcesView.as_view()(request,)
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        request = self.factory.post(self.api_base
                                    + '/eventsources', eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourcesView.as_view()(request,)
        self.assertEqual(response.status_code, 400)
        response_data = response.data

    def test_eventsourceview_update_permission_denied(self):
        eventsource_data = {
            'external_event_type': 'carcass',
            'display': 'DAS: Carcass',
            'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }
        request = self.factory.post(self.api_base
                                    + '/eventsources', eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(request,)
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        # esid = response_data['id']

        eventsource_patch = {'additional': {'a': 1, 'b': 'some string'}}
        request = self.factory.patch(f'{self.api_base}event/eventsource/{eventsource_data["external_event_type"]}',
                                     eventsource_patch)
        self.force_authenticate(request, self.eventsource_user_no2)

        response = views.EventSourceView.as_view()(
            request, external_event_type=eventsource_data['external_event_type'])
        self.assertEqual(response.status_code, 403)

    def test_update_eventsource_using_patch(self):

        eventsource_data = {
            'external_event_type': 'carcass',
            'display': 'DAS: Carcass',
            'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }
        request = self.factory.post(self.api_base
                                    + '/eventsources', eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(request,)
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        esid = response_data['id']

        eventsource_patch = {'additional': {'a': 1, 'b': 'some string'}}
        request = self.factory.patch(f'{self.api_base}event/eventsource/{esid}', eventsource_patch)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourceView.as_view()(request,
                                                   id=str(esid))
        self.assertEqual(response.status_code, 200)

        print(json.dumps(response.data, indent=2, default=str))

        additional_data = response.data.get('additional', {})
        self.assertDictEqual(additional_data, eventsource_patch['additional'])

    def test_add_event_with_external_event_type(self):

        external_event_type = 'smart-carcass'
        eventsource_data = {
            'external_event_type': external_event_type,
            'display': 'DAS: Carcass',
            'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }

        request = self.factory.post(self.api_base
                                    + '/eventsources', eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(request,)
        self.assertEqual(response.status_code, 201)

        esid = response.data['id']
        external_event_id = 'asdfioaasfseiuro11414sfa'
        # Create an event with an "External Event ID"
        event_title = 'Some arbirtrary event title.'
        event_data = {
            "event_details": {
                "attributes": [
                    {"key": "a", "value": "1"}
                ]
            },

            "external_event_type": external_event_type,
            "priority": 100,
            "title": event_title,
            "external_event_id": external_event_id,
            "location": {"latitude": 39.4, "longitude": -117.5},
            "time": datetime.now(tz=pytz.utc).isoformat(),
        }

        request = self.factory.post(f'{self.api_base}/events', event_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventsView.as_view()(request,)
        self.assertEqual(response.status_code, 201)

        eselist = EventsourceEvent.objects.filter(
            eventsource_id=esid, external_event_id=external_event_id)

        self.assertEqual(eselist.count(), 1)

        self.assertEqual(
            eselist[0].eventsource.external_event_type, external_event_type)
        self.assertEqual(eselist[0].event.title, event_title)

    def test_add_event_with_external_event_type_and_no_permissions(self):

        eventsource_data = {
            'external_event_type': 'smart_carcass_report',
            'display': 'DAS: Carcass',
            'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }

        request = self.factory.post(self.api_base
                                    + '/eventsources', eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(request,)
        self.assertEqual(response.status_code, 201)

        # Create an event with an "External Event ID"
        event_data = {
            "event_details": {
                "attributes": [
                    {"key": "a", "value": "1"}
                ]
            },

            "external_event_type": "smart_carcass_report",
            "priority": 100,
            "title": "Test External Event",
            "location": {"latitude": 1.4, "longitude": 37.5},
            "time": datetime.now(tz=pytz.utc).isoformat(),
        }

        request = self.factory.post(f'{self.api_base}/events', event_data)
        self.force_authenticate(request, self.eventsource_user_no2)

        response = views.EventsView.as_view()(request,)

        # Expect 400 Bad Request, because the given external_event_type will
        # not be found for this user.
        self.assertEqual(response.status_code, 400)

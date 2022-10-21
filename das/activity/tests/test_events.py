import copy
import csv
import io
import json
import logging
import os
import random
import shutil
import string
import tempfile
from datetime import datetime, timedelta
from unittest import mock
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
import pytz
from drf_extra_fields.geo_fields import PointField
from kombu import Connection

import django.contrib.auth
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point, Polygon
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import dateparse, lorem_ipsum, timezone
from rest_framework.fields import DateTimeField

from accounts.models import PermissionSet
from accounts.serializers import UserDisplaySerializer
from activity import views
from activity.models import (Event, EventCategory, EventDetails, EventNote,
                             EventProvider, EventRelationship, EventSource,
                             EventsourceEvent, EventType, Patrol,
                             TSVectorModel, parse_date_range)
from activity.serializers import EventDetailsSerializer
from activity.tasks import automatically_update_event_state
from activity.tests import schema_examples
from choices.models import Choice, DynamicChoice
from client_http import HTTPClient
from core.tests import BaseAPITest
from observations.models import Subject, SubjectSubType, SubjectType
from observations.serializers import SubjectSerializer
from utils.categories import get_categories_and_geo_categories
from utils.gis import convert_to_point
from utils.html import clean_user_text
from utils.schema_utils import format_key_for_title
from utils.tests_tools import BaseTestToolMixin

logger = logging.getLogger(__name__)

User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'

ET_CARCASS = 'carcass_rep'
ET_SECURITY = ET_CARCASS
ET_MONITORING = 'wildlife_sighting_rep'
ET_LOGISTICS = 'all_posts'

# These permission lists are made up, and do not necessarily correspond to permission sets in production deployments
# All perms user has... all perms
all_permissions = [
    'security_create', 'security_read', 'security_update', 'security_delete',
    'monitoring_create', 'monitoring_read', 'monitoring_update',
    'monitoring_delete',
    'logistics_create', 'logistics_read', 'logistics_update',
    'logistics_delete',
]
# Power user has all access to logistics and monitoring events, but can only
# read security events
power_user_permissions = [
    'security_read',
    'monitoring_create', 'monitoring_read', 'monitoring_update',
    'monitoring_delete',
    'logistics_create', 'logistics_read', 'logistics_update',
    'logistics_delete',

]
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


def fake_get_pool():
    return Connection("memory://").Pool(20)


class TestEventView(BaseTestToolMixin, BaseAPITest):
    user_const = dict(last_name='last', first_name='first')

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'event_data_model')
        call_command('loaddata', 'test_events_schema')

        self.no_perms_user = User.objects.create_user('no_perms_user',
                                                      'das_no_perms@vulcan.com',
                                                      'noperms',
                                                      **self.user_const)
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
        self.notes = [
            {'text': self.notes_line1_prefix + lorem_ipsum.paragraph()},
            {'text': self.notes_line2_prefix + lorem_ipsum.paragraph()}]
        self.event_data = dict(
            title="Test Event",
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude=40.1353, latitude=-1.891517),
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

        self.user_rep = UserDisplaySerializer().to_representation(
            self.guest_user)

        self.temporary_folder = tempfile.mkdtemp()
        self.now = datetime.now(tz=pytz.utc)
        self.start_of_today = self.now.replace(
            hour=0, minute=0, second=0, microsecond=0)
        self.end_of_today = self.start_of_today + \
            timedelta(hours=23, minutes=59, seconds=59)
        self.api_path = f"activity/event/{self.sample_event.pk}/"
        self.view = views.EventView

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

        data[
            'created_by_user'] = created_by_user if created_by_user else self.radio_room_user

        event = Event.objects.create_event(**data)
        if notes:
            for note in notes:
                EventNote.objects.create_note(
                    event=event, created_by_user=event.created_by_user, **note)

        return event

    def test_return_event_details(self):
        request = self.factory.get(self.api_base + '/event/')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request,
                                             id=str(self.sample_event.id))
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
        response_data = {k: response.data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_created_event_status(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_OTHER
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        id = response.data.get('id')
        event = Event.objects.get(id=id)
        self.assertEqual(event.state, "new")

    def test_create_multiple_events_on_a_single_api_call(self):
        prev_count = Event.objects.count()
        request = self.factory.post(
            self.api_base + '/events/', [self.event_data, self.event_data])
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        self.assertEqual(2, len(response.data))
        self.assertEqual(Event.objects.count(), prev_count + 2)

    def test_get_new_event_without_event_write_permissions(self):
        request = self.factory.get(self.api_base + '/events/')
        self.force_authenticate(request, self.no_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])

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

    def test_not_fail_with_emptystring_location(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_OTHER
        event_data['lcation'] = ""

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

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

    def test_bad_request_with_empty_string_location(self):
        event_data = dict(event_details={}, event_type=ET_OTHER, icon_id=ET_OTHER,
                          is_collection=False, location="", priority=100, time="2020-06-11T18:57:12.629Z")

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 400)

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
        response_data = {k: response.data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_create_new_message_only_event(self):
        event_data = {'message': lorem_ipsum.sentence(),
                      'event_type': ET_OTHER,
                      }
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = {k: response.data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

    def test_add_note(self):
        note_data = {'text': lorem_ipsum.paragraph()}
        request = self.factory.post(self.api_base
                                    + '/event/{0}/notes'.format(
                                        self.sample_event.id),
                                    note_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventNotesView.as_view()(request,
                                                  id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k: response_data[k] for k in note_data.keys()}
        self.assertDictEqual(response_data, note_data)

        note_data['id'] = response.data["id"]

        # now we delete the note
        request = self.factory.delete(
            self.api_base + f'/event/{str(self.sample_event.id)}/note/{note_data["id"]}')
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventNoteView.as_view()(
            request, id=str(self.sample_event.id), note_id=note_data["id"])
        assert response.status_code == 204

    def test_add_note_but_not_delete(self):
        note_data = {'text': lorem_ipsum.paragraph()}
        request = self.factory.post(self.api_base
                                    + '/event/{0}/notes'.format(
                                        self.sample_event.id),
                                    note_data)
        self.force_authenticate(request, self.radio_room_user)

        response = views.EventNotesView.as_view()(request,
                                                  id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        response_data = {k: response_data[k] for k in note_data.keys()}
        self.assertDictEqual(response_data, note_data)

        note_data['id'] = response.data["id"]

        # now we delete the note
        request = self.factory.delete(
            self.api_base + f'/event/{str(self.sample_event.id)}/note/{note_data["id"]}')
        self.force_authenticate(request, self.radio_room_user)
        response = views.EventNoteView.as_view()(
            request, id=str(self.sample_event.id), note_id=note_data["id"])
        assert response.status_code == 403

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
                                     + '/event/{0}'.format(
                                         self.sample_event.id),
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
                                     + '/event/{0}'.format(
                                         self.sample_event.id),
                                     event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request,
                                             id=str(self.sample_event.id))
        self.assertEqual(response.status_code, 200)
        response_notes = response.data['notes']
        self.assertTrue(len(list(
            filter(lambda note: note['text'] == note_data['text'],
                   response_notes))) == 1)

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
        response_data = {k: response.data[k] for k in event_data.keys()}
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

        event_data['id'] = None

        response_data = {k: response.data[k] for k in event_data.keys()}
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
            logger.debug(response_data)

        # Make request for the new event and assert that it includes a new
        # document.
        path = '/'.join((self.api_base, 'activity', 'event', my_event_id))
        request = self.factory.get(path, response_data)
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

        # Make request for the new event and assert that it includes a new
        # document.
        path = '/'.join((self.api_base, 'activity', 'event', my_event_id))
        request = self.factory.get(path)
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

    def test_create_event_file_with_permissions_unauthorized(self):
        event_data = dict(priority=0,
                          event_type=ET_MONITORING,
                          message='',
                          comment='')

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        event_data['id'] = None

        response_data = {k: response.data[k] for k in event_data.keys()}
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
            logger.debug(response_data)

        # Make request for the new event and assert that it includes a new
        # document.
        path = '/'.join((self.api_base, 'activity', 'event', my_event_id))
        request = self.factory.get(path, response_data)
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
        assert 'enum' not in response_data['properties']['patrol_segments']

    @patch("activity.models.is_banned")
    def test_event_feed(self, is_banned):
        is_banned.return_value = False
        request = self.factory.get(self.api_base + '/events')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        response.data
        self.assertEqual(response.status_code, 200)

    @patch("activity.models.is_banned")
    def test_event_feed_category(self, is_banned):
        is_banned.return_value = False
        request = self.factory.get(
            self.api_base + '/events?event_category=monitoring&event_category=security')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        response.data
        self.assertEqual(response.status_code, 200)

    @patch("activity.models.is_banned")
    def test_event_feed_filter_contained_events(self, is_banned):
        is_banned.return_value = False
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
            ['failed' for r in response_data['results'] if
             len(r['is_contained_in'])])

    def test_event_type_category(self):
        request = self.factory.get(
            self.api_base + '/events/eventtypes?category=monitoring&event_category=security')
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventTypesView.as_view()(request)
        response.data
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
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

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

    def test_event_revision(self):
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
        self.assertEqual(len(response_data['updates']), 2)

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

    def test_update_event_remove_location(self):
        event = self.create_event(self.event_data)
        update_data = {'location': None}

        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event.id)),
            update_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request,
                                             id=str(event.id))
        self.assertEqual(response.status_code, 200)
        response_data = response.data
        self.assertEqual(response_data['location'], update_data['location'])

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
        collection_id = response.data['id']
        response_data = {k: response.data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_LOGISTICS
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        report_id = response.data['id']
        response_data = {k: response.data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

        rel_data = {'to_event_id': report_id, 'type': 'contains'}
        request = self.factory.post(
            self.api_base + '/event/' + collection_id + '/relationships',
            rel_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventRelationshipsView.as_view()(
            request, from_event_id=collection_id)
        logger.debug(response_data)
        self.assertEqual(response.status_code, 201)

    def test_collection_event_contains_with_different_user_permissions(self):
        # Create Event A, B and collection
        collection_et = EventType.objects.get_by_value('incident_collection')
        logistics_et = EventType.objects.get_by_value(ET_LOGISTICS)
        monitoring_et = EventType.objects.get_by_value(ET_MONITORING)

        event_collection = Event.objects.create(
            title="incident_collection_event", event_type=collection_et)
        event_a = Event.objects.create(
            title="Event_A", event_type=logistics_et)
        event_b = Event.objects.create(
            title="Event_B", event_type=monitoring_et)

        EventRelationship.objects.add_relationship(
            event_collection, event_a, 'contains')
        EventRelationship.objects.add_relationship(
            event_collection, event_b, 'contains')

        request = self.factory.get(
            self.api_base + '/event/' + str(event_collection.id))
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventView.as_view()(request, id=str(event_collection.id))

        contained_events = response.data.get("contains")

        # All perms user can view all contained events (A and B)
        assert len(contained_events) == 2
        contained_event_titles = [k.get('related_event').get(
            'title') for k in contained_events]

        assert contained_event_titles == ["Event_A", "Event_B"]

        # Grant user security_read permissions

        self.guest_user_permissionset.permissions.add(
            Permission.objects.get(codename="security_read"))

        self.guest_user.permission_sets.add(self.guest_user_permissionset)

        new_request = self.factory.get(
            self.api_base + '/event/' + str(event_collection.id))
        self.force_authenticate(new_request, self.guest_user)
        new_response = views.EventView.as_view()(
            new_request, id=str(event_collection.id))

        contained_events = new_response.data.get("contains")

        # Guest user can view only the collection and event_A (security and logistics)
        assert len(contained_events) == 1
        contained_event_titles = [k.get('related_event').get(
            'title') for k in contained_events]

        assert contained_event_titles != ["Event_A", "Event_B"]
        assert "Event_B" not in contained_event_titles

    def test_return_new_contained_events(self):

        event_data = json.loads(
            """{"priority":0,"event_type":"incident_collection","message":"test parent message","title":"test parent title","contains":[{"message":"test contains message","title":"SIT-REP","event_type":"contact_rep","time":"2017-06-21 14:43","event_details":{},"priority":0,"reported_by":null},{"message":"second test contains message","title":"Other","event_type":"other","time":"2017-06-21 14:44","event_details":{},"priority":0,"reported_by":null}]}""")
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        event = response.data
        self.assertEqual(len(event_data['contains']), len(event['contains']))
        self.assertEqual(event_data['contains'][0]['message'],
                         event['contains'][0]['related_event']['message'])

    def test_event_without_event_type(self):
        event_data = {'message': 'this has no event type', 'priority': '200'}

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertTrue('event_type' in response.data[0][0],
                        'Event type must be provided.')

    def test_edit_event_title(self):
        event = self.create_event(self.event_data)
        TITLE = ''.join([random.choice(string.ascii_letters +
                                       string.digits + string.punctuation) for x
                         in range(30)])
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

    def test_edit_event_details(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['event_type'] = ET_CARCASS
        event_data['event_details'] = {"carcassrep_species": "elephant", "carcassrep_sex": "male", "carcassrep_ageofanimal": "adult",
                                       "carcassrep_ageofcarcass": "fresh", "carcassrep_trophystatus": "intact", "carcassrep_causeofdeath": "naturaldisease"}
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        event_id = response.data['id']

        update_data = {'event_details': event_data['event_details']}
        update_data['event_details']['carcassrep_species'] = 'baboon'

        request = self.factory.patch(
            self.api_base + '/event/{0}'.format(str(event_id)),
            update_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventView.as_view()(request, id=str(event_id))
        self.assertEqual(response.status_code, 200)

        # clean the generated title from above as that is happening in the ORM
        self.assertIn('Species', response.data['updates'][0]['message'])

    @patch("activity.models.is_banned")
    def test_event_with_search_filter(self, is_banned):
        is_banned.return_value = False
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
        carcass_data = json.loads(
            """{"event_type":"carcass_rep","priority":200,"event_details":{"carcassrep_species":"elephant","carcassrep_sex":"male","carcassrep_ageofanimal":"adult","carcassrep_ageofcarcass":"fresh","carcassrep_trophystatus":"intact","carcassrep_causeofdeath":"naturaldisease"},"location":{"latitude":"0.28118","longitude":"37.38544"}}""")

        request = self.factory.post(self.api_base + '/events/', carcass_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue('Priority' in response.content.decode("utf-8"))
        self.assertTrue('Notes' in response.content.decode("utf-8"))
        self.assertTrue(
            self.notes_line2_prefix in response.content.decode("utf-8"))

    def test_export_csv_with_qparam_value_cols_true(self):
        carcass_data = json.loads(
            """{"event_type":"carcass_rep","priority":200,"event_details":{"carcassrep_species":"elephant","carcassrep_sex":"male","carcassrep_ageofanimal":"adult","carcassrep_ageofcarcass":"fresh","carcassrep_trophystatus":"intact","carcassrep_causeofdeath":"naturaldisease"},"location":{"latitude":"0.28118","longitude":"37.38544"}}""")

        request = self.factory.post(self.api_base + '/events/', carcass_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export?value_cols=true"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue('Priority' in response.content.decode("utf-8"))
        self.assertTrue('Notes' in response.content.decode("utf-8"))
        self.assertTrue(
            'carcassrep_species' in response.content.decode("utf-8"))
        self.assertTrue(
            self.notes_line2_prefix in response.content.decode("utf-8"))

    def test_export_events_with_invalid_et_schema(self):
        url = """/activity/events/export?value_cols=true"""
        # Update eventschema to have an invalid schema

        EventType.objects.filter(value=ET_OTHER).update(schema={})
        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        assert response.status_code == 200

    def convert_rendered_csv_to_dict(self, content):
        reader = csv.DictReader(io.StringIO(content))
        return [row for row in reader]

    def test_collection_report_id_exported_as_parent_event_serial_number(self):
        collection_event_data = copy.deepcopy(self.event_data)
        collection_event_data['reported_by'] = self.user_rep
        collection_event_data["message"] = ""
        collection_event_data['provenance'] = Event.PC_STAFF
        collection_event_data['title'] = "Testing Collection Report ID"
        collection_event_data['event_type'] = 'incident_collection'
        request = self.factory.post(
            self.api_base + '/events/', collection_event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        response_data = response.data
        collection_serial_number = response_data.get('serial_number')
        collection_id = response_data['id']
        response_data = {k: response_data[k]
                         for k in collection_event_data.keys()}
        self.assertDictEqual(response_data, collection_event_data)
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data["message"] = ""
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = ET_LOGISTICS
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        report_id = response.data['id']
        event_serial_number = response.data['serial_number']
        response_data = {k: response.data[k] for k in event_data.keys()}
        self.assertDictEqual(response_data, event_data)

        rel_data = {'to_event_id': report_id, 'type': 'contains'}
        request = self.factory.post(
            self.api_base + '/event/' + collection_id + '/relationships',
            rel_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventRelationshipsView.as_view()(
            request, from_event_id=collection_id)
        logger.debug(response_data)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        events_report = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))
        # get the last event
        event = {}
        for ev in events_report:
            if ev.get('Report_Id', "") == str(event_serial_number):
                event = ev
        parent_ids = event.get('Collection_Report_IDs', "").split(';')
        the_parent_id = int(parent_ids[0]) if parent_ids else None
        self.assertEqual(the_parent_id, collection_serial_number)

    def test_export_csv_with_filter(self):
        carcass_data = json.loads(
            """{"event_details":{"sectionArea":["bbbe77a9-f829-47dd-8a6f-bca76920f706","957a8bfa-ad0d-4b94-bc86-983cab105910"],"team":[],"conservancy":"346f5449-52b0-4b52-9d10-b44b8aa313a6","beginning_of_incident":"2017-10-13 12:00","end_of_incident":"2017-10-14 12:00","details":"interesting details","results_and_findings":"very interesting results and findings","species":"ad26adde-1261-4133-8d3f-a22d12ceae1f","sex":"Male","causeOfDeath":"ab468ffc-9745-4c71-a19d-c34b8c9c3b18"},"event_type":"carcass_rep","priority":200,"title":"Carcass","location":{"latitude":47.65636923655089,"longitude":-122.30770111083983}}""")
        request = self.factory.post(self.api_base + '/events/', carcass_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        assert response.status_code == 201

        url = """/activity/events/export?state=active&filter=%7B%22text%22:%22carcass%22%7D"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)

        assert response.status_code == 200

    def test_export_reports_with_create_date_filter(self):
        url = """/activity/events/export"""
        q_params = json.dumps(
            {"create_date": {
                "lower": self.start_of_today.isoformat(), "upper": self.end_of_today.isoformat()}})

        request = self.factory.get(self.api_base + url, {'filter': q_params})
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_dict = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))
        assert len(rendered_dict) == 1

        tomorrow = self.now + timedelta(days=1)
        q_params = json.dumps({"create_date": {"lower": tomorrow.isoformat()}})

        request = self.factory.get(self.api_base + url, {'filter': q_params})
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_dict = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))
        assert len(rendered_dict) == 0

    @patch("activity.models.is_banned")
    def test_filter_events_with_update_date(self, is_banned):
        is_banned.return_value = False
        url = """/activity/events?"""
        q_params = json.dumps(
            {"update_date": {
                "lower": self.start_of_today.isoformat(), "upper": self.end_of_today.isoformat()}})

        request = self.factory.get(self.api_base + url, {'filter': q_params})
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)

        q_params = json.dumps(
            {"update_date": {
                "lower": self.start_of_today.isoformat()}})

        request = self.factory.get(self.api_base + url, {'filter': q_params})
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)

    def test_export_filter_on_incident_associated_reports(self):
        incident_data = copy.deepcopy(self.event_data)
        incident_data['event_type'] = 'incident_collection'
        incident_data['title'] = 'Test incident collection'

        request = self.factory.post(self.api_base + '/events/', incident_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        collection_id = response.data['id']

        request = self.factory.post(
            self.api_base + '/events/', self.event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        report_id = response.data['id']

        rel_data = {'to_event_id': report_id, 'type': 'contains'}
        request = self.factory.post(
            self.api_base + '/event/' + collection_id + '/relationships',
            rel_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventRelationshipsView.as_view()(
            request, from_event_id=collection_id)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""
        filter_spec = json.dumps({'text': incident_data['title']})
        request = self.factory.get(
            self.api_base + url, {'filter': filter_spec})

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_dict = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))
        report_names = [report["Title"] for report in rendered_dict]

        # 2 reports returned, Incident and contained report
        self.assertEqual(2, len(report_names))
        self.assertTrue(all(x in report_names for x in [
                        incident_data['title'],  self.event_data['title']]))

    def test_export_includes_all_event_detail_fields(self):

        request = self.factory.post(
            self.api_base + '/events/', self.event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        et_schema = """
            {
            "schema":
            {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Locust Absence Report (locustabsence_rep)",

                "type": "object",

                "properties":
                {

                "repObserver": {
                    "type": "string",
                    "title": "Report Observer"
                },
                "repHASurveyed": {
                    "type": "number",
                    "title": "HA Surveyed",
                    "minimum": 0
                },
                "repCountry": {
                    "type": "string",
                    "title": "Country",
                    "enum": {{enum___countries___values}},
                    "enumNames": {{enum___countries___names}}
                },
                "repLocation": {
                    "type": "string",
                    "title": "Report Location"
                },
                "eLocust-key": {
                    "type": "string",
                    "title": "e-locust-key"
                }
            }
        },
        "definition": [

            {
            "type": "fieldset",
            "title": "Report Info",
            "htmlClass": "col-lg-12",
            "items": []
            },
            {
            "type": "fieldset",
            "htmlClass": "col-lg-6",
            "items": [
                "repObserver",
                "repHASurveyed",
                "",
                "",
                "",
                "",
                "",
                ""
            ]
            },
            {
            "type": "fieldset",
            "htmlClass": "col-lg-6",
            "items": [
                "repCountry",
                "repLocation",
                "",
                "",
                "",
                "",
                ""
            ]
            },

            {
            "type": "fieldset",
            "title": "No Locusts Reported",
            "htmlClass": "col-lg-12",
            "items": []
            }

        ]
        }
        """
        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        EventDetails.objects.create(
            data={"event_details": {
                "eLocust-key": "716c9a58ca0b9a7bf3351517d7393b49", "repObserver": "an observer"}},
            event=self.sample_event)

        url = """/activity/events/export"""
        filter_spec = json.dumps({'text': "event"})
        request = self.factory.get(
            self.api_base + url, {'filter': filter_spec})

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_content = response.content.decode("utf-8")
        rendered_dict = self.convert_rendered_csv_to_dict(rendered_content)
        report_headers = rendered_dict[0].keys()

        # All hidden fields returned indipendently in the export headers
        test_headers = set(["e-locust-key", "Report_Observer"])
        assert test_headers == set(report_headers) & test_headers

        # All hidden fields values returned in export content
        self.assertTrue(all(x in rendered_content for x in [
                        "716c9a58ca0b9a7bf3351517d7393b49", "an observer"]))

    def test_export_includes_all_event_detail_fields_no_title(self):

        event_data = copy.deepcopy(self.event_data)
        event_data['title'] = 'Event details No Title Test'

        request = self.factory.post(
            self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)

        et_schema = """
            {
                "schema":
                {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "title": "Locust Absence Report (locustabsence_rep)",

                    "type": "object",

                    "properties":
                    {

                    "repObserver": {
                        "type": "string",
                        "title": "Report Observer"
                    },
                    "repHASurveyed": {
                        "type": "number",
                        "title": "HA Surveyed",
                        "minimum": 0
                    },
                    "repCountry": {
                        "type": "string",
                        "title": "Country",
                        "enum": {{enum___countries___values}},
                        "enumNames": {{enum___countries___names}}
                    },
                    "repLocation": {
                        "type": "string",
                        "title": "Report Location"
                    },
                    "eLocust-key": {
                        "type": "string"
                    }
                }
            },
            "definition": [

                {
                "type": "fieldset",
                "title": "Report Info",
                "htmlClass": "col-lg-12",
                "items": []
                },
                {
                "type": "fieldset",
                "htmlClass": "col-lg-6",
                "items": [
                    "repObserver",
                    "repHASurveyed",
                    "",
                    "",
                    "",
                    "",
                    "",
                    ""
                ]
                },
                {
                "type": "fieldset",
                "htmlClass": "col-lg-6",
                "items": [
                    "repCountry",
                    "repLocation",
                    "",
                    "",
                    "",
                    "",
                    ""
                ]
                },

                {
                "type": "fieldset",
                "title": "No Locusts Reported",
                "htmlClass": "col-lg-12",
                "items": []
                }

            ]
            }
        """
        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        details = EventDetails.objects.get(event_id=response.data['id'])
        details.data = {"event_details": {"eLocust-key": "e locust id key",
                                          "repObserver": "an observer"}}
        details.save()

        url = """/activity/events/export"""
        filter_spec = json.dumps({'text': "event"})
        request = self.factory.get(
            self.api_base + url, {'filter': filter_spec})

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_content = response.content.decode("utf-8")
        rendered_dict = self.convert_rendered_csv_to_dict(rendered_content)
        report_headers = rendered_dict[0].keys()

        # All hidden fields returned indipendently in the export headers
        test_headers = set([format_key_for_title(
            "eLocust-key").replace(' ', '_'), "Report_Observer"])
        assert test_headers == set(report_headers) & test_headers

        # All hidden fields values returned in export content
        row = [row for row in rendered_dict if row['Title']
               == event_data['title']][0]
        test_rendered_content = set(["e locust id key", "an observer"])
        assert test_rendered_content == set(
            row.values()) & test_rendered_content

    def test_export_csv_with_line_feed(self):

        currentactivity = '\n'.join(
            (lorem_ipsum.paragraph(), lorem_ipsum.paragraph()))
        sitrep_data = json.loads(
            """{"event_details":{"sitrep_currentactivity":"interesting details"},"event_type":"sit_rep","priority":200,"title":"SitRep","location":{"latitude":47.65636923655089,"longitude":-122.30770111083983}}""")
        sitrep_data['event_details']['sitrep_currentactivity'] = currentactivity

        request = self.factory.post(self.api_base + '/events/', sitrep_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.content.decode("utf-8").splitlines()), 3)

    def test_reported_by_filtering(self):
        reported_by_users = list(Event.objects.get_reported_by_for_provenance(
            Event.PC_STAFF))

        self.assertEqual(2, len(reported_by_users))
        self.assertIn(self.all_perms_user, reported_by_users)
        self.assertIn(self.power_user, reported_by_users)

    def test_add_event_category(self):
        value = 'new'
        display = 'new event permissions'
        event_category = EventCategory.objects.create(
            value=value, display=display)

        expected_permissionset_name = event_category.auto_permissionset_name
        permissionset_list = PermissionSet.objects.filter(
            name=expected_permissionset_name)

        self.assertEqual(permissionset_list.count(), 1)

        for operation in ['create', 'read', 'update', 'delete']:
            codename = '{0}_{1}'.format(value, operation)
            permission_list = Permission.objects.filter(codename=codename)

            self.assertEqual(permission_list.count(), 1)
            self.assertTrue(
                permission_list[0] in permissionset_list[0].permissions.all())

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
    def test_all_perms_user_permissions(self):
        results = self.do_all_operations_on_all_event_types(
            self.all_perms_user)

        for k, v in results.items():
            self.assertTrue(v, 'All perms user failed {0}'.format(k))

    @mock.patch("das_server.pubsub.get_pool", fake_get_pool)
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
        self.assertEqual(len(response.data), 1)

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
        event_note_data = dict(text=lorem_ipsum.paragraph())

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
        try:
            result = response.data["data"] != []
        except:
            result = response.status_code == 200
        results['{0}_read'.format(event_type_name)] = result

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

    def test_eventprovider_permissions(self):

        eventprovider_data = {
            'display': 'Smart CSD Provider',
            'owner': self.eventsource_user_no1,
            'is_active': False,
            'additional': {
                'type': 'foobar',
                'service_api': 'https://tempuri.org/',
                'service_password': 'afdo12313uapsdfiue@afouapel1.org',
                'service_username': 'asfoiusofasf1241rfspue'
            }
        }
        eventprovider = EventProvider.objects.create(**eventprovider_data)

        request = self.factory.get(f'{self.api_base}/activity/eventproviders')
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventProvidersView.as_view()(request, )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

        EventProvider.objects.filter(
            id=eventprovider.id).update(is_active=True)
        request = self.factory.get(f'{self.api_base}/activity/eventproviders')
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventProvidersView.as_view()(request, )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

        eventprovider_data.update({'is_active': True})
        result_eventprovider = {
            k: response.data['results'][0][k] for k in
            eventprovider_data.keys()}
        self.assertEqual(response.data['results']
                         [0]['id'], str(eventprovider.id))

    def test_add_eventsource(self):

        eventprovider = EventProvider.objects.create(
            display='Smart CSD Provider', owner=self.eventsource_user_no1)

        eventsource_data = {
            'external_event_type': 'carcass',
            'display': 'DAS: Carcass',
            'additional': {'version': 0},
        }
        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider.id))
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        response_data = {k: response_data[k] for k in eventsource_data.keys()}
        self.assertDictEqual(response_data, eventsource_data)

    def test_get_existing_eventsource(self):
        eventprovider = EventProvider.objects.create(
            display='Smart CSD Provider', owner=self.eventsource_user_no1)

        external_event_type = 'asoviuaodbiuapsoef'
        eventsource_data = {
            'external_event_type': external_event_type,
            'display': 'DAS: Carcass',
            'additional': {'version': 0},
        }
        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider.id))
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        response_data = {k: response_data[k] for k in eventsource_data.keys()}
        self.assertDictEqual(response_data, eventsource_data)

        request = self.factory.get(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsource/{external_event_type}')
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourceView.as_view()(request,
                                                   eventprovider_id=str(
                                                       eventprovider.id),
                                                   external_event_type=external_event_type)

        self.assertEqual(response.status_code, 200)

    def test_add_eventsource_twice(self):

        eventprovider = EventProvider.objects.create(
            display='Smart CSD Provider', owner=self.eventsource_user_no1)

        eventsource_data = {
            'external_event_type': 'carcass',
            'display': 'DAS: Carcass',
            'additional': {'version': 0},
        }
        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider.id))
        self.assertEqual(response.status_code, 201)
        response.data

        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider.id))
        self.assertEqual(response.status_code, 400)
        response.data

    def test_eventsourceview_update_permission_denied(self):

        eventprovider = EventProvider.objects.create(
            display='Smart CSD Provider', owner=self.eventsource_user_no1)

        eventsource_data = {
            'external_event_type': 'carcass',
            'display': 'DAS: Carcass',
            'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }
        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider.id))
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        esid = response_data['id']

        eventsource_patch = {'additional': {'a': 1, 'b': 'some string'}}
        request = self.factory.patch(
            f'{self.api_base}/activity/eventsource/{esid}',
            eventsource_patch)

        self.force_authenticate(request, self.eventsource_user_no2)

        response = views.EventSourceView.as_view()(request, id=esid)
        self.assertEqual(response.status_code, 403)

    def test_update_eventsource_using_patch(self):

        eventprovider = EventProvider.objects.create(
            display='Smart CSD Provider', owner=self.eventsource_user_no1)

        external_event_type = 'carass-report'
        eventsource_data = {
            'external_event_type': external_event_type,
            'display': 'DAS: Carcass',
            'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }
        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider.id))
        self.assertEqual(response.status_code, 201)
        response_data = response.data

        esid = response_data['id']

        eventsource_patch = {'additional': {'a': 1, 'b': 'some string'}}
        request = self.factory.patch(
            f'{self.api_base}/activity/eventsource/{esid}', eventsource_patch)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventSourceView.as_view()(request, id=esid)
        self.assertEqual(response.status_code, 200)

        additional_data = response.data.get('additional', {})
        self.assertDictEqual(additional_data, eventsource_patch['additional'])

    def test_add_event_with_external_event_type(self):

        eventprovider = EventProvider.objects.create(
            display='Smart CSD Provider', owner=self.eventsource_user_no1)

        external_event_type = 'smart-carcass'
        eventsource_data = {
            'external_event_type': external_event_type,
            'display': 'DAS: Carcass',
            # 'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }

        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(request,
                                                    eventprovider_id=str(
                                                        eventprovider.id))
        self.assertEqual(response.status_code, 201)

        eventsource_id = response.data['id']

        # Establish category and event-type to associate with the source.
        event_category = EventCategory.objects.create(
            value='sample-event-category', display='Some display', )

        event_type = EventType.objects.create(value='some-generic-event-type',
                                              display='Some event-type',
                                              category=event_category,
                                              default_priority=0,
                                              default_state='resolved')

        # Manual step here: Associate the new generic event type to the
        # EventSource
        EventSource.objects.filter(eventprovider_id=str(
            eventprovider.id), id=eventsource_id).update(event_type=event_type)

        external_event_id = 'asdfioaasfseiuro11414sfa'
        # Create an event with an "External Event ID"
        event_title = 'Some arbirtrary event title.'
        event_timestamp = datetime(2018, 9, 8, 12, 5, 4, tzinfo=pytz.utc)
        sort_at = datetime(2018, 9, 8, 12, 5, 4, tzinfo=pytz.utc)
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
            "eventsource": eventsource_id,
            "location": {"latitude": 39.4, "longitude": -117.5},
            "time": event_timestamp.isoformat(),
            "sort_at": sort_at.isoformat(),
        }

        request = self.factory.post(f'{self.api_base}/events', event_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventsView.as_view()(request, )
        self.assertEqual(response.status_code, 201)

        eselist = EventsourceEvent.objects.filter(
            eventsource_id=eventsource_id, external_event_id=external_event_id)

        self.assertEqual(eselist.count(), 1)

        event = eselist[0].event

        self.assertEqual(sort_at, event.sort_at)

        self.assertEqual(
            eselist[0].eventsource.external_event_type, external_event_type)
        self.assertEqual(eselist[0].event.title, event_title)

    def test_add_duplicate_external_event_id(self):
        '''
        Ensure that for a single EventProvider / EventSource, we're not able to add a duplicate event identified
        by external_event_id.
        :return:
        '''
        eventprovider = EventProvider.objects.create(
            display='Smart CSD Provider', owner=self.eventsource_user_no1)

        external_event_type = 'smart-carcass-report'
        eventsource_data = {
            'external_event_type': external_event_type,
            'display': 'DAS: Carcass',
            'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }

        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider.id))
        self.assertEqual(response.status_code, 201)

        eventsource_id = response.data['id']
        external_event_id = 'abcdefgh-ijklmnop'
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
            "eventsource": eventsource_id,
            "location": {"latitude": 38.4, "longitude": -116.5},
            "time": datetime.now(tz=pytz.utc).isoformat(),
        }

        request = self.factory.post(f'{self.api_base}/events', event_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventsView.as_view()(request, )
        self.assertEqual(response.status_code, 201)

        eselist = EventsourceEvent.objects.filter(
            eventsource_id=eventsource_id, external_event_id=external_event_id)

        self.assertEqual(eselist.count(), 1)

        self.assertEqual(
            eselist[0].eventsource.external_event_type, external_event_type)
        self.assertEqual(eselist[0].event.title, event_title)

        # Add duplicate
        request = self.factory.post(f'{self.api_base}/events', event_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventsView.as_view()(request, )
        self.assertEqual(response.status_code, 409)

    def test_cannot_see_another_users_eventprovider(self):
        '''
        EventProvider by its nature may hold sensitive information. So it's critical that a user may not see
        another user's EventProvider.
        '''
        eventprovider_no1 = EventProvider.objects.create(
            display='EP No. 1', owner=self.eventsource_user_no1)
        eventprovider_no2 = EventProvider.objects.create(
            display='EP No. 2', owner=self.eventsource_user_no2)

        request = self.factory.get(f'{self.api_base}/activity/eventproviders')
        self.force_authenticate(request, self.eventsource_user_no1)
        response = views.EventProvidersView.as_view()(request, )
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results']
                         [0]['id'], str(eventprovider_no1.id))

        request = self.factory.get(f'{self.api_base}/activity/eventproviders')
        self.force_authenticate(request, self.eventsource_user_no2)
        response = views.EventProvidersView.as_view()(request, )
        self.assertEqual(len(response.data['results']), 1)

        self.assertEqual(response.data['results']
                         [0]['id'], str(eventprovider_no2.id))

    def test_add_identical_external_event_id_with_different_event_providers(
            self):
        '''
        Ensure uniqueness constraint is applied to EventSource + External Event Id.
        '''
        eventprovider_no1 = EventProvider.objects.create(
            display='Smart CSD Provider No. 1', owner=self.eventsource_user_no1)

        eventprovider_no2 = EventProvider.objects.create(
            display='Smart CSD Provider No. 2', owner=self.eventsource_user_no1)

        external_event_type = 'smart-carcass-report'
        eventsource_data = {
            'external_event_type': external_event_type,
            'display': 'DAS: Carcass',
            # 'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }

        # Create event source for provider No. 1
        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider_no1.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)
        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider_no1.id))
        self.assertEqual(response.status_code, 201)
        esid_no1 = response.data['id']

        # Create event source for provider No. 2
        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider_no2.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)
        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider_no2.id))
        self.assertEqual(response.status_code, 201)
        esid_no2 = response.data['id']

        self.assertNotEqual(esid_no1, esid_no2)

        # Manual step here: Associate the new EventSources with some new
        # EventTypes.
        event_category = EventCategory.objects.create(
            value='sample-event-category', display='Some display', )

        event_type_no1 = EventType.objects.create(
            value='eventsource_no1_event_type',
            display='eventsource_no1_event_type', category=event_category)
        EventSource.objects.filter(eventprovider_id=str(
            eventprovider_no1.id), id=esid_no1).update(
            event_type=event_type_no1)

        event_type_no2 = EventType.objects.create(
            value='eventsource_no2_event_type',
            display='eventsource_no2_event_type', category=event_category)
        EventSource.objects.filter(eventprovider_id=str(
            eventprovider_no2.id), id=esid_no2).update(
            event_type=event_type_no2)

        # Carry on with the tests.

        # Add an event for event source No. 1.
        event_title = 'Some arbirtrary event title.'
        external_event_id = 'abcdefgh-ijklmnop'
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
            "eventsource": esid_no1,
            "location": {"latitude": 38.4, "longitude": -116.5},
            "time": datetime.now(tz=pytz.utc).isoformat(),
        }

        request = self.factory.post(f'{self.api_base}/events', event_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventsView.as_view()(request, )
        self.assertEqual(response.status_code, 201)

        # Add an event for event source No. 2, and use the same
        # external_event_id as was use for event source No. 1.
        event_title = 'Some arbirtrary event title.'
        external_event_id = 'abcdefgh-ijklmnop'
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
            "eventsource": esid_no2,
            "location": {"latitude": 38.4, "longitude": -116.5},
            "time": datetime.now(tz=pytz.utc).isoformat(),
        }

        request = self.factory.post(f'{self.api_base}/events', event_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        response = views.EventsView.as_view()(request, )
        self.assertEqual(response.status_code, 201)

    def test_add_event_with_external_event_type_and_no_permissions(self):

        eventprovider = EventProvider.objects.create(
            display='Smart CSD Provider', owner=self.eventsource_user_no1)

        eventsource_data = {
            'external_event_type': 'smart_carcass_report',
            'display': 'DAS: Carcass',
            'event_type': 'carcass_rep',
            'additional': {'version': 0},
        }

        request = self.factory.post(
            f'{self.api_base}/activity/eventprovider/{str(eventprovider.id)}/eventsources',
            eventsource_data)
        self.force_authenticate(request, self.eventsource_user_no1)

        # Create event source.
        response = views.EventSourcesView.as_view()(
            request, eventprovider_id=str(eventprovider.id))
        self.assertEqual(response.status_code, 201)

        eventsource_id = response.data['id']
        # Create an event with an "External Event ID"
        event_data = {
            "event_details": {
                "attributes": [
                    {"key": "a", "value": "1"}
                ]
            },

            "eventsource": eventsource_id,
            "priority": 100,
            "title": "Test External Event",
            "location": {"latitude": 1.4, "longitude": 37.5},
            "time": datetime.now(tz=pytz.utc).isoformat(),
        }

        request = self.factory.post(f'{self.api_base}/events', event_data)
        self.force_authenticate(request, self.eventsource_user_no2)

        response = views.EventsView.as_view()(request, )

        # Expect 400 becausethe event_type is not pre-existent
        self.assertEqual(response.status_code, 400)

    def test_list_eventfilters_schema_returns_only_from_active_categories(self):
        request = self.factory.get(
            self.api_base + '/events/eventtypes')
        self.force_authenticate(request, self.all_perms_user)

        security = EventCategory.objects.get(value='security')
        security.is_active = False
        security.save()

        response = views.EventFilterSchemaView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        response_data = str(response.data)

        self.assertNotIn('security', response_data)
        self.assertIn('monitoring', response_data)
        self.assertIn('logistics', response_data)

    def test_eventtypesview_returns_only_types_in_active_categories(self):
        request = self.factory.get(
            self.api_base + '/events/eventtypes')
        self.force_authenticate(request, self.all_perms_user)

        security = EventCategory.objects.get(value='security')
        security.is_active = False
        security.save()

        event_type_value = "SecurityType"

        EventType.objects.create(value=event_type_value, category=security)
        response = views.EventTypesView.as_view()(request)

        event_type_values = [i["value"] for i in response.data]

        self.assertNotIn(event_type_value, event_type_values)

    def test_eventcategoryview_returns_only_active_categories(self):
        request = self.factory.get(self.api_base + '/events/categories')
        self.force_authenticate(request, self.all_perms_user)
        security = EventCategory.objects.get(value='security')
        security.is_active = False
        security.save()

        response = views.EventCategoriesView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        category_values = [x['value'] for x in response.data]

        self.assertNotIn('security', category_values)
        self.assertIn('monitoring', category_values)
        self.assertIn('logistics', category_values)

    def test_property_name_same_as_enum_name(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['event_type'] = ET_CARCASS
        event_data['event_details'] = {"carcassrep_species": "elephant",
                                       "carcassrep_sex": "male",
                                       "carcassrep_ageofanimal": "adult",
                                       "carcassrep_ageofcarcass": "fresh",
                                       "carcassrep_trophystatus": "intact",
                                       "carcassrep_causeofdeath": "naturaldisease"}
        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        event_details = response.data.get('event_details')
        for k, v in event_details.items():
            self.assertNotIsInstance(v, dict)

    def test_property_checkboxes(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['event_type'] = ET_OTHER
        event_data['event_details'] = {"carcassrep_species": ["elephant", "eland"],  # checkboxes
                                       "sectionArea": "unknown",
                                       "conservancy": "unknown",
                                       # multi-select
                                       "arrestrep_reasonforarrest": ["snare", "logging"],
                                       }

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        event_details = response.data.get('event_details')
        for k, v in event_details.items():
            self.assertNotIsInstance(v, dict)
        self.assertIsInstance(event_details["carcassrep_species"], list)
        self.assertNotIsInstance(event_details["carcassrep_species"][0], dict)

    def test_property_multiselect(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['event_type'] = ET_OTHER
        event_data['event_details'] = {
            "sectionArea": "unknown",
            "conservancy": "unknown",
            # multi-select
            "arrestrep_reasonforarrest": ["snare", "logging"],
        }

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        event_details = response.data.get('event_details')
        for k, v in event_details.items():
            self.assertNotIsInstance(v, dict)
        self.assertIsInstance(event_details["arrestrep_reasonforarrest"], list)
        self.assertNotIsInstance(
            event_details["arrestrep_reasonforarrest"][0], dict)

    def test_handling_legacy_data(self):
        event = self.create_event(self.event_data)
        event_detail = EventDetails.objects.create(
            event=event,
            data={'event_details': {
                'conservancy': {"name": "Name", "value": "name"},
                'test': "test",
                "correct_output_checkbox": ["one", "two"],
                'sectionArea': [{"name": "Area1", "value": "area1"},
                                {"name": "Area2", "value": "area2"}],
                'arrestrep_reasonforarrest': ['snare',
                                              'logging']}}

        )
        serializer = EventDetailsSerializer(event_detail)
        data = serializer.data
        self.assertEqual(data['conservancy'], "name")
        self.assertEqual(data['test'], "test")
        self.assertEqual(data['correct_output_checkbox'], ["one", "two"])
        self.assertEqual(data['sectionArea'], ['area1', 'area2'])
        self.assertEqual(data['arrestrep_reasonforarrest'], [
                         'snare', 'logging'])

    def test_exporting_checkbox_events_to_csv(self):
        checkbox_data = json.loads(
            """{"event_type": "dws_test","priority":200,"event_details": {"carcassrep_species": ["elephant", "eland"]}}""")

        request = self.factory.post(self.api_base + '/events/', checkbox_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_dict = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))

        self.assertIn('DWS Test', [i.get('Report_Type')
                                   for i in rendered_dict])
        target_row = {}

        for row in rendered_dict:
            if row.get('Report_Type') == 'DWS Test':
                target_row = row
                break

        self.assertIn('Species', target_row.keys())
        self.assertEqual(target_row.get('Species'), 'Elephant;Eland')

    def test_exporting_checkbox_events_to_csv_with_qparam_value_cols_true(self):
        checkbox_data = json.loads(
            """{"event_type": "dws_test","priority":200,"event_details": {"carcassrep_species": ["elephant", "eland"]}}""")

        request = self.factory.post(self.api_base + '/events/', checkbox_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export?value_cols=True"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_dict = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))

        self.assertIn('DWS Test', [i.get('Report_Type')
                                   for i in rendered_dict])
        target_row = {}

        for row in rendered_dict:
            if row.get('Report_Type') == 'DWS Test':
                target_row = row
                break

        self.assertIn('Species', target_row.keys())
        self.assertIn('carcassrep_species', target_row.keys())
        self.assertEqual(target_row.get('Species'), 'Elephant;Eland')
        self.assertEqual(target_row.get(
            'carcassrep_species'), 'elephant;eland')

    def test_exporting_array_events_to_csv(self):
        array_data = json.loads(
            """{"event_type": "4787_arry","priority":200,"event_details": {"carcassrep_species": ["bongo", "buffalo"]}}""")

        request = self.factory.post(self.api_base + '/events/', array_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_dict = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))

        self.assertIn('4787-Array', [i.get('Report_Type')
                                     for i in rendered_dict])
        target_row = {}

        for row in rendered_dict:
            if row.get('Report_Type') == '4787-Array':
                target_row = row
                break
        self.assertIn('Species', target_row.keys())
        self.assertEqual(target_row.get('Species'), 'Bongo;Buffalo')

    def test_exporting_checkbox_in_fieldset_to_csv(self):
        array_data = json.loads(
            """{"event_type": "sprint_88_behavior","priority":200,"event_details": {"carcassrep_species": ["bongo", "buffalo"]}}""")

        request = self.factory.post(self.api_base + '/events/', array_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_dict = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))
        self.assertIn('Sprint 88 Behavior',
                      [i.get('Report_Type') for i in rendered_dict])
        target_row = {}

        for row in rendered_dict:
            if row.get('Report_Type') == 'Sprint 88 Behavior':
                target_row = row
                break

        self.assertIn('Species', target_row.keys())
        self.assertEqual(target_row.get('Species'), 'Bongo;Buffalo')

    def test_exporting_checkbox_in_fieldset_to_csv_with_qparam_value_cols_true(self):
        array_data = json.loads(
            """{"event_type": "sprint_88_behavior","priority":200,"event_details": {"carcassrep_species": ["bongo", "buffalo"]}}""")

        request = self.factory.post(self.api_base + '/events/', array_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export?value_cols=true"""

        request = self.factory.get(
            self.api_base + url)

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_dict = self.convert_rendered_csv_to_dict(
            response.content.decode("utf-8"))
        self.assertIn('Sprint 88 Behavior',
                      [i.get('Report_Type') for i in rendered_dict])
        target_row = {}

        for row in rendered_dict:
            if row.get('Report_Type') == 'Sprint 88 Behavior':
                target_row = row
                break

        self.assertIn('Species', target_row.keys())
        self.assertIn('carcassrep_species', target_row.keys())
        self.assertEqual(target_row.get('Species'), 'Bongo;Buffalo')
        self.assertEqual(target_row.get('carcassrep_species'),
                         'bongo;buffalo')

    @staticmethod
    def get_ts_token(uuid):
        from django.db import connection
        cursor = connection.cursor()

        cursor.execute(
            'SELECT tsvector_event_note FROM activity_tsvectormodel WHERE event_id=%s', [uuid])
        tsvector = cursor.fetchone()
        return tsvector

    def test_tsvector_column_is_created(self):
        event = TSVectorModel.objects.raw(
            'select * from activity_tsvectormodel')
        columns = event.columns
        self.assertIn('tsvector_event', columns)
        self.assertIn('tsvector_event_note', columns)

    def test_trigger_when_event_is_created(self):
        """Test trigger works whenever event with eventdetails is created. Creates a normalized lexeme token"""
        request = self.factory.post(
            self.api_base + '/events/', [self.event_data, self.event_data])
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        uuid = response.data[0]['id']
        tsvector = self.get_ts_token(uuid)
        self.assertTrue(tsvector)

    @patch("activity.models.is_banned")
    def test_search_event_by_event_title(self, is_banned):
        is_banned.return_value = False
        title_text = "EventTitle"
        self.event_data["title"] = title_text

        request = self.factory.post(
            self.api_base + '/events/', [self.event_data, self.event_data])
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        query = {'filter': json.dumps({'text': title_text})}
        request = self.factory.get(self.api_base + '/events', data=query)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertTrue(response.data)
        self.assertEqual(response.status_code, 200)

    @patch("activity.models.is_banned")
    def test_search_filter_with_one_event_id_returns_none(self, is_banned):
        is_banned.return_value = False
        title_text = "EventTitle"
        title_search_text = "NoMatch"
        event_data = copy.copy(self.event_data)
        event_data['title'] = title_text

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        event_id = response.data['id']

        query = {'filter': json.dumps({'text': title_search_text}),
                 'event_ids': [event_id]}

        request = self.factory.get(self.api_base + '/events', data=query)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertTrue(response.data)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.status_code, 200)

    @patch("activity.models.is_banned")
    def test_search_filter_with_two_event_id_returns_one(self, is_banned):
        is_banned.return_value = False
        title_text = "EventTitle"
        title_search_text = "NoMatch"
        event_data = copy.copy(self.event_data)
        event_data_two = copy.copy(self.event_data)
        event_data['title'] = title_text
        event_data_two['title'] = title_search_text

        request = self.factory.post(
            self.api_base + '/events/', [event_data, event_data_two])
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        event_ids = [response.data[0]['id'], response.data[1]['id']]
        query = {'filter': json.dumps({'text': title_search_text}),
                 'event_ids': event_ids}

        request = self.factory.get(self.api_base + '/events', data=query)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertTrue(response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], event_ids[1])
        self.assertEqual(response.status_code, 200)

    @patch("activity.models.is_banned")
    def test_can_search_event_by_eventtype_schema_used(self, is_banned):
        # schema used has some of its titles named: conservancy, Name Of
        # Ranger, Beginning of Incident etc.
        is_banned.return_value = False
        request = self.factory.post(
            self.api_base + '/events/', [self.event_data, self.event_data])
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        # # filter by text
        searchtext_1 = 'conservancy'
        searchtext_2 = 'name of ranger'

        query = {'filter': json.dumps({'text': searchtext_1})}
        request = self.factory.get(self.api_base + '/events', data=query)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertTrue(response.data)
        self.assertEqual(response.status_code, 200)

        request = self.factory.get(
            self.api_base + '/events', data={'filter': json.dumps({'text': searchtext_2})})
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertTrue(response.data)
        self.assertEqual(response.status_code, 200)

    @patch("activity.models.is_banned")
    def test_eventnote_generate_tsvector_doc(self, is_banned):
        is_banned.return_value = False

        request = self.factory.post(
            self.api_base + '/events/', [self.event_data])
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        uuid = response.data['id']
        url = reverse('event-view-notes', args=(uuid,))
        event_note = dict(
            id='747b4d5a-79a3-11ea-bc55-0242ac130003',
            text=lorem_ipsum.paragraph()
        )

        request = self.factory.post(url, event_note)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventNotesView.as_view()(request, id=str(uuid))
        self.assertEqual(response.status_code, 201)

        tsvector = self.get_ts_token(uuid)
        self.assertTrue(tsvector)

    @patch("activity.models.is_banned")
    def test_event_note_text_search(self, is_banned):
        is_banned.return_value = False
        request = self.factory.post(
            self.api_base + "/events/", [self.event_data])
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        uuid = response.data['id']
        url = reverse('event-view-notes', args=(uuid,))
        event_note = dict(
            id='747b4d5a-79a3-11ea-bc55-0242ac130003',
            text="This is an example of a note."
        )

        request = self.factory.post(url, event_note)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventNotesView.as_view()(request, id=str(uuid))
        self.assertEqual(response.status_code, 201)

        search_text = event_note.get('text')

        query = {'filter': json.dumps({'text': search_text})}
        request = self.factory.get(self.api_base + '/events', data=query)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertTrue(response.data)
        self.assertEqual(response.status_code, 200)

    def test_report_is_not_overquoted_when_there_is_comma_in_field(self):
        carcass_data = json.loads(
            """{"event_type":"cameratrap_rep","priority":200,"event_details":{"cameratraprep_camera-version": "v1,v2,v3"}}""")

        request = self.factory.post(self.api_base + '/events/', carcass_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        url = """/activity/events/export"""

        request = self.factory.get(
            self.api_base + url)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        # convert rendered csv to dictionary format
        content = response.content.decode('utf-8')
        csv_reader = csv.reader(io.StringIO(content))
        data = list(csv_reader)
        header = data[0]
        body = data[2]

        to_dict = {key: value for key, value in zip(header, body)}
        camera_version = to_dict.get('Camera_Version')
        expected = "v1,v2,v3"
        self.assertEqual(camera_version, expected)

    def test_checkbox_field_values_included_in_export(self):
        et_schema = json.dumps({
            "schema":
            {
                "properties":
                    {
                        "rhinosightingrep_unknownpicklist": {
                            "key": "rhinosightingrep_unknown"
                        }
                    }
            },
                "definition": [
                    {
                        "type": "fieldset",
                        "htmlClass": "col-lg-6",
                        "items": [
                            {
                                "key": "rhinosightingrep_unknownpicklist",
                                "type": "checkboxes",
                                "title": "Line 3: Unknown",
                                "titleMap": [{'value': 'unknown_rhino_1', 'name': 'Unknown Rhino 1'}]
                            }
                        ]}]})
        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        EventDetails.objects.create(
            data={"event_details": {
                "rhinosightingrep_unknownpicklist": ["unknown_rhino_1"]}},
            event=self.sample_event)

        url = """/activity/events/export"""
        filter_spec = json.dumps({'text': "Test event"})
        request = self.factory.get(
            self.api_base + url, {'filter': filter_spec})

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        self.assertTrue("Unknown Rhino 1" in response.content.decode("utf-8"))

    def test_export_with_0_event_details_data(self):
        et_schema = json.dumps({
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "type": "object",
                "properties": {
                        "test_three_number":
                            {"type": "number",
                             "title": "Test 3 Number With Min and Max",
                             "minimum": 0,
                             "maximum": 50},
                        "test_four_number":
                        {"type": "number", "title": "Test 4 Number"}
                }},
            "definition": ["test_three_number", "test_four_number"]
        })

        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        EventDetails.objects.create(
            data={"event_details": {"test_four_number": 0, "test_three_number": 0}},
            event=self.sample_event)

        url = """/activity/events/export"""
        filter_spec = json.dumps({'text': "Test event"})
        request = self.factory.get(
            self.api_base + url, {'filter': filter_spec})

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_content = response.content.decode("utf-8")
        rendered_dict = self.convert_rendered_csv_to_dict(rendered_content)

        first_report = rendered_dict[0]

        # 0 event detail values included in export
        assert int(first_report.get('Test_4_Number')) == 0
        assert int(first_report.get('Test_3_Number_With_Min_and_Max')) == 0

    def test_export_on_checkbox_with_query_titlemaps(self):
        DynamicChoice.objects.create(
            id="queens",
            model_name='observations.subject',
            criteria='[["subject_subtype", "queens"], ["additional__sex", "female"]]',
            value_col='id',
            display_col='name')

        subject_type = SubjectType.objects.create(value='Cats')
        subject_subtype = SubjectSubType.objects.create(
            value='queens', subject_type=subject_type)
        subject = Subject.objects.create(
            name='Katie Kitten', subject_subtype=subject_subtype, additional={'sex': 'female'})

        et_schema = """{
            "schema":
            {
                "properties":
                    {"kitten": {"type": "a", "title" : "Test checkbox with query"}}
            },
            "definition": [
                {
                    "key": "kitten",
                    "type": "checkboxes",
                    "title": "Test checkbox with query",
                    "titleMap": {{query___queens___map}}
                }]}"""
        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        EventDetails.objects.create(
            data={"event_details": {"kitten": [str(subject.id)]}},
            event=self.sample_event)

        url = """/activity/events/export"""
        filter_spec = json.dumps({'text': "Test event"})
        request = self.factory.get(
            self.api_base + url, {'filter': filter_spec})

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)

        # title returned, not UUID
        self.assertTrue('Katie Kitten' in response.content.decode("utf-8"))

    def test_export_on_similar_titles_for_different_reports(self):
        et_schema = """{"schema":
                        {"properties":
                            {
                            "eLocust-key": {"type": "string"},
                            "behavior": {"type": "string"}
                        }},
                    "definition": []
                    }"""

        et = EventType.objects.filter(display='Other').first()
        et.schema = et_schema
        et.save()

        traffic_et = EventType.objects.filter(display='Traffic').first()
        traffic_et.schema = et_schema
        traffic_et.save()

        event1 = Event.objects.create(
            title="test_event_1", event_type=et, created_by_user=self.all_perms_user)
        event2 = Event.objects.create(
            title="test_event_2", event_type=et, created_by_user=self.all_perms_user)

        # Report from a different eventtype, similar property key
        event3 = Event.objects.create(
            title="test_event_3", event_type=traffic_et, created_by_user=self.all_perms_user)

        EventDetails.objects.bulk_create([
            EventDetails(
                data={"event_details": {"eLocust-key": "one"}}, event=event1),
            EventDetails(
                data={"event_details": {"eLocust-key": "two"}}, event=event2),
            EventDetails(data={"event_details": {"eLocust-key": "three"}}, event=event3)])

        url = """/activity/events/export"""
        filter_spec = json.dumps({'text': "test_event"})
        request = self.factory.get(
            self.api_base + url, {'filter': filter_spec})

        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsExportView.as_view()(request)
        rendered_content = response.content.decode("utf-8")
        rendered_dict = self.convert_rendered_csv_to_dict(rendered_content)
        report_headers = [key for key in rendered_dict[0].keys()]

        # Single column returned containing all the three report records
        assert report_headers.count('E_Locust-Key') == 1

    def test_no_event_type_display(self):
        # User with no-perms can't view event categories
        request = self.factory.get(
            self.api_base + '/events/eventtypes')
        self.force_authenticate(request, self.no_perms_user)

        response = views.EventTypesView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_only_display_eventtype_of_category_logistic_only(self):
        # Guest users can see logistics events and nothing else
        request = self.factory.get(
            self.api_base + '/events/eventtypes')
        self.force_authenticate(request, self.guest_user)

        response = views.EventTypesView.as_view()(request)
        expected_display = 'Logistics'
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(o.get('category').get('display') ==
                            expected_display for o in response.data))

    def test_no_schema_display(self):
        # no event-schema is displayed for user with no even-category
        # permission.
        request = self.factory.get(
            self.api_base + '/events/schema')
        self.force_authenticate(request, self.no_perms_user)

        response = views.EventSchemaView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('properties')
                         ['reported_by']['enum'], [])

    def test_schema_with_inactive_choices(self):
        for choice in Choice.objects.all():
            choice.delete()

        choices = []
        choice = Choice.objects.create(
            model='activity.event',
            field='wildlifesighting_species',
            value='elephant',
            display='Elephant',
        )

        choice.save()
        choices.append(choice)

        choice = Choice.objects.create(
            model='activity.event',
            field='wildlifesighting_species',
            value='rhino',
            display='Rhino',
        )
        choice.save()
        choices.append(choice)

        choice = Choice.objects.create(
            model='activity.event',
            field='wildlifesighting_species',
            value='baboon',
            display='Baboon',
            is_active=False
        )
        choice.save()
        choices.append(choice)

        et_schema = """{
            "schema":
            {
                "properties":
                    {"species": {"title" : "Test checkbox with enum"},
                    "animal_species": {"title" : "Test animal checkbox with enum"},
                    "reportlocationarea": {"type": "string", "title": "Location / Area TEST String"},
                    "reportreportername": {"type": "string", "title": "Reporter Name"}
                    }
            },
            "definition": [
                {
                    "type": "fieldset",
                    "htmlClass": "col-lg-6",
                    "items": [
                      "reportlocationarea",
                      {
                        "key": "animal_species",
                        "type": "checkboxes",
                        "title": "Test animal checkbox with enum",
                        "titleMap": {{enum___wildlifesighting_species___map}}
                       }
                    ]
                },
                {
                    "type": "fieldset",
                    "htmlClass": "col-lg-6",
                    "items": [
                        "reportlocationarea",
                        "reportreportername"
                    ]
                },
                {
                    "key": "species",
                    "type": "checkboxes",
                    "title": "Test checkbox with enum",
                    "titleMap": {{enum___wildlifesighting_species___map}}
                }
            ]
            }"""
        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        url = self.api_base + f'/events/schema/eventtype/'
        request = self.factory.get(url)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventTypeSchemaView.as_view()(
            request, eventtype=event_type.value)

        assert response.status_code == 200
        species_display = [display_prop for display_prop in response.data['definition']
                           if display_prop.get('key', '') == 'species'][0]
        assert "inactive_titleMap" in species_display

        species_display = [display_prop for display_prop in response.data['definition'][0]['items']
                           if isinstance(display_prop, dict) and display_prop.get('key', '') == 'animal_species'][0]
        assert "inactive_titleMap" in species_display

    def test_case_insensitive_eventtype(self):
        eventtype_value = 'Smart_rhino_sighting'
        event_category = EventCategory.objects.create(
            value='test_category', display='Test Category')
        event_type = EventType.objects.create(
            value=eventtype_value,
            display='Smart Rhino Sighting', category=event_category)
        url = self.api_base + f'/events/schema/eventtype/'
        request = self.factory.get(url)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventTypeSchemaView.as_view()(
            request, eventtype=eventtype_value)
        assert response.status_code == 200

    def test_schema_with_same_inactive_choices(self):
        Choice.objects.all().delete()

        [Choice.objects.create(model=Choice.Field_Reports,
                               field='behavior',
                               value=f'ac{i}',
                               ordernum=i,
                               display=f'AC{i}') for i in range(0, 2)]

        [Choice.objects.create(model=Choice.Field_Reports,
                               field='behavior',
                               value=f'di{i}',
                               display=f'DI{i}',
                               ordernum=i,
                               is_active=False) for i in range(3, 5)]

        et_schema = schema_examples.ET_SCHEMA
        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        properties_with_enum = ['repCountry', 'HopAppearance', 'HopBehaviour',
                                'HopDensity', 'HopDensityUnit', 'HopStageDom',
                                'HopActivity', 'HopStage', 'HopColour']

        url = reverse('event-schema-eventtype',
                      kwargs={'eventtype': event_type.value})
        request = self.factory.get(url)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventTypeSchemaView.as_view()(
            request, eventtype=event_type.value)
        assert response.status_code == 200

        properties = response.data['schema']['properties']
        inactive_choices = ['di3', 'di4']

        for o in properties_with_enum:
            # Inactive enums present
            data = properties.get(o)
            inactive_enum = data.get('inactive_enum')
            assert inactive_enum == inactive_choices

        url += '?{}'.format(urlencode({'definition': 'flat'}))
        request = self.factory.get(url)
        self.force_authenticate(request, self.all_perms_user)
        new_response = views.EventTypeSchemaView.as_view()(
            request, eventtype=event_type.value)

        properties = new_response.data['schema']['properties']

        for o in properties_with_enum:
            # Inactive enums skipped
            data = properties.get(o)
            assert not data.get('inactive_enum')
            assert all(inactive_choices) not in data.get('enum')
            assert all(inactive_choices) not in data.get('enumNames').keys()

    def test_flat_definition(self):
        choice = Choice.objects.create(
            model='activity.event',
            field='wildlifesighting_species',
            value='elephant',
            display='Elephant',
        )

        et_schema = """{
            "schema":
            {
                "properties":
                    {"species": {"title" : "Test checkbox with enum"},
                    "animal_species": {"title" : "Test animal checkbox with enum"},
                    "reportlocationarea": {"type": "string", "title": "Location / Area TEST String"},
                    "reportreportername": {"type": "string", "title": "Reporter Name"}
                    }
            },
            "definition": [
                {
                    "type": "fieldset",
                    "htmlClass": "col-lg-6",
                    "items": [
                      "reportlocationarea",
                      {
                        "key": "animal_species",
                        "type": "checkboxes",
                        "title": "Test animal checkbox with enum",
                        "titleMap": {{enum___wildlifesighting_species___map}}
                       }
                    ]
                },
                {
                    "type": "fieldset",
                    "htmlClass": "col-lg-6",
                    "items": [
                        "reportlocationarea",
                        "reportreportername"
                    ]
                },
                {
                    "key": "species",
                    "type": "checkboxes",
                    "title": "Test checkbox with enum",
                    "titleMap": {{enum___wildlifesighting_species___map}}
                }
            ]
            }"""
        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        url = self.api_base + f'/events/schema/eventtype/?definition=flat'
        request = self.factory.get(url)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventTypeSchemaView.as_view()(
            request, eventtype=event_type.value)
        assert response.status_code == 200

        assert len([display_prop for display_prop in response.data['definition'] if isinstance(
            display_prop, dict) and display_prop.get('type') == 'fieldset']) == 0
        assert len([display_prop for display_prop in response.data['definition'] if isinstance(
            display_prop, str) and display_prop in ('reportlocationarea', 'reportreportername')]) == 3

        url = self.api_base + f'/events/schema/eventtype/?definition=invalid'
        request = self.factory.get(url)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventTypeSchemaView.as_view()(
            request, eventtype=event_type.value)
        assert response.status_code == 400

    def test_schema_with_string_arrays(self):
        choice = Choice.objects.create(
            model='activity.event',
            field='wildlifesighting_species',
            value='elephant',
            display='Elephant',
        )

        base_schema = {
            "schema": {
                "properties": {
                    "MusthBull": {
                        "title": "Musth Bull Present",
                        "type": "string",
                        "enum": [
                            "yes",
                            "no"
                        ]
                    }
                },
                "definition": [
                    "MusthBull"
                ]
            }
        }
        event_type = self.sample_event.event_type
        event_type.schema = json.dumps(base_schema)
        event_type.save()

        url = f"{self.api_base}/events/schema/eventtype/{event_type.id}/"
        request = self.factory.get(url)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventTypeSchemaView.as_view()(
            request, eventtype=event_type.value)

        assert response.status_code == 200

        assert response.data["schema"]["properties"]["MusthBull"]["title"] == base_schema["schema"]["properties"]["MusthBull"]["title"]
        assert response.data["schema"]["definition"][0] == base_schema["schema"]["definition"][0]

    def test_schema_with_different_inactive_choices(self):

        Choice.objects.all().delete()

        [Choice.objects.create(model=Choice.Field_Reports,
                               field='wildlifesightingrep_species',
                               value=c,
                               display=c.title()) for c in ['asiatic lion', 'asiatic cheetah', 'siberian tiger']]

        [Choice.objects.create(model=Choice.Field_Reports,
                               field='yesno',
                               value=i,
                               display=i.title()) for i in ['oh yeah!', 'yes', 'no']]

        Choice.objects.filter(value='asiatic cheetah').update(is_active=False)
        Choice.objects.filter(value='oh yeah!').update(is_active=False)

        et_schema = schema_examples.WILDLIFE_SCHEMA
        event_type = self.sample_event.event_type
        event_type.schema = et_schema
        event_type.save()

        url = reverse('event-schema-eventtype',
                      kwargs={'eventtype': event_type.value})
        request = self.factory.get(url)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventTypeSchemaView.as_view()(
            request, eventtype=event_type.value)
        assert response.status_code == 200

        properties = response.data['schema']['properties']

        species = properties.get('wildlifesightingrep_species')
        inactive_enum = species.get('inactive_enum')
        assert inactive_enum == ['asiatic cheetah']

        livestock_array = properties['livestock_killed_array']["items"]["properties"]["Animal Name"]
        inactive_enum = livestock_array.get('inactive_enum')
        assert inactive_enum == ['asiatic cheetah']

        state = properties.get('wildlifesightingrep_collared')
        inactive_enum = state.get('inactive_enum')
        assert inactive_enum == ['oh yeah!']

    def test_auto_resolve_eventtype(self):
        event_data = copy.deepcopy(self.event_data)
        event_data['reported_by'] = self.user_rep
        event_data['provenance'] = Event.PC_STAFF

        EventType.objects.filter(value=ET_OTHER).update(
            auto_resolve=True, resolve_time=1)
        event_data['event_type'] = ET_OTHER

        request = self.factory.post(self.api_base + '/events/', event_data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        created_at = datetime.now(tz=pytz.utc) - timedelta(hours=2)
        Event.objects.filter(id=response.data.get(
            'id')).update(created_at=created_at)

        self.assertEqual(response.data.get('state'), 'new')
        automatically_update_event_state()

        state = Event.objects.get(id=response.data.get('id')).state
        self.assertEqual(state, 'resolved')

    def test_post_with_checkboxes(self):
        schema = schema_examples.WILDLIFE_SCHEMA_CHECKBOX
        event_type = self.sample_event.event_type
        event_type.schema = schema
        event_type.save()
        data = json.loads(
            "{\"priority\":0,\"time\":\"2021-06-05T19:26:32.985Z\",\"event_details\":{\"wildlifesightingrep_species\":[\"bongo\"],\"wildlifesightingrep_numberanimals\":1,\"wildlifesightingrep_collared\":[\"no\"],\"wildlifesightingrep_comments\":\"Some Comments\"}}")
        data["event_type"] = event_type.value
        request = self.factory.post(self.api_base + '/events/', data)
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventsView.as_view()(request)
        assert response.status_code == 201
        event_id = response.data['id']

        request = self.factory.get(self.api_base + f"/event/{event_id}")
        self.force_authenticate(request, self.all_perms_user)
        response = views.EventView.as_view()(request, id=event_id)
        assert response.status_code == 200

        event = Event.objects.get(id=event_id)
        event_details = EventDetails.objects.get(event_id=event_id)
        assert isinstance(
            event_details.data["event_details"]["wildlifesightingrep_species"][0], str)

    def test_consistency_checkbox_value(self):
        Choice.objects.all().delete()
        Choice.objects.create(model=Choice.Field_Reports,
                              field='wildlifesightingrep_species',
                              value='buffalo',
                              display='Buffalo')

        Choice.objects.create(model=Choice.Field_Reports,
                              field='yesno',
                              value='yes',
                              display='Yes')

        schema = schema_examples.WILDLIFE_SCHEMA_CHECKBOX
        event_type = self.sample_event.event_type
        event_type.schema = schema
        event_type.save()

        payload = {"event_type": event_type.value,
                   "event_details": {"wildlifesightingrep_species": ["buffalo"],
                                     "wildlifesightingrep_collared": ["yes"],
                                     "wildlifesightingrep_numberanimals": "2"}}

        request = self.factory.post(self.api_base + '/events/', payload)
        self.force_authenticate(request, self.all_perms_user)

        response = views.EventsView.as_view()(request)
        self.assertEqual(response.status_code, 201)

        expected_result = {'event_details': {'wildlifesightingrep_species': ['buffalo'],
                                             'wildlifesightingrep_collared': ['yes'],
                                             'wildlifesightingrep_numberanimals': '2'}}

        actual_result = Event.objects.get(
            id=response.data.get('id')).event_details.first()
        self.assertEqual(expected_result, actual_result.data)


class TestParsing(TestCase):

    def test_dates(self):
        upper = dateparse.parse_datetime('2019-01-01T01:00:00')
        lower = dateparse.parse_datetime('2018-12-12T01:00:00')
        val = dict(lower=lower.isoformat(),
                   upper=upper.isoformat())
        result = parse_date_range(val)
        self.assertTupleEqual((lower, upper), result)

    def test_missing_upper(self):
        lower = dateparse.parse_datetime('2018-12-12T01:00:00')
        val = dict(lower=lower.isoformat())
        result = parse_date_range(val)
        self.assertTupleEqual((lower, None), result)

    def test_missing_lower(self):
        upper = dateparse.parse_datetime('2018-12-12T01:00:00')
        val = dict(upper=upper.isoformat())
        result = parse_date_range(val)
        self.assertTupleEqual((None, upper), result)

    def test_bad_lower(self):
        val = dict(lower=0)
        with self.assertRaises(TypeError):
            parse_date_range(val)


@pytest.mark.django_db
class TestEventFilterQueryset:
    ID = [
        "248d5504-c430-4c61-8609-3f36db231806",
        "6f0d6cdc-8dbd-45b6-9348-cbb5a0da3558",
        "10989e64-81a9-4ee9-90c0-7a1d62ca6a45",
        "d6e15c45-2e65-4f54-a06d-1d4075d07a10",
        "b97e67c4-350e-412c-9ef7-cd1e54ed205a",
    ]

    def test_by_text_filter_method_for_serial_number(self, five_events_with_details):
        event = Event.objects.last()

        events = Event.objects.by_text_filter(f"{event.serial_number}")

        assert events.count() == 1

    @pytest.mark.parametrize("term", ["2", "24", "248"])
    def test_by_text_filter_method_using_numbers_for_ids_in_event_details_data(
        self, five_events_with_details, term
    ):
        event_details = EventDetails.objects.all()
        for idx, event_detail in enumerate(event_details, 0):
            event_detail.data = {
                "event_details": {
                    "rhinosightingrep_Rhino": self.ID[idx],
                }
            }
            event_detail.save()

        events = Event.objects.by_text_filter(term)

        assert events.count() >= 1

    @pytest.mark.parametrize("term", ["d", "d6", "d6e"])
    def test_by_text_filter_method_using_letters_for_ids_in_event_details_data(
        self, five_events_with_details, term
    ):
        event_details = EventDetails.objects.all()
        for idx, event_detail in enumerate(event_details, 0):
            event_detail.data = {
                "event_details": {
                    "rhinosightingrep_Rhino": self.ID[idx],
                }
            }
            event_detail.save()

        events = Event.objects.by_text_filter(term)

        assert events.count() >= 1

    @pytest.mark.parametrize(
        "known_location",
        [
            {
                "location": "-103.527837, 20.668671",
                "known_distance_meters": 1200,
                "result": False,
            },
            {
                "location": "-103.523242, 20.655429",
                "known_distance_meters": 2000,
                "result": False,
            },
            {
                "location": "-103.520739, 20.669644",
                "known_distance_meters": 500,
                "result": True,
            },
            {
                "location": "-103.519298, 20.671825",
                "known_distance_meters": 250,
                "result": True,
            },
        ],
    )
    @pytest.mark.parametrize(
        "get_geo_permission_set",
        [
            [
                "view_analyzer_event_geographic_distance",
                "view_logistics_geographic_distance",
                "view_monitoring_geographic_distance",
                "view_security_geographic_distance",
            ]
        ],
        indirect=True,
    )
    @pytest.mark.parametrize(
        "events_with_category",
        [["analyzer_event", "logistics", "monitoring", "security"]],
        indirect=True,
    )
    def test_by_location_filter(
            self,
            events_with_category,
            get_geo_permission_set,
            known_location,
            settings,
            rf,
            monkeypatch,
    ):
        is_banned = MagicMock(return_value=False)
        monkeypatch.setattr("activity.models.is_banned", is_banned)

        settings.GEO_PERMISSION_RADIUS_METERS = 1000
        event = events_with_category[-1]
        user_location = "-103.517015,20.672398"

        url = f"{reverse('events')}?location={user_location}"
        request = rf.get(url)
        client = HTTPClient()
        client.app_user.permission_sets.add(get_geo_permission_set)
        request.user = client.app_user

        event.location = convert_to_point(known_location["location"])
        event.save()
        categories_to_search = get_categories_and_geo_categories(request.user)
        assert Event.objects.by_location(
            request.GET.get("location", ""),
            request.user,
            categories_to_search
        ).exists() == known_location["result"]


@pytest.mark.django_db
class TestEventFilterQuerysetByBbox:
    @pytest.fixture
    def _events_with_geometries(self, five_events, five_event_geometries):
        FLOWER_MILL_PARK = Polygon((
            (-98.8345742225647, 19.51572603509693),
            (-98.84262084960938, 19.51813278329343),
            (-98.84324312210083, 19.516454130768803),
            (-98.84146213531494, 19.515988958912285),
            (-98.84139776229858, 19.514290059021565),
            (-98.8444447517395, 19.514775460812128),
            (-98.84530305862427, 19.513400151953725),
            (-98.84008884429932, 19.509678669328427),
            (-98.83386611938475, 19.512247310514844),
            (-98.83571147918701, 19.514087807845353),
            (-98.8345742225647, 19.51572603509693)
        ))
        TEXCOCO_DOWNTOWN = Point((-98.8826984167099, 19.514676863691378))
        TEXCOCO_LAKE = Polygon((
            (-98.95462989807129, 19.483019024382198),
            (-98.9934253692627, 19.46982917028777),
            (-98.98527145385742, 19.448747451000244),
            (-98.94621849060059, 19.46311245167841),
            (-98.95462989807129, 19.483019024382198)
        ))

        town = five_events[0]
        town.location = TEXCOCO_DOWNTOWN
        town.save()
        expected_events = [town]

        park, lake = five_event_geometries[:2]
        for event_geometry, polygon in [(park, FLOWER_MILL_PARK),
                                        (lake, TEXCOCO_LAKE)]:
            event_geometry.geometry = polygon
            event_geometry.save()
            expected_events.append(event_geometry.event)

        return expected_events

    def test_bbox_includes_both_geometries_and_locations(
        self,
        _events_with_geometries
    ):
        MEXICO_CITY_EAST = (-99.179592, 19.398440, -98.747349, 19.606854)
        events = Event.objects.by_bbox(MEXICO_CITY_EAST)
        town, park, lake = _events_with_geometries

        expected_ids = set([town.id, park.id, lake.id])
        actual_ids = set(events.values_list("id", flat=True))

        assert events.count() == 3
        assert expected_ids == actual_ids

    def test_bbox_excludes_geometries_out_of_boundaries(
        self,
        _events_with_geometries
    ):
        TEXCOCO_CITY = (-98.920469, 19.485446, -98.812408, 19.537547)
        events = Event.objects.by_bbox(TEXCOCO_CITY)
        town, park = _events_with_geometries[:2]

        expected_ids = set([town.id, park.id])
        actual_ids = set(events.values_list("id", flat=True))

        assert events.count() == 2
        assert expected_ids == actual_ids

    def test_bbox_includes_partial_overlapping_event(
        self,
        _events_with_geometries
    ):
        MEXICO_CITY_AIRPORT = (-99.117622, 19.370426, -98.974285, 19.494751)
        events = Event.objects.by_bbox(MEXICO_CITY_AIRPORT)

        expected_ids = set([_events_with_geometries[2].id])
        actual_ids = set(events.values_list("id", flat=True))

        assert events.count() == 1
        assert expected_ids == actual_ids

    def test_bbox_excludes_all_geometries_and_locations(
        self,
        _events_with_geometries
    ):
        DESERT_OF_LIONS = (-99.387732, 19.223557, -99.171610, 19.327910)
        events = Event.objects.by_bbox(DESERT_OF_LIONS)

        assert events.count() == 0


@pytest.mark.django_db
class TestEventView2(BaseTestToolMixin):
    api_path = "activity/events/"
    view = views.EventsView

    def test_auto_add_report_to_patrols(self, five_patrol_segment_subject):
        patrol = Patrol.objects.order_by("created_at").last()
        segment = patrol.patrol_segments.first()
        subject = patrol.patrol_segments.first().leader

        event_data = {
            "event_type": "acoustic_detection",
            "reported_by": SubjectSerializer(subject).data,
            "time": datetime.now().isoformat(),
            "event_details": {
                "type_accident": "1",
                "number_people_involved": 5,
                "animals_involved": "1"
            }
        }

        url = f"{reverse('events')}"
        client = HTTPClient()
        client.app_user.is_superuser = True
        client.app_user.save()
        request = client.factory.post(url, data=event_data)
        client.force_authenticate_with_cyber_tracker(request, client.app_user)
        response = views.EventsView.as_view()(request)

        segment.refresh_from_db()

        assert response.status_code == 201
        assert segment.events.count() >= 1
        assert segment.events.first(
        ).event_type.value == event_data["event_type"]

    @pytest.mark.parametrize(
        "known_locations",
        [
            [
                {"location": "0, 0", "distance": 500},
                {"location": "0.002711,  -0.000000", "distance": 300},
                {"location": "-0.000006, 0.000943", "distance": 100},
                {"location": "-0.001804, 0.000338", "distance": 200},
            ]
        ],
    )
    @pytest.mark.parametrize(
        "events_with_category",
        [["analyzer_event", "logistics", "monitoring", "security"]],
        indirect=True,
    )
    def test_list_events(self, known_locations, events_with_category, settings, monkeypatch):
        mock = MagicMock(return_value=False)
        monkeypatch.setattr("activity.models.is_banned", mock)

        settings.GEO_PERMISSION_RADIUS_METERS = 1000
        events = Event.objects.order_by("-created_at")[:4]

        for event, data in zip(events, known_locations):
            event.location = convert_to_point(data["location"])
            event.save()

        permissions = ["analyzer_event", "logistics"]
        geojson_set = PermissionSet.objects.create(name="geojson_set")

        for permission in permissions:
            permission_name = f"view_{permission}_geographic_distance"
            geojson_set.permissions.add(
                Permission.objects.get(codename=permission_name))

        url = f"{reverse('events')}?location=0,0"
        client = HTTPClient()
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)
        client.app_user.permission_sets.add(geojson_set)
        response = views.EventsView.as_view()(request)

        assert response.data["count"] == 2
        assert response.status_code == 200
        for event in response.data["results"]:
            assert event["event_category"] in permissions

    def test_events_view_with_no_location(self, settings, monkeypatch):
        is_banned = MagicMock(return_value=False)
        monkeypatch.setattr("activity.models.is_banned", is_banned)

        settings.GEO_PERMISSION_RADIUS_METERS = 1000

        permissions = ["analyzer_event", "logistics", "monitoring", "security"]
        geojson_set = PermissionSet.objects.create(name="geojson_set")

        for permission in permissions:
            permission_name = f"view_{permission}_geographic_distance"
            geojson_set.permissions.add(
                Permission.objects.get(codename=permission_name))

        url = f"{reverse('events')}"
        client = HTTPClient()
        request = client.factory.get(url)
        client.force_authenticate(request, client.app_user)
        client.app_user.permission_sets.add(geojson_set)
        response = views.EventsView.as_view()(request)

        assert response.status_code == 200
        assert response.data["count"] == 0

    def test_get_json_schema_method_without_repeated_dynamic_choice(self, event_type):
        schema_waited = {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Rhino Sighting (rhino_sighting_rep)",
                "type": "object",
                "properties": {
                    "rhinosightingrep_earnotchcount": {
                        "type": "number",
                        "title": "Ear notch count",
                    },
                    "rhinosightingrep_Rhino": {
                        "type": "string",
                        "title": "Individual Rhino ID",
                        "enum": "{{query___blackRhinos___values}}",
                        "enumNames": "{{query___blackRhinos___names}}",
                    },
                },
            },
            "definition": [
                {"key": "rhinosightingrep_earnotchcount", "htmlClass": "col-lg-6"},
                {"key": "rhinosightingrep_Rhino", "htmlClass": "col-lg-6"},
            ],
        }
        schema = '''{
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Rhino Sighting (rhino_sighting_rep)",

                "type": "object",

                "properties":
                {
                    "rhinosightingrep_earnotchcount": {
                        "type":"number",
                        "title": "Ear notch count"
                    },
                    "rhinosightingrep_Rhino": {
                        "type": "string",
                        "title": "Individual Rhino ID",
                        "enum": {{query___blackRhinos___values}},
                        "enumNames": {{query___blackRhinos___names}}
                    }
                }
            },
            "definition": [
            {
                "key":         "rhinosightingrep_earnotchcount",
                "htmlClass": "col-lg-6"
            },
            {
                "key":         "rhinosightingrep_Rhino",
                "htmlClass": "col-lg-6"
            }
            ]
        }'''
        event_type.schema = schema
        event_type.save()

        events_view = views.EventTypeSchemaView()
        json_schema = events_view._get_json_schema(event_type)

        assert json_schema == schema_waited

    def test_get_json_schema_method_with_repeated_dynamic_choice(self, event_type):
        schema_waited = {
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Rhino Sighting (rhino_sighting_rep)",
                "type": "object",
                "properties": {
                    "rhinosightingrep_earnotchcount": {
                        "type": "number",
                        "title": "Ear notch count",
                    },
                    "rhinosightingrep_Rhino": {
                        "type": "string",
                        "title": "Individual Rhino ID",
                        "enum": "{{query___blackRhinos___values}}",
                        "enumNames": "{{query___blackRhinos___names}}",
                    },
                    "rhinosightingrep_Rhino2": {
                        "type": "string",
                        "title": "Individual Rhino ID 2",
                        "enum": "{{query___blackRhinos___values}}",
                        "enumNames": "{{query___blackRhinos___names}}",
                    }
                },
            },
            "definition": [
                {"key": "rhinosightingrep_earnotchcount", "htmlClass": "col-lg-6"},
                {"key": "rhinosightingrep_Rhino", "htmlClass": "col-lg-6"},
                {"key": "rhinosightingrep_Rhino2", "htmlClass": "col-lg-6"},
            ],
        }
        schema = '''{
            "schema": {
                "$schema": "http://json-schema.org/draft-04/schema#",
                "title": "Rhino Sighting (rhino_sighting_rep)",

                "type": "object",

                "properties":
                {
                    "rhinosightingrep_earnotchcount": {
                        "type":"number",
                        "title": "Ear notch count"
                    },
                    "rhinosightingrep_Rhino": {
                        "type": "string",
                        "title": "Individual Rhino ID",
                        "enum": {{query___blackRhinos___values}},
                        "enumNames": {{query___blackRhinos___names}}
                    },
                    "rhinosightingrep_Rhino2": {
                        "type": "string",
                        "title": "Individual Rhino ID 2",
                        "enum": {{query___blackRhinos___values}},
                        "enumNames": {{query___blackRhinos___names}}
                    }
                }
            },
            "definition": [
            {
                "key":         "rhinosightingrep_earnotchcount",
                "htmlClass": "col-lg-6"
            },
            {
                "key":         "rhinosightingrep_Rhino",
                "htmlClass": "col-lg-6"
            },
            {
                "key":         "rhinosightingrep_Rhino2",
                "htmlClass": "col-lg-6"
            }
            ]
        }'''
        event_type.schema = schema
        event_type.save()

        events_view = views.EventTypeSchemaView()
        json_schema = events_view._get_json_schema(event_type)

        assert json_schema == schema_waited

    def test_create_event_with_only_create_permission(self):
        event_data = {'title': 'test title',
                      "event_type": "acoustic_detection"}
        url = f"{reverse('events')}"
        client = HTTPClient()

        permission_set = PermissionSet.objects.create(
            name='Only create Events')
        permission = Permission.objects.get(codename='analyzer_event_create')
        permission_set.permissions.add(permission)
        client.app_user.permission_sets.add(permission_set)

        request = client.factory.post(url, data=event_data)
        client.force_authenticate(request, client.app_user)
        response = views.EventsView.as_view()(request)

        assert response.status_code == 201
        assert 'id' in response.data
        assert len(response.data.keys()) == 1

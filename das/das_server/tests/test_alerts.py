import copy
import das_server.mailer as mailer

import django.contrib.auth
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import Permission
from django.core.management import call_command
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from accounts.models import PermissionSet
from activity.models import Event, EventAttachment, EventType, EventRelationship
from observations.models import Subject

User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'

target_subject_new_event = 'DAS Green ALERT: {0}  {1} NEW'
target_body_new_event = '''DAS Event Alert
{0}: {6} NEW




Full event data:

id: {0}

time: {1}

message: {2}

provenance: {5}

event_type: {3}

priority_label: Green

attributes: {{}}

notes: []

state: New

photos: []

is_contained_in: []

url: /api/v1.0/activity/event/{0}

event_category: security

is_collection: {4}'''
target_from_address_new_event = 'notifications@pamdas.org'

target_subject_update_event = 'DAS Green ALERT: {0}  New Title UPDATE'
target_body_update_event = '''DAS Event Alert
{0}: New Title UPDATE




Full event data:

id: {0}

time: {1}

message: {2}

provenance: {5}

event_type: {3}

priority_label: Green

attributes: {{}}

title: New Title

notes: []

state: New

photos: []

is_contained_in: []

url: /api/v1.0/activity/event/{0}

event_category: security

is_collection: {4}'''

target_from_address_update_event = 'notifications@pamdas.org'


class TestEventView(TestCase):
    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')

        self.user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user('super', 'super@test.com', 'super', is_superuser=True, is_staff=True, **self.user_const)
        self.readonly_user = User.objects.create_user('readonly','readonly@test.com', 'readonly', **self.user_const)
        self.no_perms_user = User.objects.create_user('noperms', 'noperms@test.com', 'noperms', **self.user_const)
        self.staff = Subject.objects.create(name='Ranger 2', additional={})

        self.event_data = dict(
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517')
            )

        self.event = self.create_event(self.event_data)
        self.incident, self.contained_event = self.create_incident()


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

    def update_event(self, event):
        event.title = "New Title"
        event.save()
        revision = event.revision.all_user().order_by('sequence').last()
        return revision

    def create_incident(self):
        incident_data = copy.deepcopy(self.event_data)
        incident_data['provenance'] = Event.PC_STAFF
        incident_data['event_type'] = 'incident_collection'
        incident = self.create_event(incident_data)

        event_data = copy.deepcopy(self.event_data)
        event_data['provenance'] = Event.PC_STAFF
        event_data['event_type'] = 'other'
        event = self.create_event(event_data)

        EventRelationship.objects.add_relationship(incident, event, 'contains')

        return incident, event

        # rel_data = {'to_event_id': event.id, 'type': 'contains'}
        # request = self.factory.post(
        #     self.api_base + '/event/' + incident.id + '/relationships', rel_data)
        # self.force_authenticate(request, self.user)
        # response = views.EventRelationshipsView.as_view()(request,
        #                                                   from_event_id=incident.id)
        # print(response)
        # self.assertEqual(response.status_code, 201)

    def test_new_event_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        mailer.send_event_mail(self.event, self.user, None, mail_callback)

        target_subject = target_subject_new_event.format(self.event.id, self.event.title)
        target_body = target_body_new_event.format(self.event.id,
                                                   self.time_to_string(self.event.event_time),
                                                   self.event.message,
                                                   self.event.event_type.value,
                                                   'False',
                                                   self.event.get_display_value('provenance', self.event.provenance),
                                                   self.event.title).strip()

        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address_new_event)

    def test_change_event_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        revision = self.update_event(self.event)

        mailer.send_event_mail(self.event, self.user, revision, mail_callback)
        target_subject = target_subject_update_event.format(self.event.id)
        target_body = target_body_update_event.format(self.event.id,
                                                      self.time_to_string(self.event.event_time),
                                                      self.event.message,
                                                      self.event.event_type.value,
                                                      'False',
                                                      self.event.get_display_value('provenance', self.event.provenance)).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address_update_event)

    def test_new_incident_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        mailer.send_event_mail(self.incident, self.user, None, mail_callback)

        target_subject = target_subject_new_event.format(self.incident.id, self.incident.title)
        target_body = target_body_new_event.format(self.incident.id,
                                                   self.time_to_string(self.incident.event_time),
                                                   self.incident.message,
                                                   self.incident.event_type.value,
                                                   'True',
                                                   self.incident.get_display_value('provenance', self.incident.provenance),
                                                   self.incident.title).strip()

        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address_new_event)

    def test_change_incident_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        revision = self.update_event(self.incident)

        mailer.send_event_mail(self.incident, self.user, revision, mail_callback)
        target_subject = target_subject_update_event.format(self.incident.id)
        target_body = target_body_update_event.format(self.incident.id,
                                                      self.time_to_string(self.incident.event_time),
                                                      self.incident.message,
                                                      self.incident.event_type.value,
                                                      'True',
                                                      self.incident.get_display_value('provenance', self.incident.provenance),).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address_new_event)

    def time_to_string(self, time):
        time = time.isoformat()
        if time.endswith('+00:00'):
            time = time[:-6] + 'Z'
        return time
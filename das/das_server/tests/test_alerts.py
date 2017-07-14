import copy
import pytz
import das_server.mailer as mailer
import django.contrib.auth
from datetime import datetime
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from activity.models import Event, EventType, EventRelationship, EventDetails, EventNote, EventAttachment
from observations.models import Subject

User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'

event_schema_data = {
    "event_details": {
        "conservancy": {
            "name": "Sera",
            "value": "19778984-f5aa-42df-9e0c-29ae2e4a4884"
        },
        "sectionArea": [{
            "name": "Corner Safi",
            "value": "1ec47dea-7e8e-4761-a15a-da6b01633cf8"
        }],
        "details": 'some details about the event',
    }
}

incident_schema_data = {
    "event_details": {
        "conservancy": {
            "name": "Sera",
            "value": "19778984-f5aa-42df-9e0c-29ae2e4a4884"
        },
        "details": 'some details about the event',
    }
}

base_target_subject = 'DAS Green Alert: {serial} {title}'
target_from_address = 'notifications@pamdas.org'

new_event_body = '''DAS Green Alert
{serial}: {title}



Conservancy: Sera

Details: some details about the event

Section/Area: Corner Safi

time: {time}

message: {text}

event_type: {type}

notes:'''

update_event_body = '''DAS Green Alert UPDATE
{serial}: {title}


The following fields have been changed:

title: New Title

-------------------

Full event data:

Conservancy: Sera

Details: some details about the event

Section/Area: Corner Safi

time: {time}

message: {text}

event_type: {type}

notes:'''

new_incident_body = '''DAS Green Alert
{serial}: {title}



Conservancy: Sera

Details: some details about the event

time: {time}

message: {text}

event_type: {type}

notes:'''

update_incident_body = '''DAS Green Alert UPDATE
{serial}: {title}


The following fields have been changed:

title: New Title

-------------------

Full event data:

Conservancy: Sera

Details: some details about the event

time: {time}

message: {text}

event_type: {type}

notes:'''

new_contained_event = '''DAS Green Alert
{serial}: {title} (contained in {parent})



Conservancy: Sera

Details: some details about the event

Section/Area: Corner Safi

time: {time}

message: {text}

event_type: {type}

notes: 

reported_by: Ranger 2'''

event_with_note_body = '''DAS Green Alert
{serial}: {title}



time: {time}

message: {text}

event_type: {type}

notes: first last: some text

reported_by: super'''


class TestEventView(TestCase):
    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'initial_choices')
        from choices.models import Conservancy
        count = Conservancy.objects.count()

        self.user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user(
            'super', 'super@test.com', 'super', is_superuser=True,
            is_staff=True, **self.user_const)
        self.readonly_user = User.objects.create_user(
            'readonly', 'readonly@test.com', 'readonly', **self.user_const)
        self.no_perms_user = User.objects.create_user(
            'noperms', 'noperms@test.com', 'noperms', **self.user_const)
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

        details = EventDetails.objects.create_event_details(
            event=self.event, data=event_schema_data)
        details.save()

        self.incident, self.contained_event = self.create_incident(
            self.event_data, self.event_data)
        self.contained_event.reported_by = Subject.objects.get(name='Ranger 2')

        details = EventDetails.objects.create_event_details(
            event=self.incident, data=incident_schema_data)
        details.save()

        details = EventDetails.objects.create_event_details(
            event=self.contained_event, data=event_schema_data)
        details.save()

        self.event.refresh_from_db()
        self.incident.refresh_from_db()

        self.event_with_note = self.create_event(self.event_data)
        EventNote.objects.create_note(
            event_id=self.event_with_note.id, text='some text', created_by_user=self.user)

        self.event_with_note.reported_by = self.user

    def time_to_string(self, time):
        return time.strftime('%A, %B %d, %Y at %H:%M')

    def create_event(self, event_data):
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

        return Event.objects.create_event(**data)

    def create_incident(self, incident_data, event_data):
        data = copy.deepcopy(incident_data)
        data['provenance'] = Event.PC_STAFF
        data['event_type'] = 'incident_collection'
        incident = self.create_event(data)

        data = copy.deepcopy(event_data)
        data['provenance'] = Event.PC_STAFF
        data['event_type'] = 'other'
        event = self.create_event(data)

        EventRelationship.objects.add_relationship(incident, event, 'contains')

        return incident, event

    def update_event(self, event):
        event.title = "New Title"
        event.save()
        revision = event.revision.all_user().order_by('sequence').last()
        return revision

    def test_new_event_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        mailer.send_event_mail(self.event, self.user, None, mail_callback)

        target_subject = base_target_subject.format(
            serial=self.event.serial_number,
            title=self.event.title)
        target_body = new_event_body.format(
            serial=self.event.serial_number,
            id=self.event.id,
            time=self.time_to_string(self.event.event_time),
            text=self.event.message,
            type=self.event.event_type.display,
            is_collection='False',
            provenance=self.event.get_display_value(
                'provenance', self.event.provenance),
            title='No Title',
            parent=0).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)

    def test_change_event_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        revision = self.update_event(self.event)

        mailer.send_event_mail(self.event, self.user, revision, mail_callback)
        target_subject = base_target_subject.format(
            serial=self.event.serial_number,
            title=self.event.title)
        target_body = update_event_body.format(
            serial=self.event.serial_number,
            id=self.event.id,
            time=self.time_to_string(self.event.event_time),
            text=self.event.message,
            type=self.event.event_type.display,
            is_collection='False',
            provenance=self.event.get_display_value(
                'provenance', self.event.provenance),
            title=self.event.title,
            parent=0).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)

    def test_new_incident_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        mailer.send_event_mail(self.incident, self.user, None, mail_callback)

        target_subject = base_target_subject.format(
            serial=self.incident.serial_number,
            title=self.incident.title)
        target_body = new_incident_body.format(
            serial=self.incident.serial_number,
            id=self.incident.id,
            time=self.time_to_string(self.incident.event_time),
            text=self.incident.message,
            type=self.incident.event_type.display,
            is_collection='True',
            provenance=self.incident.get_display_value(
                'provenance', self.incident.provenance),
            title='No Title',
            parent=0).strip()

        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)

    def test_change_incident_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        revision = self.update_event(self.incident)

        mailer.send_event_mail(self.incident, self.user,
                               revision, mail_callback)
        target_subject = base_target_subject.format(
            serial=self.incident.serial_number,
            title=self.incident.title)
        target_body = update_incident_body.format(
            serial=self.incident.serial_number,
            id=self.incident.id,
            time=self.time_to_string(self.incident.event_time),
            text=self.incident.message,
            type=self.incident.event_type.display,
            is_collection='True',
            provenance=self.incident.get_display_value(
                'provenance', self.incident.provenance),
            title=self.incident.title,
            parent=0).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)

    def test_contained_event_notiifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        mailer.send_event_mail(self.contained_event,
                               self.user, None, email_callback=mail_callback)
        target_subject = base_target_subject.format(
            serial=self.contained_event.serial_number,
            title=self.contained_event.title)
        target_body = new_contained_event.format(
            serial=self.contained_event.serial_number,
            id=self.contained_event.id,
            time=self.time_to_string(self.contained_event.event_time),
            text=self.contained_event.message,
            type=self.contained_event.event_type.display,
            is_collection='True',
            provenance=self.contained_event.get_display_value(
                'provenance', self.contained_event.provenance),
            title='No Title',
            parent=self.incident.serial_number).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)

    def test__alert_with_notes(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        mailer.send_event_mail(self.event_with_note, self.user, None,
                               email_callback=mail_callback)
        target_subject = base_target_subject.format(
            serial=self.event_with_note.serial_number,
            title=self.event_with_note.title)
        target_body = event_with_note_body.format(
            serial=self.event_with_note.serial_number,
            id=self.event_with_note.id,
            time=self.time_to_string(self.event_with_note.event_time),
            text=self.event_with_note.message,
            type=self.event_with_note.event_type.display,
            is_collection='False',
            provenance=self.event_with_note.get_display_value(
                'provenance', self.event_with_note.provenance),
            title='No Title',
            parent=0).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)


target_subject_template = 'Immobility Report: {name} {time}'
target_body_template = '''DAS Immobility Alert

Name: {name}
Start time of immobility (GMT): {time}
Probability: {probability}%
Sample Size: {sample}
Cluster Search Radius (meters): {radius}
Estimated Latitude: {lat}
Estimated Longitude: {lon}'''


class TestImmobilityEvent(TestCase):

    fixtures = ['initial_eventtype.yaml', 'analyzer_eventtype.yaml', 'initial_choices.yaml']
    def setUp(self):
        super().setUp()

        from choices.models import Conservancy
        count = Conservancy.objects.count()

        self.user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user(
            'super', 'super@test.com', 'super', is_superuser=True,
            is_staff=True, **self.user_const)
        self.readonly_user = User.objects.create_user(
            'readonly', 'readonly@test.com', 'readonly', **self.user_const)
        self.no_perms_user = User.objects.create_user(
            'noperms', 'noperms@test.com', 'noperms', **self.user_const)
        self.staff = Subject.objects.create(name='Ranger 2', additional={})


        analyzer_result_values = {
            'probability_value': 80,
            'cluster_radius': 13,
            'cluster_fix_count': 6,
            'total_fix_count': 26,
        }

        self.event_data = dict(
            message='Woody is immobile',
            time=pytz.utc.localize(datetime.utcnow()),
            provenance=Event.PC_ANALYZER,
            event_type='immobility',
            priority=Event.PRI_URGENT,
            location=dict(longitude='36.5', latitude='1.5')
        )

        self.subject_details = dict(
            name='Elle',
            additional={}
        )

        self.event = self.create_event(self.event_data)

        details = EventDetails.objects.create_event_details(
            event=self.event, data=analyzer_result_values)
        details.save()

        self.subject = self.create_subject(self.subject_details)

        EventAttachment.objects.create(target=self.subject, event=self.event)

        self.event.refresh_from_db()

    def time_to_string(self, time):
        return time.strftime('%A, %B %d, %Y at %H:%M')

    def create_subject(self, subject_data):
        data = copy.deepcopy(subject_data)
        return Subject.objects.create_subject(**data)

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


    def create_incident(self, incident_data, event_data):
        data = copy.deepcopy(incident_data)
        data['provenance'] = Event.PC_STAFF
        data['event_type'] = 'incident_collection'
        incident = self.create_event(data)

        data = copy.deepcopy(event_data)
        data['provenance'] = Event.PC_STAFF
        data['event_type'] = 'other'
        event = self.create_event(data)

        EventRelationship.objects.add_relationship(incident, event, 'contains')

        return incident, event

    def update_event(self, event):
        event.title = "New Title"
        event.save()
        revision = event.revision.all_user().order_by('sequence').last()
        return revision


    def test_new_event_notifications(self):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        mailer.send_immobility_mail(self.event, self.user, mail_callback)

        details = self.event.event_details.first().data

        target_subject = target_subject_template.format(
            name=self.event.subjects[0].name if len(self.event.subjects) > 0 else 'No Name',
            time=self.time_to_string(self.event.time))
        target_body = target_body_template.format(
            name=self.event.subjects[0].name if len(self.event.subjects) > 0 else 'No Name',
            time=self.time_to_string(self.event.event_time),
            probability=details['probability_value'],
            sample=details['total_fix_count'],
            radius=details['cluster_radius'],
            lat=self.event.location.x,
            lon=self.event.location.y).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)

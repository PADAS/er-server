import copy
import das_server.mailer as mailer
import django.contrib.auth
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from activity.models import Event, EventType, EventRelationship, EventDetails
from observations.models import Subject

User = django.contrib.auth.get_user_model()
ET_OTHER = 'immobility'

event_schema_data = {
    "event_details": {
        "details": 'an elephant stopped moving',
    }
}

target_from_address = 'notifications@pamdas.org'
target_subject_template = 'DAS Green Alert: {serial} {title}'
target_body_template = '''DAS Green Alert
{serial}: {title}



Details: some details about the event

Conservancy: Sera

Section/Area: Corner Safi

time: {time}

message: {text}

event_type: {type}

notes: []'''

class TestEventView(TestCase):
    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'initial_choices')

        self.user_const = dict(last_name='last', first_name='first')
        self.user = User.objects.create_user(
            'super', 'super@test.com', 'super', is_superuser=True,
            is_staff=True, **self.user_const)
        self.readonly_user = User.objects.create_user(
            'readonly','readonly@test.com', 'readonly', **self.user_const)
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

        self.event.refresh_from_db()

    def time_to_string(self, time):
        return time.strftime('%A, %B %d, %Y at %H:%M')


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

        mailer.send_event_mail(self.event, self.user, None, mail_callback)

        target_subject = target_subject_template.format(
            serial=self.event.serial_number,
            title=self.event.title)
        target_body = target_body_template.format(
            serial=self.event.serial_number,
            id=self.event.id,
            time=self.time_to_string(self.event.event_time),
            text=self.event.message,
            type=self.event.event_type.display,
            is_collection='False',
            provenance=self.event.get_display_value('provenance', self.event.provenance),
            title='No Title',
            parent=0).strip()
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)
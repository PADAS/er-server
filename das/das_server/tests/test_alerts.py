import copy
import das_server.mailer as mailer
import django.contrib.auth
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from accounts.models import PermissionSet
from activity.models import Event, EventType, EventRelationship, EventDetails, EventNote
from observations.models import Subject

User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'
ET_INCIDENT = 'incident_collection'


event_schema_data = {q
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

reported_by_permission_set_id = 'b5057387-9f6c-4685-8ec1-46ad29684eea'

base_target_subject = 'DAS Green Alert: {serial} {title}'
target_from_address = 'notifications@pamdas.org'

event_body = '''DAS {serial}: {title}
Priority: Green

  - Conservancy: Sera
  - Details: some details about the event
  - Section/Area: Corner Safi
  - Created On: {time}
  - Report Type: Other
  {updated} Title: {title}
  - Notes: Mr. DAS: When tweetle beetles fight, its called a tweetle beetle battle
Mr. DAS: Through three cheese trees three free fleas flew
  - Reported By: mr_das'''

incident_body = '''DAS {das_3_serial}: {das_3_title}
Priority: Green

  - Conservancy: Sera
  - Details: some details about the event
  - Created On: {das_3_time}
  - Report Type: Incident Collection
  {das_3_updated} Title: {das_3_title}
  - Notes: 
  - Reported By: mr_das


 - Contained Reports:

    - DAS {das_4_serial}: {das_4_title}
    - Priority: Green
       - Conservancy: Sera
       - Details: some details about the event
       - Section/Area: Corner Safi
       - Created On: {das_4_time}
       - Report Type: Other
       {das_4_updated} Title: {das_4_title}
       - Notes: Mr. DAS: Sue sews socks of fox in socks now. Slow Joe Crow sews Knox in box now. Sue sews rose on Slow Joe Crows clothes. Fox sews hose on Slow Joe Crows nose.
       - Reported By: mr_das

    - DAS {das_5_serial}: {das_5_title}
    - Priority: Green
       - Conservancy: Sera
       - Details: some details about the event
       - Section/Area: Corner Safi
       - Created On: {das_5_time}
       - Report Type: Other
       {das_5_updated} Title: {das_5_title}
       - Notes: Mr. DAS: If, sir, you, sir, choose to chew, sir, with the Goo-Goose, chew, sir. Do, sir.
Mr. DAS: Duck takes licks in lakes Luke Luck likes. Luke Luck takes licks in lakes duck likes
       - Reported By: mr_das'''


class TestEventView(TestCase):
    def setUp(self):
        super().setUp()
        call_command('loaddata', 'initial_eventdata')
        call_command('loaddata', 'initial_choices')
        from choices.models import Conservancy
        count = Conservancy.objects.count()

        self.reported_by_permission_set = PermissionSet.objects.get(
            id=reported_by_permission_set_id)

        self.user_const = dict(last_name='DAS ', first_name='Mr.')
        self.user = User.objects.create_user(
            'mr_das', 'mr_das@pamdas.org', 'Mr. DAS', is_superuser=True,
            is_staff=True, **self.user_const)
        self.user.permission_sets.add(self.reported_by_permission_set)
        self.readonly_user = User.objects.create_user(
            'readonly', 'readonly@test.com', 'readonly', **self.user_const)
        self.user.permission_sets.add(self.reported_by_permission_set)
        self.no_perms_user = User.objects.create_user(
            'noperms', 'noperms@test.com', 'noperms', **self.user_const)
        self.user.permission_sets.add(self.reported_by_permission_set)
        self.ranger_one = Subject.objects.create(
            name='Ranger One', additional={})
        self.ranger_two = Subject.objects.create(
            name='Ranger Two', additional={})
        self.ranger_red = Subject.objects.create(
            name='Ranger Red', additional={})
        self.ranger_blue = Subject.objects.create(
            name='Ranger Blue', additional={})

        self.incident_data = dict(
            title='New DAS Incident',
            message=lorem_ipsum.paragraph(),
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_INCIDENT,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517')
        )

        self.event_data = dict(
            title='New DAS Event',
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_SYSTEM,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517')
        )

        # Make the events
        self.standalone_event_one = self.create_event(self.event_data)
        self.standalone_event_two = self.create_event(self.event_data)
        self.parent_event = self.create_event(self.incident_data)
        self.child_event_one = self.create_event(self.event_data)
        self.child_event_two = self.create_event(self.event_data)

        # Set up the event relationships
        EventRelationship.objects.add_relationship(self.parent_event,
                                                   self.child_event_one,
                                                   'is_linked_to')
        EventRelationship.objects.add_relationship(self.parent_event,
                                                   self.child_event_one,
                                                   'contains')
        EventRelationship.objects.add_relationship(self.parent_event,
                                                   self.child_event_two,
                                                   'is_linked_to')
        EventRelationship.objects.add_relationship(self.parent_event,
                                                   self.child_event_two,
                                                   'contains')

        # Add schema data to the events
        details = EventDetails.objects.create_event_details(
            event=self.standalone_event_one, data=event_schema_data)
        details.save()
        details = EventDetails.objects.create_event_details(
            event=self.standalone_event_two, data=event_schema_data)
        details.save()
        details = EventDetails.objects.create_event_details(
            event=self.parent_event, data=event_schema_data)
        details.save()
        details = EventDetails.objects.create_event_details(
            event=self.child_event_one, data=event_schema_data)
        details.save()
        details = EventDetails.objects.create_event_details(
            event=self.child_event_two, data=event_schema_data)
        details.save()

        # Add reported_by
        self.standalone_event_one.reported_by = self.user
        self.standalone_event_one.provenance = 'staff'
        self.standalone_event_two.reported_by = self.user
        self.standalone_event_two.provenance = 'staff'
        self.parent_event.reported_by = self.user
        self.parent_event.provenance = 'staff'
        self.child_event_one.reported_by = self.user
        self.child_event_one.provenance = 'staff'
        self.child_event_two.reported_by = self.user
        self.child_event_two.provenance = 'staff'

        # Add some notes
        EventNote.objects.create_note(event_id=self.child_event_one.id,
                                      text='Sue sews socks of fox in socks now. Slow Joe Crow sews Knox in box now. Sue sews rose on Slow Joe Crows clothes. Fox sews hose on Slow Joe Crows nose.', created_by_user=self.user)
        EventNote.objects.create_note(event_id=self.child_event_two.id,
                                      text='If, sir, you, sir, choose to chew, sir, with the Goo-Goose, chew, sir. Do, sir.', created_by_user=self.user)
        EventNote.objects.create_note(event_id=self.child_event_two.id,
                                      text='Duck takes licks in lakes Luke Luck likes. Luke Luck takes licks in lakes duck likes', created_by_user=self.user)
        EventNote.objects.create_note(event_id=self.standalone_event_one.id,
                                      text='When tweetle beetles fight, its called a tweetle beetle battle', created_by_user=self.user)
        EventNote.objects.create_note(event_id=self.standalone_event_one.id,
                                      text='Through three cheese trees three free fleas flew', created_by_user=self.user)

        self.parent_event.save()
        self.child_event_one.save()
        self.child_event_two.save()
        self.standalone_event_one.save()
        self.standalone_event_two.save()
        self.parent_event.refresh_from_db()
        self.child_event_one.refresh_from_db()
        self.child_event_two.refresh_from_db()
        self.standalone_event_one.refresh_from_db()
        self.standalone_event_two.refresh_from_db()

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

    def time_to_string(self, time):
        return time.strftime('%A, %B %d, %Y at %H:%M')

    def update_event_title(self, event, new_title):
        event.title = new_title
        event.save()
        revision = event.revision.all_user().order_by('sequence').last()
        return revision

    def get_base_template_fields(self):
        return {
            'das_3_title': self.parent_event.title or 'No Title',
            'das_4_title': self.child_event_one.title or 'No Title',
            'das_5_title': self.child_event_two.title or 'No Title',
            'das_3_serial': self.parent_event.serial_number,
            'das_4_serial': self.child_event_one.serial_number,
            'das_5_serial': self.child_event_two.serial_number,
            'das_3_time': self.time_to_string(self.parent_event.time),
            'das_4_time': self.time_to_string(self.child_event_one.time),
            'das_5_time': self.time_to_string(self.child_event_two.time),
            'das_3_updated': '-',
            'das_4_updated': '-',
            'das_5_updated': '-',
        }

    def test_create_incident_with_children(self):
        base_fields = self.get_base_template_fields()
        target_subject = base_target_subject.format(
            serial=self.parent_event.serial_number,
            title=self.parent_event.title)
        target_body = incident_body.format(**base_fields).strip()

        self.base_test(self.parent_event, self.user, None,
                       target_subject, target_body)

    def test_update_parent_in_incident(self):
        revision = self.update_event_title(
            self.parent_event, 'One Fish, Two Fish, Red Fish, Blue Fish')
        base_fields = self.get_base_template_fields()
        base_fields['das_3_updated'] = '*'
        target_subject = base_target_subject.format(
            serial=self.parent_event.serial_number,
            title=self.parent_event.title)
        target_body = incident_body.format(**base_fields).strip()

        self.base_test(self.child_event_two, self.user, revision,
                       target_subject, target_body)

    def test_update_child_in_incident(self):
        revision = self.update_event_title(
            self.child_event_one, 'The Cat in the Hat')
        base_fields = self.get_base_template_fields()
        base_fields['das_4_updated'] = '*'
        target_subject = base_target_subject.format(
            serial=self.parent_event.serial_number,
            title=self.parent_event.title)
        target_body = incident_body.format(**base_fields).strip()

        self.base_test(self.child_event_two, self.user,
                       revision, target_subject, target_body)

    def test_create_standalone_event(self):
        base_fields = {'serial': self.standalone_event_one.serial_number,
                       'title': self.standalone_event_one.title or 'No Title',
                       'updated': '-',
                       'time': self.time_to_string(self.standalone_event_one.time)}
        target_subject = base_target_subject.format(
            serial=self.standalone_event_one.serial_number,
            title=self.standalone_event_one.title or 'No Title')
        target_body = event_body.format(**base_fields).strip()

        self.base_test(self.standalone_event_one, self.user, None, target_subject,
                       target_body)

    def test_update_standalone_event(self):
        revision = self.update_event_title(
            self.standalone_event_one, 'Hop On Pop')
        base_fields = {'serial': self.standalone_event_one.serial_number,
                       'title': self.standalone_event_one.title or 'No Title',
                       'updated': '*',
                       'time': self.time_to_string(
                           self.standalone_event_one.time)}
        target_subject = base_target_subject.format(
            serial=self.standalone_event_one.serial_number,
            title=self.standalone_event_one.title or 'No Title')
        target_body = event_body.format(**base_fields).strip()

        self.base_test(self.standalone_event_one, self.user,
                       revision, target_subject, target_body)

    def base_test(self, event, user, revision, target_subject, target_body):
        email_data = {}

        def mail_callback(subject, body, from_address):
            email_data['subject'] = subject
            email_data['body'] = body.strip()
            email_data['from_address'] = from_address

        mailer.send_event_mail(event, user, revision, mail_callback)
        self.assertEquals(email_data['subject'], target_subject)
        self.assertEquals(email_data['body'], target_body)
        self.assertEquals(email_data['from_address'], target_from_address)

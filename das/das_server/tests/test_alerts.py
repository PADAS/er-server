import copy
import pytz
import das_server.mailer as mailer
import django.contrib.auth
from datetime import datetime
import django.conf as django_conf
from django.utils import lorem_ipsum
from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command
from rest_framework.fields import DateTimeField
from drf_extra_fields.geo_fields import PointField

from accounts.models.user import AccountsAbstractUser
from accounts.models import PermissionSet
from activity.models import Event, EventType, EventRelationship, EventDetails, EventNote
import activity.signals
from observations.models import Subject

from unittest.mock import call, patch

from das_server.tasks import get_alert_users
import das_server.tests.mocks.mock_routing as mock_routing

User = django.contrib.auth.get_user_model()
ET_OTHER = 'other'
ET_INCIDENT = 'incident_collection'


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

reported_by_permission_set_id = 'b5057387-9f6c-4685-8ec1-46ad29684eea'

base_target_subject = 'DAS Green Alert: {serial} {title}'
target_from_address = 'notifications@pamdas.org'

new_event_body = '''DAS {serial}: {title}
Priority: Green

  - Created On: {time}
  - Report Type: Other
  - Title: {title}
  - Notes: 
  - Reported By: mr_das'''

update_event_body = '''DAS {serial}: {title}
Priority: Green

  - Conservancy: Sera
  - Details: some details about the event
  - Section/Area: Corner Safi
  - Created On: {time}
  - Report Type: Other
  - Title: {title}
  - Notes: 
  - Reported By: mr_das'''

new_parent_child_body = '''DAS {parent_serial}: {parent_title}
Priority: Green

  - Created On: {parent_time}
  - Report Type: Incident Collection
  - Title: {parent_title}
  - Notes: 
  - Reported By: mr_das


 - Contained Reports:

    - DAS {child_serial}: {child_title}
    - Priority: Green
       - Created On: {child_time}
       - Report Type: Other
       - Title: {child_title}
       - Notes: 
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
            is_staff=True, is_email_alert=True, **self.user_const)
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
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_STAFF,
            event_type=ET_INCIDENT,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517'),
            reported_by=self.user,
        )

        self.event_data = dict(
            title='New DAS Event',
            time=DateTimeField().to_representation(timezone.now()),
            provenance=Event.PC_STAFF,
            event_type=ET_OTHER,
            priority=Event.PRI_REFERENCE,
            location=dict(longitude='40.1353', latitude='-1.891517'),
            reported_by=self.user,
        )

        # Make a standalone event that we will update later
        self.standalone_event = self.create_event(self.event_data)
        self.standalone_event.refresh_from_db()

        self.parent_one = self.create_event(self.incident_data)
        self.child_one = self.create_event(self.event_data)
        EventRelationship.objects.add_relationship(
            self.parent_one, self.child_one, 'contains')
        self.child_one.refresh_from_db()
        self.parent_one.refresh_from_db()

        self.parent_two = self.create_event(self.incident_data)
        self.child_two = self.create_event(self.event_data)
        EventRelationship.objects.add_relationship(
            self.parent_two, self.child_two, 'contains')
        self.child_two.refresh_from_db()
        self.parent_two.refresh_from_db()

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

    # @patch.object(AccountsAbstractUser, 'email_user')
    # @patch('das_server.celery.app.send_task', side_effect=mock_routing.mock_send_task)
    # @patch('activity.alerts.get_alert_users')
    # def test_create_new_standalone_event(self, mock_get_alert_users, mock_task, mock_send_email):
    #
    #     # Configure mocks
    #     mock_get_alert_users.return_value = [self.user]
    #
    #     # Do the event creation
    #     new_event = self.create_event(self.event_data)
    #     new_event.refresh_from_db()
    #
    #     # Generate the target email fields
    #     target_body = new_event_body.format(
    #         serial=new_event.serial_number,
    #         title=new_event.title or 'No Title',
    #         time=self.time_to_string(new_event.time)).strip()
    #     target_subject = base_target_subject.format(
    #         serial=new_event.serial_number,
    #         title=new_event.title)
    #
    #     # Make sure the mocks were called the correct number of times with the
    #     # correct values
    #     mock_get_alert_users.assert_called_once()
    #     mock_task.assert_called_once()
    #     mock_send_email.assert_called_once_with(target_subject, target_body,
    #                                             target_from_address)

    # @patch.object(AccountsAbstractUser, 'email_user')
    # @patch('das_server.celery.app.send_task', side_effect=mock_routing.mock_send_task)
    # @patch.object(AlertUtils, 'get_alert_users')
    # def test_update_existing_event(self, mock_get_alert_users, mock_task, mock_send_email):
    #     # Configure mocks
    #     mock_get_alert_users.return_value = [self.user]
    #
    #     # Modify the event
    #     EventDetails.objects.create_event_details(
    #         event=self.standalone_event, data=event_schema_data)
    #
    #     # Generate the target email fields
    #     target_body = update_event_body.format(
    #         serial=self.standalone_event.serial_number,
    #         title=self.standalone_event.title or 'No Title',
    #         time=self.time_to_string(self.standalone_event.time)).strip()
    #     target_subject = base_target_subject.format(
    #         serial=self.standalone_event.serial_number,
    #         title=self.standalone_event.title)
    #
    #     # Make sure the mocks were called the correct number of times with the
    #     # correct values
    #     mock_get_alert_users.assert_called_once()
    #     mock_task.assert_called_once()
    #     mock_send_email.assert_called_once_with(target_subject, target_body,
    #                                             target_from_address)
    #
    # @patch.object(AccountsAbstractUser, 'email_user')
    # @patch('das_server.celery.app.send_task', side_effect=mock_routing.mock_send_task)
    # @patch.object(AlertUtils, 'get_alert_users')
    # def test_create_event_and_incident(self, mock_get_alert_users, mock_task, mock_send_email):
    #     # Configure mocks
    #     mock_get_alert_users.return_value = [self.user]
    #
    #     # Create the events and the relationship between them
    #     child = self.create_event(self.event_data)
    #     parent = self.create_event(self.incident_data)
    #     EventRelationship.objects.add_relationship(parent, child, 'contains')
    #     child.refresh_from_db()
    #     parent.refresh_from_db()
    #
    #     # Generate the target email fields
    #     target_body = new_parent_child_body.format(
    #         parent_serial=parent.serial_number,
    #         parent_title=parent.title or 'No Title',
    #         parent_time=self.time_to_string(parent.time),
    #         child_serial=child.serial_number,
    #         child_title=child.title or 'No Title',
    #         child_time=self.time_to_string(child.time)).strip()
    #     target_subject = base_target_subject.format(
    #         serial=parent.serial_number,
    #         title=parent.title)
    #
    #     # Make sure the mocks were called the correct number of times with the correct values
    #     # TODO database signaling is working differently during tests,which
    #     # is causing three emails to be sent instead of 2. In a real scenario,
    #     # the creation of the incident and the relationship would be batched
    #     # into one transaction and result in one fewer email. If they aren't
    #     # batched, three emails is the correct amount
    #     self.assertEquals(mock_task.call_count, 3, "mock_task called {0} times".format(
    #         mock_task.call_count))
    #     self.assertEquals(mock_send_email.call_count, 3, "mock_send_email called {0} times".format(
    #         mock_send_email.call_count))
    #     mock_send_email.assert_called_with(
    #         target_subject, target_body, target_from_address)
    #
    @patch.object(AccountsAbstractUser, 'email_user')
    @patch('das_server.celery.app.send_task', side_effect=mock_routing.mock_send_task)
    @patch('das_server.tasks.get_alert_users')
    def test_update_child_event(self, mock_get_alert_users, mock_task, mock_send_email):
        # Configure mocks
        mock_get_alert_users.return_value = [self.user]

        # Create the events and the relationship between them
        self.child_one.title = 'Now I have a new title'
        self.child_one.save()

        # Generate the target email fields
        target_body = new_parent_child_body.format(
            parent_serial=self.parent_one.serial_number,
            parent_title=self.parent_one.title or 'No Title',
            parent_time=self.time_to_string(self.parent_one.time),
            child_serial=self.child_one.serial_number,
            child_title=self.child_one.title or 'No Title',
            child_time=self.time_to_string(self.child_one.time)).strip()
        target_subject = base_target_subject.format(
            serial=self.parent_one.serial_number,
            title=self.parent_one.title)

        # Make sure the mocks were called the correct number of times with the correct values
        # TODO database signaling is working differently during tests,which
        # is causing three emails to be sent instead of 2. In a real scenario,
        # the creation of the incident and the relationship would be batched
        # into one transaction and result in one fewer email. If they aren't
        # batched, three emails is the correct amount
        self.assertEquals(mock_task.call_count, 1, "mock_task called {0} times".format(
            mock_task.call_count))
        self.assertEquals(mock_send_email.call_count, 1, "mock_send_email called {0} times".format(
            mock_send_email.call_count))
        mock_send_email.assert_called_with(
            target_subject, target_body, target_from_address)
    #
    # @patch.object(AccountsAbstractUser, 'email_user')
    # @patch('das_server.celery.app.send_task',
    #        side_effect=mock_routing.mock_send_task)
    # @patch.object(AlertUtils, 'get_alert_users')
    # def test_update_parent_event(self, mock_get_alert_users, mock_task,
    #                              mock_send_email):
    #     # Configure mocks
    #     mock_get_alert_users.return_value = [self.user]
    #
    #     # Create the events and the relationship between them
    #     self.parent_two.title = 'Now I have a new title'
    #     self.parent_two.save()
    #
    #     # Generate the target email fields
    #     target_body = new_parent_child_body.format(
    #         parent_serial=self.parent_two.serial_number,
    #         parent_title=self.parent_two.title or 'No Title',
    #         parent_time=self.time_to_string(self.parent_two.time),
    #         child_serial=self.child_two.serial_number,
    #         child_title=self.child_two.title or 'No Title',
    #         child_time=self.time_to_string(self.child_two.time)).strip()
    #     target_subject = base_target_subject.format(
    #         serial=self.parent_two.serial_number,
    #         title=self.parent_two.title)
    #
    #     # Make sure the mocks were called the correct number of times with the correct values
    #     # TODO database signaling is working differently during tests,which
    #     # is causing three emails to be sent instead of 2. In a real scenario,
    #     # the creation of the incident and the relationship would be batched
    #     # into one transaction and result in one fewer email. If they aren't
    #     # batched, three emails is the correct amount
    #     self.assertEquals(mock_task.call_count, 1,
    #                       "mock_task called {0} times".format(
    #                           mock_task.call_count))
    #     self.assertEquals(mock_send_email.call_count, 1,
    #                       "mock_send_email called {0} times".format(
    #                           mock_send_email.call_count))
    #     mock_send_email.assert_called_with(target_subject, target_body,
    #                                        target_from_address)

import json
import logging
import time
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core import mail
from django.core.management import call_command
from django.db.models.signals import post_save
from django.test import TestCase
from mockredis import mock_redis_client, MockRedis

from accounts.models import User, PermissionSet
from activity.alerting.message import coerce_state_value, send_event_alert, render_event_alert_context
from activity.alerting.service import evaluate_event
from activity.models import Event, NotificationMethod, AlertRule, EventType, \
    EventDetails, EventCategory
from activity.signals import event_post_save
from activity.tasks import send_alert_to_notificationmethod, \
    evaluate_conditions_for_sending_alerts, evaluate_alert_rules
from observations.models import Subject, SubjectType, SubjectSubType
from choices.models import DynamicChoice

logger = logging.getLogger(__name__)


user_permissions = [
    'security_read', 'security_create', 'security_update', 'security_delete']


@patch('redis.StrictRedis', MockRedis)
class TestAlerts(TestCase):
    def setUp(self) -> None:
        call_command('loaddata', 'event_data_model')
        self.states = [{'name': 'New', 'value': 'new'},
                       {'name': 'Active', 'value': 'active'},
                       {'name': 'Resolved', 'value': 'resolved'}]

        self.alerts_permissionset = PermissionSet.objects.get(
            name='Alert Rule Permissions')

        for perm in user_permissions:
            self.alerts_permissionset.permissions.add(
                Permission.objects.get(codename=perm))

        self.owner = User.objects.create_user(
            username='owner',
            password='asdfo9823sfdsdsiu23$',
            email='alertsuser@tempuri.org')

        self.owner.permission_sets.add(self.alerts_permissionset)

        category = EventCategory.objects.get(value="security")

        self.event_type = EventType.objects.create(
            display="AlertTest",
            value="alert_test",
            schema=json.dumps({
                "schema": {
                    "$schema": "http://json-schema.org/draft-04/schema#",
                    "title": "EventType Test Data",
                    "type": "object",
                    "required": [
                        "details"
                    ],
                    "properties": {
                        "sex": {
                            "type": "string",
                            "title": "Sex of animal",
                            "enum": [
                                "Male",
                                "Female",
                                "Unknown"
                            ]
                        }
                    }
                },
                "definition": [
                    "sex"
                ]
            }),
            category=category
        )

        self.notification_method = NotificationMethod. \
            objects.create(owner=self.owner,
                           title="Email",
                           method='email',
                           value="test@test.com")

        # create alert rule
        self.alert_rule = AlertRule.objects.create(
            owner=self.owner,
            title="Alert",
            conditions={
                "all": [
                    {
                        "name": "sex",
                        "value": "Male",
                        "operator": "equal_to"
                    }
                ]
            },
            schedule={"timezone": "Africa/Nairobi"},
        )

        self.alert_rule.notification_methods.add(self.notification_method)
        self.alert_rule.event_types.add(self.event_type)

    def test_alert_coerces_to_the_right_state_val(self):
        for state in self.states:
            self.assertEqual(state.get('name'),
                             coerce_state_value(val=state.get('value')))

    @patch("activity.alerting.message.send_report")
    def test_sending_email_alert(self, mock_send_report):

        post_save.disconnect(event_post_save, sender=Event)

        event = Event.objects.create(title="test event",
                                     event_type=self.event_type,
                                     created_by_user=self.owner)

        # new rule, if update within 1 second of create Event record, the update is
        # still considered new.
        time.sleep(1)

        # event updated here
        event_details = EventDetails.objects.create(event=event, data={
            "event_details": {"sex": "Male"}})
        send_event_alert(alert_rule_id=self.alert_rule.id, event_id=event.id,
                         notification_method_id=self.notification_method.id)

        self.assertTrue(mock_send_report.called)
        _, kwargs = mock_send_report.call_args
        self.assertEqual(self.notification_method.value, kwargs.get('to_email'))
        self.assertIn("updated", kwargs.get('subject'))
        self.assertIn("Active", kwargs.get('html_content'))

    def test_only_sending_notifications_when_the_condition_value_changes(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            notification_method = NotificationMethod. \
                objects.create(owner=self.owner,
                               title="Email",
                               method='email',
                               value="test@test.com")

            alert_rule = AlertRule.objects.create(
                owner=self.owner,
                title="State is one of resolved",
                conditions={
                    "all": [
                        {
                            "name": "state",
                            "value": [
                                "resolved",
                                "new"
                            ],
                            "operator": "shares_at_least_one_element_with"
                        }
                    ]
                }
            )

            alert_rule.notification_methods.add(notification_method)
            alert_rule.event_types.add(self.event_type)

            event = Event.objects.create(title="test event",
                                         event_type=self.event_type,
                                         created_by_user=self.owner, state="new")
#            EventDetails.objects.create(event=event, data={
#                "event_details": {"sex": "Male"}})

            evaluate_alert_rules(event.id, created=True)


            self.assertEqual(len(mail.outbox), 1)

            # update event title, no email should be sent
            time.sleep(1) # follow on update must be more than 1 sec from created_at time
            event.title = "New title"
            event.save()

            evaluate_alert_rules(event.id, created=False)

            # no email sent so outbox should still have 1 email
            self.assertEqual(len(mail.outbox), 1)

    def test_checkbox_event_details_returned_with_correct_titles_on_alert(self):
        DynamicChoice.objects.create(
            id="queens",
            model_name='observations.subject', 
            criteria='[["subject_subtype", "queens"], ["additional__sex", "female"]]',
            value_col='id',
            display_col='name')

        subject_type = SubjectType.objects.create(value='Cats')
        subject_subtype = SubjectSubType.objects.create(value='queens', subject_type=subject_type)
        subject = Subject.objects.create(name='Katie Kitten', subject_subtype=subject_subtype, additional={'sex':'female'})

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
        event_type = self.event_type
        event_type.schema = et_schema
        event_type.save()

        notification_method = NotificationMethod.objects.create(
            owner=self.owner,
            title="Email",
            method='email',
            value="test@test.com")

        alert_rule = AlertRule.objects.create(
            owner=self.owner,
            conditions={
                "all": [
                    { 
                        "name": "kitten", "value": [str(subject.id)],
                        "operator": "shares_at_least_one_element_with"
                    }
                ]})

        alert_rule.notification_methods.add(notification_method)
        alert_rule.event_types.add(self.event_type)
        event = Event.objects.create(
            title="test event",
            event_type=self.event_type,
            created_by_user=self.owner, state="new")

        EventDetails.objects.create(
            data={"event_details": {"kitten": [str(subject.id)]}},
            event=event)
        report_context = render_event_alert_context(
            alert_rule, event, notification_method,
            event_updated_fields={}, event_details_updated_fields={})

        details_sent_to_mail = dict(report_context.get('pretty_details').get('kitten'))
        expected_detail = {'title': 'Test checkbox with query', 'value': 'Katie Kitten'}

        # details sent to email as titles rather than guids, checkbox title returned
        self. assertTrue(expected_detail == details_sent_to_mail)
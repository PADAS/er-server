import json
import logging
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from django_multitenant.utils import get_current_tenant, set_current_tenant
from mockredis import MockRedis

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.core import mail
from django.core.management import call_command
from django.db.models.signals import post_save
from django.test import override_settings

from accounts.models import PermissionSet, User
from accounts.utils import permission_get_by_natural_key
from activity.alerting.message import (
    coerce_state_value,
    render_event_alert_context,
    render_to_whatsapp_content,
    send_event_alert,
)
from activity.alerting.rate_limit import (
    KEY_ALERT_LIMIT,
    allow_send_event_alert,
    get_alert_counter,
    get_or_set_user_alerts_counter,
    get_remaining_alert_count,
    increment_alert_counter,
    prepend_alert_warning_message,
    publish_user_alert_quota_percentage,
    reset_alerts_counter,
)
from activity.alerts import has_alerts_permissionset
from activity.alerts_views import AlertRuleListView
from activity.models import (
    NOTIFICATION_METHOD_EMAIL,
    NOTIFICATION_METHOD_SMS,
    NOTIFICATION_METHOD_WHATSAPP,
    AlertRule,
    Event,
    EventCategory,
    EventDetails,
    EventType,
    NotificationMethod,
)
from activity.serializers import EventSerializer
from activity.signals import event_post_save
from activity.tasks import execute_evaluate_alert_rules
from choices.models import DynamicChoice
from core.tests import BaseAPITest
from core.utils import NonHttpRequest
from factories import PermissionSetFactory
from observations.models import (
    SEX_FEMALE,
    Subject,
    SubjectGroup,
    SubjectSubType,
    SubjectType,
)
from utils.tenant import Tenant

logger = logging.getLogger(__name__)

user_permissions = ["security_read", "security_create", "security_update", "security_delete"]


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAlertPermissions:
    @pytest.fixture
    def alerts_permissionset(self):
        permissions = [
            Permission.objects.get_by_natural_key("view_alertrule", "activity", "alertrule"),
        ]
        permission_set = PermissionSetFactory.create(permissions=permissions)
        return permission_set

    def test_alerts_enabled_for_any_user_with_view_alerts_permission(self, user_client, alerts_permissionset):
        user_client.user.permission_sets.add(alerts_permissionset)

        assert has_alerts_permissionset(user_client.user)


@patch("redis.StrictRedis", MockRedis)
@patch("django.contrib.auth.models.PermissionManager.get_by_natural_key", permission_get_by_natural_key)
class TestAlerts(BaseAPITest):
    def setUp(self) -> None:
        super().setUp()
        call_command("loaddata_with_tenant", "event_data_model")
        self.states = [
            {"name": "New", "value": "new"},
            {"name": "Active", "value": "active"},
            {"name": "Resolved", "value": "resolved"},
        ]

        self.alerts_permissionset, _ = PermissionSet.objects.get_or_create(name="Alert Rule Permissions")

        for perm in user_permissions:
            self.alerts_permissionset.permissions.add(
                Permission.objects.get_by_natural_key(codename=perm, app_label="activity", model="event")
            )

        self.owner = User.objects.create_user(
            username="owner", password="asdfo9823sfdsdsiu23$", email="alertsuser@tempuri.org"
        )

        self.owner.permission_sets.add(self.alerts_permissionset)

        self.category = EventCategory.objects.get(value="security")

        self.event_type = EventType.objects.create(
            display="AlertTest",
            value="alert_test",
            schema=json.dumps(
                {
                    "schema": {
                        "$schema": "http://json-schema.org/draft-04/schema#",
                        "title": "EventType Test Data",
                        "type": "object",
                        "required": ["details"],
                        "properties": {
                            "sex": {"type": "string", "title": "Sex of animal", "enum": ["Male", "Female", "Unknown"]}
                        },
                    },
                    "definition": ["sex"],
                }
            ),
            category=self.category,
        )

        self.notification_method = NotificationMethod.objects.create(
            owner=self.owner, title="Email", method=NOTIFICATION_METHOD_EMAIL, value="test@test.com"
        )

        # create alert rule
        self.alert_rule = AlertRule.objects.create(
            owner=self.owner,
            title="Alert",
            conditions={"all": [{"name": "sex", "value": "Male", "operator": "equal_to"}]},
            schedule={"timezone": "Africa/Nairobi"},
        )

        self.alert_rule.notification_methods.add(self.notification_method)
        self.alert_rule.event_types.add(self.event_type)

        self.tenant_mock = MagicMock()
        self.tenant_mock.time_zone = "America/Los_Angeles"
        self.tenant_mock.default_from_email = "er@pamdas.org"

    def test_alert_coerces_to_the_right_state_val(self):
        for state in self.states:
            self.assertEqual(state.get("name"), coerce_state_value(val=state.get("value")))

    @pytest.mark.skip(
        reason="expensive test loading up a second tenants data for one test, was used to figure out an issue"
    )
    @pytest.mark.usefixtures("tenant_two")
    def test_create_alert_in_one_tenant_with_common_eventtype(self):
        # activity/tests/test_alerts.py::TestAlerts::test_create_alert_in_one_tenant_with_common_eventtype
        tenant_two_tenant = self.tenant_two[0]

        previous_tenant = get_current_tenant()
        set_current_tenant(tenant_two_tenant)
        tenant_two_event_type = EventType.objects.get(value="animal_control_rep")
        set_current_tenant(previous_tenant)

        defaults = dict(
            display=tenant_two_event_type.display, schema=tenant_two_event_type.schema, category=self.category
        )
        event_type, created = EventType.objects.get_or_create(value=tenant_two_event_type.value, defaults=defaults)

        alert_rule = {
            "title": "Alert Test",
            "conditions": {"all": []},
            "reportTypes": ["animal_control_rep"],
            "schedule": {},
            "is_active": True,
            "notifications": [self.notification_method.id],
            "notification_method_ids": [self.notification_method.id],
        }

        request = self.factory.post(self.api_base + "/activity/alerts", alert_rule)
        self.force_authenticate(request, self.owner)

        response = AlertRuleListView.as_view()(request)

        assert response.status_code == 201

    @patch("activity.alerting.message.send_report")
    def test_sending_email_alert(self, mock_send_report):
        post_save.disconnect(event_post_save, sender=Event)

        event = Event.objects.create(title="test event", event_type=self.event_type, created_by_user=self.owner)

        # new rule, if update within 1 second of create Event record, the update is
        # still considered new.
        time.sleep(1)

        EventDetails.objects.create(event=event, data={"event_details": {"sex": "Male"}})
        send_event_alert(
            alert_rule_id=self.alert_rule.id, event_id=event.id, notification_method_id=self.notification_method.id
        )
        self.assertTrue(mock_send_report.called)
        _, kwargs = mock_send_report.call_args
        self.assertEqual(self.notification_method.value, kwargs.get("to_email"))
        self.assertIn("updated", kwargs.get("subject"))
        self.assertIn("Active", kwargs.get("html_content"))

    def test_alert_url_contains_correct_event_details(self):
        """Test that the alert url contains the correct event details"""
        event = Event.objects.create(title="test event", event_type=self.event_type, created_by_user=self.owner)
        EventDetails.objects.create(event=event, data={"event_details": {"sex": "Female"}})
        report_context = render_event_alert_context(
            self.alert_rule, event, self.notification_method, event_updated_fields={}, event_details_updated_fields={}
        )
        self.assertTrue("site_url" in report_context)
        self.assertTrue(report_context.get("site_url").endswith(f"/events/{event.id}"))
        self.assertTrue("lnglat" not in report_context.get("site_url"))

        event.location = Point(-103.313486, 20.420935)
        event.save()
        report_context = render_event_alert_context(
            self.alert_rule, event, self.notification_method, event_updated_fields={}, event_details_updated_fields={}
        )
        self.assertTrue("lnglat" in report_context.get("site_url"))

    def test_whatsapp_render_contains_alert_url_and_location(self):
        event = Event.objects.create(title="test event", event_type=self.event_type, created_by_user=self.owner)
        EventDetails.objects.create(event=event, data={"event_details": {"sex": "Female"}})
        report_context = render_event_alert_context(
            self.alert_rule, event, self.notification_method, event_updated_fields={}, event_details_updated_fields={}
        )
        whatsapp_content = render_to_whatsapp_content(report_context)
        assert whatsapp_content["7"].endswith(f"/events/{event.id}")
        assert "lnglat" not in whatsapp_content["7"]

        event.location = Point(-103.313486, 20.420935)
        event.save()
        report_context = render_event_alert_context(
            self.alert_rule, event, self.notification_method, event_updated_fields={}, event_details_updated_fields={}
        )
        whatsapp_content = render_to_whatsapp_content(report_context)
        assert "lnglat" in whatsapp_content["7"]

    def test_sending_notification_for_new_event_delay_on_event_details_add(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            notification_method = NotificationMethod.objects.create(
                owner=self.owner, title="Email", method="email", value="test@test.com"
            )

            AlertRule.objects.all().delete()

            alert_rule = AlertRule.objects.create(
                owner=self.owner,
                title="State is one of resolved",
                conditions={
                    "all": [{"name": "state", "value": ["new"], "operator": "shares_at_least_one_element_with"}]
                },
                schedule={"timezone": "Europe/Warsaw"},
            )

            alert_rule.notification_methods.add(notification_method)
            alert_rule.event_types.add(self.event_type)

            request = NonHttpRequest()
            request.user = self.owner
            ser = EventSerializer(
                data={
                    "title": "test event",
                    "event_type": self.event_type.value,
                    "created_by_user": self.owner.id,
                    "state": "new",
                    "event_time": datetime.now(tz=timezone.utc),
                    "event_details": {"sex": "Male"},
                },
                context={"request": request},
            )

            assert ser.is_valid()

            event = ser.create(ser.validated_data)
            event = Event.objects.get(id=event.id)
            event_details = EventDetails.objects.get(event=event)
            revision = event_details.revision.all().latest("revision_at")
            revision.revision_at = revision.revision_at + timedelta(seconds=2)
            revision.save()

            execute_evaluate_alert_rules(event.id, created=True, domain="zoo.com")

            self.assertEqual(len(mail.outbox), 1)

    def test_only_sending_notifications_when_the_condition_value_changes(self):
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            notification_method = NotificationMethod.objects.create(
                owner=self.owner, title="Email", method="email", value="test@test.com"
            )

            alert_rule = AlertRule.objects.create(
                owner=self.owner,
                title="State is one of resolved",
                conditions={
                    "all": [
                        {"name": "state", "value": ["resolved", "new"], "operator": "shares_at_least_one_element_with"}
                    ]
                },
                schedule={"timezone": "Europe/Warsaw"},
            )

            alert_rule.notification_methods.add(notification_method)
            alert_rule.event_types.add(self.event_type)

            event = Event.objects.create(
                title="test event", event_type=self.event_type, created_by_user=self.owner, state="new"
            )

            execute_evaluate_alert_rules(event.id, created=True, domain="zoo.com")

            self.assertEqual(len(mail.outbox), 1)

            # update event title, no email should be sent
            time.sleep(1)  # follow on update must be more than 1 sec from created_at time
            event.title = "New title"
            event.save()

            execute_evaluate_alert_rules(event.id, created=False, domain="zoo.com")

            # no email sent so outbox should still have 1 email
            self.assertEqual(len(mail.outbox), 1)

    def test_checkbox_event_details_returned_with_correct_titles_on_alert(self):
        DynamicChoice.objects.create(
            choice_name="queens",
            model_name="observations.subject",
            criteria='[["subject_subtype", "queens"], ["additional__sex", "female"]]',
            value_col="id",
            display_col="name",
        )

        subject_type = SubjectType.objects.create(value="Cats")
        subject_subtype = SubjectSubType.objects.create(value="queens", subject_type=subject_type)
        subject = Subject.objects.create(
            name="Katie Kitten", subject_subtype=subject_subtype, additional={"sex": SEX_FEMALE}
        )

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
            owner=self.owner, title="Email", method="email", value="test@test.com"
        )

        alert_rule = AlertRule.objects.create(
            owner=self.owner,
            conditions={
                "all": [{"name": "kitten", "value": [str(subject.id)], "operator": "shares_at_least_one_element_with"}]
            },
        )

        alert_rule.notification_methods.add(notification_method)
        alert_rule.event_types.add(self.event_type)
        event = Event.objects.create(
            title="test event", event_type=self.event_type, created_by_user=self.owner, state="new"
        )

        EventDetails.objects.create(data={"event_details": {"kitten": [str(subject.id)]}}, event=event)
        report_context = render_event_alert_context(
            alert_rule, event, notification_method, event_updated_fields={}, event_details_updated_fields={}
        )

        details_sent_to_mail = dict(report_context.get("pretty_details").get("kitten"))
        expected_detail = {"title": "Test checkbox with query", "value": "Katie Kitten"}

        # details sent to email as titles rather than guids, checkbox title returned
        self.assertDictEqual(expected_detail, details_sent_to_mail)

    def test_alert_rules_owned_by_inactive_users_are_skipped(self):
        """Test that alert rules owned by inactive users are not processed (ERA-11874)"""
        # Clear existing alert rules to avoid interference
        AlertRule.objects.all().delete()

        # Create an inactive user
        inactive_user = User.objects.create_user(
            username="inactive_user", password="asdfo9823sfdsdsiu23$", email="inactive@tempuri.org", is_active=False
        )
        inactive_user.permission_sets.add(self.alerts_permissionset)

        # Create alert rule owned by inactive user
        inactive_alert_rule = AlertRule.objects.create(
            owner=inactive_user,
            title="Inactive User Alert",
            conditions={"all": [{"name": "sex", "value": "Male", "operator": "equal_to"}]},
            schedule={"timezone": "Africa/Nairobi"},
        )
        inactive_alert_rule.notification_methods.add(self.notification_method)
        inactive_alert_rule.event_types.add(self.event_type)

        # Create event that would trigger the alert
        event = Event.objects.create(
            title="test event", event_type=self.event_type, created_by_user=self.owner, state="new"
        )
        EventDetails.objects.create(event=event, data={"event_details": {"sex": "Male"}})

        # Execute alert evaluation
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            execute_evaluate_alert_rules(event.id, created=True, domain="zoo.com")

        # No email should be sent because the alert rule owner is inactive
        self.assertEqual(len(mail.outbox), 0)

    def test_alert_rules_owned_by_active_users_are_processed(self):
        """Test that alert rules owned by active users are still processed normally"""
        # Create an active user
        active_user = User.objects.create_user(
            username="active_user", password="asdfo9823sfdsdsiu23$", email="active@tempuri.org", is_active=True
        )
        active_user.permission_sets.add(self.alerts_permissionset)

        # Create notification method for active user
        active_notification_method = NotificationMethod.objects.create(
            owner=active_user, title="Active Email", method="email", value="active@test.com"
        )

        # Create alert rule owned by active user
        active_alert_rule = AlertRule.objects.create(
            owner=active_user,
            title="Active User Alert",
            conditions={"all": [{"name": "sex", "value": "Female", "operator": "equal_to"}]},
            schedule={"timezone": "Africa/Nairobi"},
        )
        active_alert_rule.notification_methods.add(active_notification_method)
        active_alert_rule.event_types.add(self.event_type)

        # Create event that would trigger the alert
        event = Event.objects.create(
            title="test event", event_type=self.event_type, created_by_user=self.owner, state="new"
        )
        EventDetails.objects.create(event=event, data={"event_details": {"sex": "Female"}})

        # Execute alert evaluation
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            execute_evaluate_alert_rules(event.id, created=True, domain="zoo.com")

        # Email should be sent because the alert rule owner is active
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["active@test.com"])

    @patch("sendsms.api.send_sms")
    def test_alert_rule_override_sms_message(self, mock_send_sms):

        alert_rule = AlertRule.objects.create(
            owner=self.owner,
            title="Alert",
            conditions={"all": [{"name": "sex", "value": "Male", "operator": "equal_to"}]},
            schedule={"timezone": "Africa/Nairobi"},
            override_message="This is an override message.",
        )
        event = Event.objects.create(title="test event", event_type=self.event_type, created_by_user=self.owner)

        EventDetails.objects.create(event=event, data={"event_details": {"sex": "Female"}})

        notification_method = NotificationMethod.objects.create(
            owner=self.owner, title="Text", method=NOTIFICATION_METHOD_SMS, value="+14155552671"
        )

        send_event_alert(alert_rule_id=alert_rule.id, event_id=event.id, notification_method_id=notification_method.id)

        self.assertTrue(mock_send_sms.called)
        _, kwargs = mock_send_sms.call_args
        self.assertEqual(alert_rule.override_message, kwargs.get("body"))

    @patch("activity.alerting.message.send_report")
    def test_alert_rule_override_email_message(self, mock_send_email):

        alert_rule = AlertRule.objects.create(
            owner=self.owner,
            title="Alert",
            conditions={"all": [{"name": "sex", "value": "Male", "operator": "equal_to"}]},
            schedule={"timezone": "Africa/Nairobi"},
            override_message="This is an override message.",
        )
        event = Event.objects.create(title="test event", event_type=self.event_type, created_by_user=self.owner)

        EventDetails.objects.create(event=event, data={"event_details": {"sex": "Female"}})

        notification_method = NotificationMethod.objects.create(
            owner=self.owner, title="Email", method=NOTIFICATION_METHOD_EMAIL, value="test@example.com"
        )

        send_event_alert(alert_rule_id=alert_rule.id, event_id=event.id, notification_method_id=notification_method.id)

        self.assertTrue(mock_send_email.called)
        _, kwargs = mock_send_email.call_args
        self.assertEqual(alert_rule.override_message, kwargs.get("html_content"))
        self.assertEqual(alert_rule.override_message, kwargs.get("text_content"))

    @patch("activity.alerting.message.send_whatsapp")
    def test_whatsapp_alert_for_geofence_event_with_nested_subject_group(self, mock_send_whatsapp):
        """A WhatsApp alert should fire for a geofence-break event whose subject belongs
        to a child subject group when the alert rule is conditioned on the parent subject
        group (i.e. the group assigned to the geofence analyzer)."""
        with self.settings(CELERY_TASK_ALWAYS_EAGER=True):
            subject_type, _ = SubjectType.objects.get_or_create(value="wildlife", defaults={"display": "Wildlife"})
            subject_subtype, _ = SubjectSubType.objects.get_or_create(
                value="elephant", defaults={"display": "Elephant", "subject_type": subject_type}
            )
            subject = Subject.objects.create(name="Geofence Elephant", subject_subtype=subject_subtype)

            # Build the hierarchy: parent_sg → child_sg → subject.
            # The geofence analyzer is conceptually assigned to parent_sg; the subject
            # is only a direct member of child_sg.
            child_sg = SubjectGroup.objects.create(name="alert_test_child_sg")
            child_sg.subjects.add(subject)
            # Give the alert rule owner subject-level access via the child group, so that
            # render_event_alert_context can render the event when sending the notification.
            child_sg.permission_sets.add(self.alerts_permissionset)

            parent_sg = SubjectGroup.objects.create(name="alert_test_parent_sg")
            parent_sg.children.add(child_sg)

            # Geofence-break event type (mirrors what the analyzer creates).
            analyzer_ec, _ = EventCategory.objects.get_or_create(
                value="analyzer_event", defaults={"display": "Analyzer Events"}
            )
            geofence_event_type, _ = EventType.objects.get_or_create(
                value="geofence_break",
                category=analyzer_ec,
                defaults={"display": "Geofence Break"},
            )

            whatsapp_nm = NotificationMethod.objects.create(
                owner=self.owner,
                title="WhatsApp",
                method=NOTIFICATION_METHOD_WHATSAPP,
                value="+14155552671",
            )

            # Alert rule conditioned on parent_sg; the subject is only directly in child_sg.
            alert_rule = AlertRule.objects.create(
                owner=self.owner,
                title="Geofence WhatsApp Alert",
                conditions={
                    "all": [
                        {
                            "name": "subject_group",
                            "value": [str(parent_sg.id)],
                            "operator": "shares_at_least_one_element_with",
                        }
                    ]
                },
                schedule={"timezone": "Africa/Nairobi"},
            )
            alert_rule.notification_methods.add(whatsapp_nm)
            alert_rule.event_types.add(geofence_event_type)

            # render_event_alert_context renders the event as the alert rule owner, so the
            # owner must have read permission on the event category. Grant it here.
            analyzer_event_read = Permission.objects.get_by_natural_key(
                codename="analyzer_event_read", app_label="activity", model="event"
            )
            self.alerts_permissionset.permissions.add(analyzer_event_read)

            # Simulate the event the geofence analyzer would create.
            event = Event.objects.create(
                title="Elephant crossed geofence",
                event_type=geofence_event_type,
                created_by_user=self.owner,
            )
            event.related_subjects.add(subject)

            execute_evaluate_alert_rules(event.id, created=True, domain="zoo.com")

            self.assertTrue(
                mock_send_whatsapp.called,
                "Expected a WhatsApp message for a geofence event whose subject is in a "
                "child subject group of the group specified in the alert rule condition.",
            )


@pytest.mark.django_db
class TestAlertsLimit:
    @pytest.mark.usefixtures("tenant_settings")
    def test_set_alert_counter(self, superuser, monkeypatch):
        mock = MagicMock(return_value=0)
        monkeypatch.setattr("activity.alerting.rate_limit.alerts_storage.insert_key", mock)

        counter = reset_alerts_counter(superuser)
        key = KEY_ALERT_LIMIT.format(str(superuser.id))

        mock.assert_called_once_with(key=key, value=0, ttl=settings.ALERTS_RATE_LIMIT_DURATION_SECONDS)
        assert counter == 0

    @pytest.mark.parametrize("value", [0, None])
    @pytest.mark.usefixtures("tenant_settings")
    def test_get_alert_counter(self, value, superuser, monkeypatch):
        mock = MagicMock(return_value=value)
        monkeypatch.setattr("activity.alerting.rate_limit.alerts_storage.get_key", mock)

        counter = get_alert_counter(superuser)
        key = KEY_ALERT_LIMIT.format(superuser.id)

        mock.assert_called_once_with(key)
        assert counter == 0

    @pytest.mark.usefixtures("tenant_settings")
    def test_get_or_set_user_alerts_counter_with_existing_value(self, superuser, monkeypatch):
        mock = MagicMock(return_value=10)
        monkeypatch.setattr("activity.alerting.rate_limit.alerts_storage.get_key", mock)

        counter = get_or_set_user_alerts_counter(superuser)
        key = KEY_ALERT_LIMIT.format(superuser.id)

        mock.assert_called_once_with(key)
        assert counter == 10

    @pytest.mark.usefixtures("tenant_settings")
    def test_get_or_set_user_alerts_counter_without_existing_value(self, superuser, monkeypatch):
        mock_get_key = MagicMock(return_value=None)
        monkeypatch.setattr("activity.alerting.rate_limit.alerts_storage.get_key", mock_get_key)

        mock_set_key = MagicMock(return_value=0)
        monkeypatch.setattr("activity.alerting.rate_limit.alerts_storage.insert_key", mock_set_key)

        counter = get_or_set_user_alerts_counter(superuser)
        key = KEY_ALERT_LIMIT.format(superuser.id)

        mock_get_key.assert_called_once_with(key)
        mock_set_key.assert_called_once_with(key=key, value=0, ttl=settings.ALERTS_RATE_LIMIT_DURATION_SECONDS)
        assert counter == 0

    @pytest.mark.usefixtures("tenant_settings")
    def test_increment_alert_counter(self, superuser, monkeypatch, caplog, tenant_response):
        caplog.set_level(logging.INFO)
        mock = MagicMock(return_value=1)
        monkeypatch.setattr("activity.alerting.rate_limit.alerts_storage.increment_key_by_value", mock)
        tenant_settings = Tenant.from_dict(tenant_response)
        monkeypatch.setattr("activity.alerting.rate_limit.get_tenant_settings", MagicMock(return_value=tenant_settings))

        increment_alert_counter(superuser, NOTIFICATION_METHOD_EMAIL)
        key = KEY_ALERT_LIMIT.format(superuser.id)

        mock.assert_called_once_with(key, 1)
        tenant_domain = tenant_response["domain"]
        assert f"Site {tenant_domain} message sent {NOTIFICATION_METHOD_EMAIL} alert" in caplog.text

    @override_settings(ALERTS_RATE_LIMIT=20)
    @pytest.mark.usefixtures("tenant_settings")
    def test_allow_send_event_alert_allowed(self, superuser, monkeypatch):
        mock = MagicMock(return_value=1)
        monkeypatch.setattr("activity.alerting.rate_limit.alerts_storage.get_key", mock)

        key = KEY_ALERT_LIMIT.format(superuser.id)

        assert allow_send_event_alert(superuser)
        mock.assert_called_once_with(key)

    def test_allow_send_event_alert_not_allowed(self, superuser, monkeypatch, tenant_settings):
        mock = MagicMock(return_value=20)
        monkeypatch.setattr("activity.alerting.rate_limit.alerts_storage.get_key", mock)
        tenant_settings.env_settings.alert_rate_limit = 20

        key = KEY_ALERT_LIMIT.format(superuser.id)

        assert not allow_send_event_alert(superuser)
        mock.assert_called_once_with(key)

    @pytest.mark.parametrize("counter,percentage", [[10, ""], [18, "90.0"]])
    def test_publish_user_alert_quota_percentage(self, counter, percentage, superuser, caplog, tenant_settings):
        tenant_settings.env_settings.alert_rate_limit = 20
        caplog.set_level(logging.INFO)

        publish_user_alert_quota_percentage(superuser, counter)

        assert percentage in caplog.text

    @pytest.mark.parametrize("counter,exp_remaining", [[0, 19], [5, 14], [10, 9], [15, 4], [20, -1]])
    def test_get_remaining_alert_count(self, superuser, counter, exp_remaining, monkeypatch, tenant_settings):
        tenant_settings.env_settings.alert_rate_limit = 20
        mock = MagicMock(return_value=counter)
        monkeypatch.setattr("activity.alerting.rate_limit.get_or_set_user_alerts_counter", mock)

        remaining = get_remaining_alert_count(superuser)

        mock.assert_called_once_with(superuser)
        assert remaining == exp_remaining

    @override_settings(ALERTS_REMAINING_COUNTER_FOR_WARNING=3)
    @pytest.mark.parametrize(
        "counter,expected",
        [[5, False], [4, False], [3, True], [2, True], [1, True], [0, True]],
    )
    def test_prepend_alert_warning_message(self, counter, expected, superuser, monkeypatch, tenant_settings):
        tenant_settings.env_settings.alert_rate_limit = 20
        mock = MagicMock(return_value=counter)
        monkeypatch.setattr("activity.alerting.rate_limit.get_remaining_alert_count", mock)

        assert prepend_alert_warning_message(superuser) == expected
        mock.assert_called_once_with(superuser)

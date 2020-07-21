import json
import uuid

import django.db.models as models
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.cookie import CookieStorage
from django.db import connection
from django.test import RequestFactory, override_settings

from activity.admin import RefreshRecreateEventDetailViewAdmin
from activity.materialized_view import (check_db_view_exists, generate_DDL,
                                        re_create_view,
                                        refresh_materialized_view)
from activity.models import (Event, EventCategory, EventDetails,
                             EventType, RefreshRecreateEventDetailView)
from core.tests import BaseAPITest


class MockSuperUser:
    def has_perm(self, perm):
        return True


class details_view(models.Model):
    # Test model to view records saved to event_details materialized view
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    event_type = models.CharField(max_length=50)
    subjects_name = models.CharField(max_length=50)
    behavior_choice = models.CharField(max_length=50)
    behavior = models.CharField(max_length=50)

    class Meta:
        managed = False


class TestMaterializedView(BaseAPITest):

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.request = RequestFactory()
        self.admin = RefreshRecreateEventDetailViewAdmin(
            model=RefreshRecreateEventDetailView, admin_site=self.site)
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(details_view)

    def test_execute_generated_ddl(self):
        re_create_view()
        self.assertTrue(check_db_view_exists())

        refresh_materialized_view()
        self.assertTrue(check_db_view_exists())

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_when_admin_refresh_view(self):
        request = self.request.get('/admin')
        request.user = MockSuperUser()

        # NOTE: For this test to pass, celery must run concurrently
        messages = CookieStorage(request)
        setattr(request, '_messages', messages)

        response = self.admin.refresh_view(request)
        self.assertEqual(messages._queued_messages[0].message,
                         "Successfully refresh 'event_detail_view'")
        self.assertEqual(response.status_code, 302)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_when_admin_recreate_view(self):
        request = self.request.get('/admin')
        request.user = MockSuperUser()

        # NOTE: For this test to pass, celery must run concurrently
        messages = CookieStorage(request)
        setattr(request, '_messages', messages)

        response = self.admin.recreate_view(request)
        self.assertEqual(messages._queued_messages[0].message,
                         "Successfully recreate 'event_detail_view'")
        self.assertEqual(response.status_code, 302)

    def test_enum_values_returned_instead_of_names(self):

        # array types, old and new enum(string types) representations normalised to detail value
        schema = json.dumps({
            "schema":
                {"properties": {
                    "subjects_name": {"type": "string", "title": "enum test"},
                    "behavior_choice": {"type": "string", "title": "name and value test"},
                    "behavior": {"type": "array", "title": "array test"}}
                },
            "definition": ["behavior_choice"]
            })

        self.event_type = EventType.objects.filter(value="immobility").first()
        self.event_type.schema = schema
        self.event_type.save()

        self.event = Event.objects.create(
            title="test event", event_type=self.event_type,
            created_by_user=self.app_user, state="new")
        EventDetails.objects.create(
            data={
                "event_details": {
                    "subjects_name": "fatu",
                    "behavior_choice": {"name": "Ambushed", "value": "ambushed"},
                    "behavior": [{"name": "sleeping", "value": "b1"}, {"name": "eating", "value": "b2"}]}
            },
            event=self.event)

        # clear all eventtypes to focus ddl generation on one eventtype
        EventType.objects.exclude(value="immobility").delete()

        # Send query data to a sample model instead of the materialized view to read output
        query_string = 'select '
        for line in generate_DDL()[1:]:
            query_string += line

        detail = details_view.objects.raw(query_string)[0]

        self.assertTrue(detail.subjects_name == 'fatu')
        self.assertTrue(detail.behavior_choice == 'ambushed')
        self.assertTrue(detail.behavior == ['b1', 'b2'])

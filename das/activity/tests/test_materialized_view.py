from django.test import RequestFactory, override_settings
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.cookie import CookieStorage

from core.tests import BaseAPITest
from activity.models import RefreshRecreateEventDetailView
from activity.admin import RefreshRecreateEventDetailViewAdmin
from activity.materialized_view import re_create_view, refresh_materialized_view, check_db_view_exists


class MockSuperUser:
    def has_perm(self, perm):
        return True

class TestMaterializedView(BaseAPITest):

    def setUp(self):
        super().setUp()
        self.site = AdminSite()
        self.request = RequestFactory()
        self.admin = RefreshRecreateEventDetailViewAdmin(model=RefreshRecreateEventDetailView, admin_site=self.site)

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

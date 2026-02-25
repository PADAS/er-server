import json
import logging
from datetime import timedelta
from unittest.mock import patch

import pytest

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import DisallowedHost
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from client_http import HTTPClient
from core.models.oauth import DASAccessToken, DASApplication
from factories import SubjectFactory
from utils.efb_token import EFB_COOKIE_NAME
from utils.features import features
from utils.middleware import (
    EFB_APPLICATION_ID,
    ManageAdminEFBTokenMiddleware,
    TenantSettingsMiddleware,
)
from utils.tenant.thread import Tenant, get_tenant_settings


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestTenantSettingsMiddleware:
    @pytest.mark.skipif(not features.tms.is_on(), reason="TMS feature flag is off")
    @pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    def test_tenant_settings_middleware_getting_tenant(self, mocked_tenant_client, tenant_response, rf):
        mocked_tenant_client.return_value = tenant_response

        client = HTTPClient()
        user = client.app_user

        url = f"{reverse('events')}"
        request = rf.get(url)
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        settings_middleware(request)
        settings = get_tenant_settings()

        assert isinstance(settings, Tenant)
        assert json.loads(settings.to_json()) == tenant_response

    @pytest.mark.skipif(features.tms.is_on(), reason="TMS feature flag is on")
    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    def test_tenant_settings_middleware_getting_tenant_from_django(self, mocked_tenant_client, tenant_response, rf):
        mocked_tenant_client.return_value = tenant_response
        client = HTTPClient()
        user = client.app_user
        url = f"{reverse('events')}"
        request = rf.get(url)
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        settings_middleware(request)
        settings = get_tenant_settings()

        assert isinstance(settings, Tenant)
        assert json.loads(settings.to_json()) == tenant_response

    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    @patch("utils.tenant.domains.get_current_cluster_domains")
    @override_settings(ALLOWED_HOSTS=["testserver.org", "localhost"])
    def test_middleware_adds_valid_tenant(self, mocked_cluster_domains, mocked_tenant_client, tenant_response, rf):
        mocked_tenant_client.return_value = tenant_response
        mocked_cluster_domains.return_value = ["tenant.testserver.org"]
        client = HTTPClient()
        user = client.app_user
        url = f"{reverse('events')}"
        request = rf.get(url, HTTP_HOST="tenant.testserver.org")
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        settings_middleware(request)

        from django.conf import settings

        assert request.get_host() in settings.ALLOWED_HOSTS

    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    @patch("utils.tenant.domains.get_current_cluster_domains")
    @override_settings(ALLOWED_HOSTS=["testserver.org", "tenant.testserver.org"])
    def test_middleware_ignores_known_tenant(self, mocked_cluster_domains, mocked_tenant_client, tenant_response, rf):
        mocked_tenant_client.return_value = tenant_response
        mocked_cluster_domains.return_value = ["tenant.testserver.org"]
        client = HTTPClient()
        user = client.app_user
        url = f"{reverse('events')}"
        request = rf.get(url, HTTP_HOST="tenant.testserver.org")
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        settings_middleware(request)

        assert not mocked_cluster_domains.called

    @patch("utils.tenant.providers.TenantData.get_tenant_data")
    @patch("utils.tenant.domains.get_current_cluster_domains")
    @override_settings(ALLOWED_HOSTS=["testserver.org", "test.testserver.org", "localhost"])
    def test_middleware_fails_with_invalid_tenant(
        self, mocked_cluster_domains, mocked_tenant_client, tenant_response, caplog, rf
    ):
        caplog.set_level(logging.INFO)
        mocked_tenant_client.return_value = tenant_response
        mocked_cluster_domains.return_value = ["tenant.testserver.org"]
        client = HTTPClient()
        user = client.app_user
        url = f"{reverse('events')}"
        request = rf.get(url, HTTP_HOST="not-a-tenant.testserver.org")
        request.user = user

        settings_middleware = TenantSettingsMiddleware(self._get_response)
        with pytest.raises(DisallowedHost):
            settings_middleware(request)

        from django.conf import settings

        assert "not-a-tenant.testserver.org" not in settings.ALLOWED_HOSTS

    def _get_response(self, request):
        return HttpResponse()


@pytest.mark.django_db
class TestManageAdminEFBTokenMiddleware:
    @pytest.fixture(autouse=True)
    def setup(self, superuser, superuser_client):
        self.middleware = ManageAdminEFBTokenMiddleware(lambda r: None)
        self.factory = RequestFactory()
        self.client = superuser_client
        self.superuser = superuser
        self.efb_app = DASApplication.objects.get(client_id=EFB_APPLICATION_ID)

    def _create_admin_request(self, path="/admin/login"):  # Proper supports request session
        request = self.factory.get(path)
        request.user = self.superuser

        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        request.session["_auth_user_id"] = str(self.superuser.id)
        request.session.save()

        return request

    def test_token_creation_on_admin_access(self):
        request = self._create_admin_request()
        response = self.client.get("/admin/login")
        response = self.middleware.process_response(request, response)

        assert EFB_COOKIE_NAME in response.cookies
        token = DASAccessToken.objects.get(user=self.superuser, application__client_id=EFB_APPLICATION_ID)
        assert response.cookies[EFB_COOKIE_NAME].value == token.token

    def test_generated_token_can_access_api(self, user_client):
        admin_request = self._create_admin_request()
        admin_response = self.client.get("/admin/login")
        admin_response = self.middleware.process_response(admin_request, admin_response)

        token = admin_response.cookies[EFB_COOKIE_NAME].value
        user_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        SubjectFactory.create_batch(5)
        res = user_client.get(reverse("subjects-list-view"))
        assert res.status_code == 200
        assert len(res.data) == 5

    def test_no_duplicate_token_creation_cookie_created_with_valid_token(self):
        DASAccessToken.objects.create(
            user=self.superuser,
            application=self.efb_app,
            token="existing_token",
            expires=timezone.now() + timedelta(days=1),
        )

        request = self._create_admin_request()
        response = self.client.get("/admin/login")
        response = self.middleware.process_response(request, response)

        tokens = DASAccessToken.objects.filter(user=self.superuser, application__client_id=EFB_APPLICATION_ID)
        assert tokens.count() == 1
        assert tokens.first().token == "existing_token"
        assert EFB_COOKIE_NAME in response.cookies  # This means existing valid token is re-setted on response

    def test_token_invalidation_with_cookie(self):
        test_token = "test_token_123"
        DASAccessToken.objects.create(
            token=test_token, user=self.superuser, application=self.efb_app, expires=timezone.now() + timedelta(days=1)
        )

        request = self._create_admin_request("/admin/logout")
        request.COOKIES = {EFB_COOKIE_NAME: test_token}

        response = self.client.get("/admin/logout")
        response = self.middleware.process_response(request, response)

        assert not DASAccessToken.objects.filter(token=test_token).exists()
        assert EFB_COOKIE_NAME in response.cookies
        assert response.cookies[EFB_COOKIE_NAME].value == ""

    def test_token_cleanup_without_cookie(self):
        DASAccessToken.objects.create(
            user=self.superuser,
            application=self.efb_app,
            token="orphan_token",
            expires=timezone.now() + timedelta(days=1),
        )

        request = self._create_admin_request("/admin/logout")
        request.COOKIES = {}

        response = self.client.get("/admin/logout")
        response = self.middleware.process_response(request, response)

        assert not DASAccessToken.objects.filter(
            user=self.superuser, application__client_id=EFB_APPLICATION_ID
        ).exists()

    def test_no_token_cleanup_for_anonymous(self):
        request = self.factory.get("/admin/logout")
        request.user = AnonymousUser()
        request.COOKIES = {EFB_COOKIE_NAME: "any_token"}

        response = self.client.get("/admin/logout")
        response = self.middleware.process_response(request, response)

        assert EFB_COOKIE_NAME in response.cookies
        assert response.cookies[EFB_COOKIE_NAME].value == ""

    @patch("utils.middleware.ManageAdminEFBTokenMiddleware._should_create_efb_token", return_value=False)
    def test_error_handling_during_token_deletion(self, _, caplog):
        with patch("core.models.oauth.DASAccessToken.objects.filter", side_effect=Exception("DB Error")) as mock_delete:
            request = self._create_admin_request("/admin/logout")
            request.COOKIES = {EFB_COOKIE_NAME: "test_token"}

            response = self.middleware.process_response(request, HttpResponse())

            assert "Error: DB Error invalidating" in caplog.text
            assert EFB_COOKIE_NAME in response.cookies
            assert response.cookies[EFB_COOKIE_NAME].value == ""
            mock_delete.assert_called_once()

    @patch("utils.middleware.ManageAdminEFBTokenMiddleware._should_create_efb_token", return_value=False)
    def test_error_handling_during_token_deletion_without_cookie(self, _, caplog):
        """DB error on the no-cookie cleanup path should not crash the logout request."""
        with patch("core.models.oauth.DASAccessToken.objects.filter", side_effect=Exception("DB Error")):
            request = self._create_admin_request("/admin/logout")
            request.COOKIES = {}

            response = self.middleware.process_response(request, HttpResponse())

            assert response.status_code == 200
            assert "Error: DB Error invalidating" in caplog.text

    def test_expired_token_replacement(self):
        DASAccessToken.objects.create(
            user=self.superuser,
            application=self.efb_app,
            token="expired_token",
            expires=timezone.now() - timedelta(days=1),
        )

        request = self._create_admin_request()
        response = self.client.get("/admin/login")
        response = self.middleware.process_response(request, response)

        tokens = DASAccessToken.objects.filter(user=self.superuser, application__client_id=EFB_APPLICATION_ID)
        assert tokens.count() == 2
        assert "expired_token" in [t.token for t in tokens]
        assert EFB_COOKIE_NAME in response.cookies

    def test_token_not_created_for_non_staff_user(self, user, user_client):
        user.is_staff = False
        user.save()
        DASAccessToken.objects.all().delete()

        request = RequestFactory().get("/admin/login")
        request.user = user

        response = user_client.get("/admin/login")
        response = self.middleware.process_response(request, response)

        assert not DASAccessToken.objects.filter(user=user, application__client_id=EFB_APPLICATION_ID).exists()
        assert EFB_COOKIE_NAME not in response.cookies

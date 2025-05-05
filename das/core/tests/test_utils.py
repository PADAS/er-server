from datetime import timedelta
from unittest.mock import patch

import pytest

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models.oauth import DASAccessToken, DASApplication
from core.utils import get_site_name, is_uuid
from factories import SubjectFactory
from utils.authentication import (
    EFB_ACCESS_TOKEN_NAME,
    EFB_APPLICATION_ID,
    AdminEFBTokenAuthentication,
)


class TestUtils(TestCase):
    def test_site_name(self):
        site_urls = ["https://mysite.pamdas.org", "https://mysite.apn.pamdas.org"]
        site_name = "mysite"
        for site in site_urls:
            settings.UI_SITE_URL = site
            self.assertEqual(site_name, get_site_name())


@pytest.mark.django_db
class TestIsUUD:
    @pytest.mark.parametrize(
        "string,expected",
        [
            ("f9b2cbd3-a82e-4aec-b46e-4ebf5bdbd441", True),
            ("this-is-not-a-uuid", False),
            (12, False),
        ],
    )
    def test_string_is_uud(self, string, expected):
        is_string_uuid = is_uuid(string)

        assert is_string_uuid is expected


@pytest.mark.django_db
class TestAdminEFBTokenAuthentication:
    @pytest.fixture(autouse=True)
    def setup(self, superuser, superuser_client):
        self.middleware = AdminEFBTokenAuthentication(lambda r: None)
        self.factory = RequestFactory()
        self.client = superuser_client
        self.superuser = superuser
        self.efb_app = DASApplication.objects.create(
            client_id=EFB_APPLICATION_ID,
            client_type="Confidential",
            authorization_grant_type="password",
            name="Test EFB App",
        )

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

        assert EFB_ACCESS_TOKEN_NAME in response.cookies
        token = DASAccessToken.objects.get(user=self.superuser, application__client_id=EFB_APPLICATION_ID)
        assert response.cookies[EFB_ACCESS_TOKEN_NAME].value == token.token

    def test_generated_token_can_access_api(self, user_client):
        admin_request = self._create_admin_request()
        admin_response = self.client.get("/admin/login")
        admin_response = self.middleware.process_response(admin_request, admin_response)

        token = admin_response.cookies[EFB_ACCESS_TOKEN_NAME].value
        user_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        SubjectFactory.create_batch(5)
        res = user_client.get(reverse("subjects-list-view"))
        assert res.status_code == 200
        assert len(res.data) == 5

    def test_no_duplicate_token_creation(self):
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
        assert EFB_ACCESS_TOKEN_NAME not in response.cookies

    def test_token_invalidation_with_cookie(self):
        test_token = "test_token_123"
        DASAccessToken.objects.create(
            token=test_token, user=self.superuser, application=self.efb_app, expires=timezone.now() + timedelta(days=1)
        )

        request = self._create_admin_request("/admin/logout")
        request.COOKIES = {EFB_ACCESS_TOKEN_NAME: test_token}

        response = self.client.get("/admin/logout")
        response = self.middleware.process_response(request, response)

        assert not DASAccessToken.objects.filter(token=test_token).exists()
        assert EFB_ACCESS_TOKEN_NAME in response.cookies
        assert response.cookies[EFB_ACCESS_TOKEN_NAME].value == ""

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
        request.COOKIES = {EFB_ACCESS_TOKEN_NAME: "any_token"}

        response = self.client.get("/admin/logout")
        response = self.middleware.process_response(request, response)

        assert EFB_ACCESS_TOKEN_NAME in response.cookies
        assert response.cookies[EFB_ACCESS_TOKEN_NAME].value == ""

    @patch("utils.authentication.AdminEFBTokenAuthentication._can_create_efb_token", return_value=False)
    def test_error_handling_during_token_deletion(self, caplog):
        with patch("core.models.oauth.DASAccessToken.objects.filter", side_effect=Exception("DB Error")) as mock_delete:
            with pytest.raises(Exception):
                request = self._create_admin_request("/admin/logout")
                request.COOKIES = {EFB_ACCESS_TOKEN_NAME: "test_token"}

                response = self.client.get("/admin/logout")
                response = self.middleware.process_response(request, response)

                assert "Error: DB Error invalidating" in caplog.text

                assert EFB_ACCESS_TOKEN_NAME in response.cookies
                assert response.cookies[EFB_ACCESS_TOKEN_NAME].value == ""
                mock_delete.assert_called_once()

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
        assert EFB_ACCESS_TOKEN_NAME in response.cookies

    def test_token_not_created_for_non_staff_user(self, user, user_client):
        user.is_staff = False
        user.save()
        DASAccessToken.objects.all().delete()

        request = RequestFactory().get("/admin/login")
        request.user = user

        response = user_client.get("/admin/login")
        response = self.middleware.process_response(request, response)

        assert not DASAccessToken.objects.filter(user=user, application__client_id=EFB_APPLICATION_ID).exists()
        assert EFB_ACCESS_TOKEN_NAME not in response.cookies

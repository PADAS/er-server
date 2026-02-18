from datetime import timedelta

import pytest

from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import timezone

from core.models.oauth import DASAccessToken, DASApplication
from utils.efb_token import (
    EFB_APPLICATION_ID,
    EFB_COOKIE_NAME,
    get_or_create_efb_token,
    set_efb_token_cookie,
)


@pytest.fixture
def efb_app(superuser):
    """Ensure EFB application exists for the test tenant (fixture only)."""
    app, _ = DASApplication.objects.get_or_create(
        client_id=EFB_APPLICATION_ID,
        defaults={
            "client_type": "Confidential",
            "authorization_grant_type": "password",
            "client_secret": "",
            "name": "Event Form Builder Admin App",
            "skip_authorization": True,
        },
    )
    return app


@pytest.mark.django_db
class TestGetOrCreateEfbToken:
    @pytest.fixture(autouse=True)
    def setup(self, superuser, efb_app):
        self.superuser = superuser
        self.efb_app = efb_app

    def test_returns_existing_valid_token(self):
        existing = DASAccessToken.objects.create(
            user=self.superuser,
            application=self.efb_app,
            token="existing_valid_token",
            expires=timezone.now() + timedelta(days=1),
        )

        result = get_or_create_efb_token(self.superuser)

        assert result.pk == existing.pk
        assert result.token == "existing_valid_token"

    def test_ignores_expired_token_and_creates_new(self):
        DASAccessToken.objects.create(
            user=self.superuser,
            application=self.efb_app,
            token="expired_token",
            expires=timezone.now() - timedelta(days=1),
        )

        result = get_or_create_efb_token(self.superuser)

        assert result is not None
        assert result.token != "expired_token"
        assert result.expires > timezone.now()

    def test_creates_token_when_none_exists(self):
        DASAccessToken.objects.filter(application__client_id=EFB_APPLICATION_ID, user=self.superuser).delete()

        result = get_or_create_efb_token(self.superuser)

        assert result is not None
        assert result.user == self.superuser
        assert result.application.client_id == EFB_APPLICATION_ID
        assert result.scope == "read write"

    def test_returns_none_when_efb_app_missing(self):
        DASApplication.objects.filter(client_id=EFB_APPLICATION_ID).delete()

        result = get_or_create_efb_token(self.superuser)

        assert result is None


@pytest.mark.django_db
class TestSetEfbTokenCookie:
    @pytest.fixture(autouse=True)
    def setup(self, superuser, efb_app):
        self.superuser = superuser
        self.factory = RequestFactory()

    def test_sets_cookie_for_authenticated_staff(self):
        request = self.factory.get("/")
        request.user = self.superuser

        response = HttpResponse()
        set_efb_token_cookie(request, response)

        assert EFB_COOKIE_NAME in response.cookies
        token_value = response.cookies[EFB_COOKIE_NAME].value
        assert DASAccessToken.objects.filter(token=token_value).exists()

    def test_noop_for_unauthenticated_user(self):
        from django.contrib.auth.models import AnonymousUser

        request = self.factory.get("/")
        request.user = AnonymousUser()

        response = HttpResponse()
        set_efb_token_cookie(request, response)

        assert EFB_COOKIE_NAME not in response.cookies

    def test_noop_for_non_staff_user(self, user):
        user.is_staff = False
        user.save()

        request = self.factory.get("/")
        request.user = user

        response = HttpResponse()
        set_efb_token_cookie(request, response)

        assert EFB_COOKIE_NAME not in response.cookies

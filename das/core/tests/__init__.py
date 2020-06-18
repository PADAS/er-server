import datetime
import uuid

import pytest
import django.contrib.auth
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from oauth2_provider.models import Application, AccessToken
from kombu import Connection

pytestmark = pytest.mark.django_db

User = django.contrib.auth.get_user_model()

API_BASE = '/api/v1.0'

def fake_get_pool():
    return Connection("memory://").Pool(20)


class BaseAPITest(TestCase):
    api_base = API_BASE

    def setUp(self):
        user_const = dict(last_name='last', first_name='first')

        self.app_user = User.objects.create_user('app-user', 'app-user@test.com',
                                                 'app-user', is_superuser=False,
                                                 is_staff=True, **user_const)

        self.application = Application(
            name="Test Application",
            redirect_uris="http://localhost",
            user=self.app_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )
        self.application.save()

        self.factory = APIRequestFactory(enforce_csrf_checks=True)

    def create_access_token(self, user):
        tok = AccessToken.objects.create(
            user=user, token=str(uuid.uuid4()),
            application=self.application, scope='read write',
            expires=timezone.now() + datetime.timedelta(days=1)
        )
        return tok

    def force_authenticate(self, request, user):
        request.user = user
        tok = self.create_access_token(user)

        force_authenticate(request, user=user, token=tok)

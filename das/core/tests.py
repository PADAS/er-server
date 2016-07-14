import datetime

import django.contrib.auth
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from oauth2_provider.models import Application, AccessToken


User = django.contrib.auth.get_user_model()


class BaseAPITest(TestCase):
    def setUp(self):
        user_const = dict(last_name='last', first_name='first')
        self.api_base = '/api/v1.0'
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


    def force_authenticate(self, request, user):
        request.user = user
        tok = AccessToken.objects.create(
            user=request.user, token='1234567890',
            application=self.application, scope='read write',
            expires=timezone.now() + datetime.timedelta(days=1)
        )

        force_authenticate(request, user=request.user, token=tok)

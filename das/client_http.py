import uuid
import datetime

import django.contrib.auth
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from oauth2_provider.models import Application, AccessToken

User = django.contrib.auth.get_user_model()
API_BASE = "/api/v1.0"


class HTTPClient:
    def __init__(self):
        self.api_base = API_BASE
        self.app_user = User.objects.create_user(
            "app-user",
            "app-user@test.com",
            "app-user",
            is_superuser=False,
            is_staff=True,
            **dict(last_name="last", first_name="first")
        )
        self.application = Application.objects.create(
            name="Test Application",
            redirect_uris="http://localhost",
            user=self.app_user,
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        )
        self.factory = APIRequestFactory(enforce_csrf_checks=True)

    def create_access_token(self, user):
        return AccessToken.objects.create(
            user=user,
            token=str(uuid.uuid4()),
            application=self.application,
            scope="read write",
            expires=timezone.now() + datetime.timedelta(days=1),
        )

    def force_authenticate(self, request, user):
        request.user = user
        token = self.create_access_token(user)
        force_authenticate(request, user=user, token=token)

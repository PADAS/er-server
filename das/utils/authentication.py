"""
Code found here:
Allow a superuser to browse the DRF api.
"""

import json
import logging
from datetime import timedelta

from oauth2_provider.models import get_access_token_model
from oauthlib.common import generate_token

from django.conf import settings
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from rest_framework.authentication import SessionAuthentication

from core.models.oauth import DASAccessToken, DASApplication

logger = logging.getLogger("django.request")

AccessToken = get_access_token_model()


EFB_APPLICATION_ID = "EFB_APPLICATION_ID"


class SuperUserSessionAuthentication(SessionAuthentication):
    """
    Use Django's session framework for authentication of super users.
    """

    def authenticate(self, request):
        """
        Returns a `User` if the request session currently has a logged in user.
        Otherwise returns `None`.
        """

        # Get the underlying HttpRequest object
        request = request._request
        user = getattr(request, "user", None)

        # Unauthenticated, CSRF validation not required
        if not user or not user.is_active:  # or not user.is_superuser:
            return None

        # self.enforce_csrf(request)

        # CSRF passed with authenticated user
        return (user, None)


class BearerTokenInUrlAuthentication(SessionAuthentication):
    def authenticate(self, request):
        token = getattr(request, "query_params", {"auth": None}).get("auth", None)
        if token:
            access_token = AccessToken.objects.get(token=token)
            return access_token.user, None
        return None


class SkylinePostAuthentication(SessionAuthentication):
    """
    One off for Skyline Enigma, so that they can json post
    a 'CustomerId' field that maps to a long lived token
    """

    def authenticate(self, request):
        if request.method == "POST":
            json_data = json.loads(request.body)
            token = json_data["CustomerId"]
            if token:
                access_token = AccessToken.objects.get(token=token)
                return access_token.user, None
            return None


class AdminEFBTokenAuthentication(MiddlewareMixin):
    def process_response(self, request, response):
        if (
            "/admin" in request.path
            and request.user.is_authenticated
            and request.user.is_staff
            and not response.has_header("Set-Cookie")
        ):
            # Check if the user has is logged in within scope of this request
            if "_auth_user_id" in request.session and request.session["_auth_user_id"] == str(request.user.pk):
                try:
                    efb_app, _ = DASApplication.objects.get_or_create(
                        client_id=EFB_APPLICATION_ID,
                        defaults={
                            "client_type": "Confidential",
                            "authorization_grant_type": "password",
                            "client_secret": "",
                            "name": "Event Form Builder Das App",
                            "skip_authorization": True,
                        },
                    )

                    oauth2_settings = getattr(settings, "OAUTH2_PROVIDER", {})
                    expire_in_secs = oauth2_settings.get("ACCESS_TOKEN_EXPIRE_SECONDS")
                    expires = timezone.now() + timedelta(seconds=expire_in_secs)

                    access_token = DASAccessToken.objects.create(
                        user=request.user,
                        token=generate_token(),
                        application=efb_app,
                        expires=expires,
                        scope="read write",
                        das_tenant=request.user.das_tenant,
                    )
                    logger.info(
                        "Middleware: Created access token for user %s at %s",
                        request.user.username,
                        EFB_APPLICATION_ID,
                    )

                    response.set_cookie("efb_access_token", access_token.token)

                except Exception as e:
                    logger.error(f"Middleware: Error creating token: {e}")
        return response

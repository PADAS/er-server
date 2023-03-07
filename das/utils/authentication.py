"""
Code found here:
Allow a superuser to browse the DRF api.
"""

import json
import logging

from oauth2_provider.models import get_access_token_model

from rest_framework.authentication import SessionAuthentication

logger = logging.getLogger("django.request")

AccessToken = get_access_token_model()


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

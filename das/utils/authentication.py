"""
Code found here:
Allow a superuser to browse the DRF api.
"""

import logging

from rest_framework.authentication import SessionAuthentication
from oauth2_provider.models import AccessToken


logger = logging.getLogger('django.request')


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
        user = getattr(request, 'user', None)

        # Unauthenticated, CSRF validation not required
        if not user or not user.is_active or not user.is_superuser:
            return None

        # self.enforce_csrf(request)

        # CSRF passed with authenticated user
        return (user, None)


class BearerTokenInUrlAuthentication(SessionAuthentication):
    def authenticate(self, request):
        token = getattr(request, 'query_params', {
                        'auth': None}).get('auth', None)
        if token:
            access_token = AccessToken.objects.get(token=token)
            return (access_token.user, None)
        return None

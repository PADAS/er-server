"""Auth0 authentication check endpoint using ResourceProtector pattern

Simple JWT validation endpoint using Django's authlib integration with ResourceProtector.
"""

from authlib.integrations.django_oauth2 import ResourceProtector

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from utils.auth0.auth0_validators import Auth0JWTBearerTokenValidator

require_auth = ResourceProtector()
require_auth.register_token_validator(Auth0JWTBearerTokenValidator())


@csrf_exempt
@require_auth(None)
def echo_auth0_token_subject(request):
    token = require_auth.acquire_token(request)

    return JsonResponse(
        {
            "message": "Hello from a private endpoint! You need to be authenticated to see this.",
            "user_sub": token.sub,
        }
    )

from __future__ import annotations

import logging

from authlib.oauth2 import ResourceProtector

from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from accounts.models import User
from utils.auth0.auth0_validators import Auth0JWTBearerTokenValidator

logger = logging.getLogger(__name__)

_resource_protector = ResourceProtector()
_resource_protector.register_token_validator(Auth0JWTBearerTokenValidator())


@method_decorator(cache_control(no_store=True), name="dispatch")
class AccountLinkingGateView(APIView):
    """Account-linking gate: report whether the Auth0 caller already maps to an ER user.

    Validates the inbound Auth0 JWT imperatively via the generic ``ResourceProtector``
    singleton (never emitting 401 — invalid tokens yield 400), then looks up the active
    ER user for the token's ``sub`` claim through the tenant-scoped ``User.objects``
    manager. The lookup is automatically isolated to the request's tenant by the
    host->tenant middleware that runs before this view.

    Responses:
      - 204 (no body): a matching active user exists; no linking needed.
      - 200 (text/plain): no matching active user; body is the absolute link URL.
      - 400 (no body): invalid/missing JWT, missing ``sub``, or multiple matches.

    This view overtly opts out of the project's DRF auth/permission defaults (see the
    class attributes below). It must, because ``DEFAULT_AUTHENTICATION_CLASSES`` is led by
    ``Auth0JWTAuthentication``, which raises 401 for a valid JWT whose ``sub`` has no
    matching active user — exactly the unlinked caller this gate must answer with 200 — and
    ``DEFAULT_PERMISSION_CLASSES`` is ``IsAuthenticated``. The JWT is still required: it is
    validated imperatively in ``get`` (an authenticator cannot express the 200/204/400
    matrix this endpoint needs).

    The ``@method_decorator(cache_control(no_store=True), name="dispatch")`` decorator wraps
    ``dispatch``, so ``Cache-Control: no-store`` is set on every response — the 204, the 200,
    the 400 paths, and DRF's auto-generated 405 for non-GET methods alike — and the result is
    never cached by any client. It deliberately wraps ``dispatch`` (not ``get``) so the 405
    also carries the header.
    """

    # Overtly opt out of the project's DRF defaults. DEFAULT_AUTHENTICATION_CLASSES leads with
    # Auth0JWTAuthentication, which raises 401 for a valid JWT whose sub has no matching active
    # user — exactly the unlinked caller this gate must answer with 200. DEFAULT_PERMISSION_CLASSES
    # is IsAuthenticated. Both must stay disabled or the unlinked on-ramp breaks. The JWT is still
    # required: it is validated imperatively below (an authenticator cannot express 200/204/400).
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request) -> HttpResponse:
        # Returns a Django HttpResponse, NOT a DRF Response, to preserve the deliberate response
        # shapes: empty-body 204/400 and a bare text/plain URL on 200. A DRF Response would route
        # the URL through the project's ExtendedJSONRenderer and emit a quoted JSON string instead.
        # DRF's finalize_response passes HttpResponseBase instances through unrendered, so this is
        # safe. The DRF `request` is passed straight to validate_request (as Auth0JWTAuthentication
        # does): parse_request_authorization reads request.headers.get("Authorization"), which the
        # DRF Request satisfies — do not reach for request._request.
        try:
            token = _resource_protector.validate_request(scopes=None, request=request)
        except Exception:
            logger.warning("user/linked: Auth0 JWT validation failed", exc_info=True)
            return HttpResponse(status=400)

        auth0_subject = token.get("sub")
        if not auth0_subject:
            logger.warning("user/linked: Auth0 JWT missing sub claim")
            return HttpResponse(status=400)

        try:
            User.objects.get(auth0_id=auth0_subject, is_active=True)  # tenant-scoped manager
        except User.DoesNotExist:
            return HttpResponse(
                request.build_absolute_uri(reverse("link_accounts")),
                content_type="text/plain",
                status=200,
            )
        except User.MultipleObjectsReturned:  # defensive parity; unreachable while tenant scoping holds
            logger.error("user/linked: multiple active users with auth0_id %s", auth0_subject)
            return HttpResponse(status=400)

        return HttpResponse(status=204)

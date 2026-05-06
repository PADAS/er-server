"""
Account Linker: binds an ER user account to an Auth0 identity via a dedicated
public Auth0 client that does NOT require Auth0 organization membership.

Two entry points converge on the same PKCE OAuth flow and callback:
1. Magic link (new users): signed token in URL identifies the user
2. Session (existing users): user_id in session before redirecting here
"""

import logging
import secrets

from auth0.management import Auth0 as Auth0Management
from authlib.integrations.django_client import OAuth

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from accounts.models import User
from utils.auth0.helpers import (
    get_auth0_custom_domain,
    get_auth0_management_api_access_token,
)
from utils.tenant import get_tenant_settings
from utils.tenant.decorators import require_enabled_idp_configs

logger = logging.getLogger(__name__)


class _LazyOAuthClient:
    """Defers OAuth client registration until first use so that settings
    and helpers (e.g. get_auth0_custom_domain) are not evaluated at
    module import time."""

    def __init__(self):
        self._client = None

    def _ensure_registered(self):
        if self._client is None:
            domain = get_auth0_custom_domain()
            self._client = OAuth()
            self._client.register(
                "auth0",
                client_id=settings.AUTH0_CLIENT_ID_FOR_ACCOUNT_LINKER,
                client_kwargs={
                    "scope": "openid profile email",
                    "code_challenge_method": "S256",
                },
                server_metadata_url=f"https://{domain}/.well-known/openid-configuration",
            )

    @property
    def auth0(self):
        self._ensure_registered()
        return self._client.auth0


_account_linker_auth0_client = _LazyOAuthClient()

ACCOUNT_LINKER_LANDING_URL_NAME = "account_linker_landing"
ACCOUNT_LINKER_CALLBACK_URL_NAME = "account_linker_callback"

MAGIC_LINK_SALT = "account-linker"
SESSION_KEY_PREFIX = "account_linker_attempt:"

_IDP_NOT_ENABLED_MESSAGE = "Account linking is not available for this site. Please contact support."
_INVALID_LINK_MESSAGE = "Invalid link. Please contact your site administrator."
_UNABLE_TO_LINK_MESSAGE = "Unable to associate your accounts. Please contact support."


def create_magic_link_token(user_id):
    """Create a signed, timestamped token encoding a user ID for magic links."""
    return signing.dumps({"user_id": str(user_id)}, salt=MAGIC_LINK_SALT)


def resolve_user_from_magic_link_token(token):
    """Resolve a User from a magic link token."""

    max_age = settings.ACCOUNT_LINKER_MAGIC_LINK_MAX_AGE_SECONDS
    payload = signing.loads(token, salt=MAGIC_LINK_SALT, max_age=max_age)
    return User.objects.get(id=payload["user_id"], is_active=True)


@require_enabled_idp_configs(message=_IDP_NOT_ENABLED_MESSAGE, status=400)
def account_linker_landing(request):
    """Landing page for the Account Linker which initiates the PKCE flow to Auth0.

    Two modes:
    1. ``?token=<signed_token>`` — magic link flow: verify token, resolve user
    2. ``?session_ref=<ref>`` — session flow: caller stored user_id in session
    """
    token = request.GET.get("token")

    if token:
        try:
            user = resolve_user_from_magic_link_token(token)
        except signing.SignatureExpired:
            return HttpResponse(
                "This link has expired. Please contact your site administrator for a new invitation.",
                status=400,
            )
        except Exception:
            logger.exception("Error resolving user from magic link token")
            return HttpResponse(_INVALID_LINK_MESSAGE, status=400)
    else:
        session_ref = request.GET.get("session_ref")
        user_id = request.session.pop(f"{SESSION_KEY_PREFIX}{session_ref}", None) if session_ref else None
        if not user_id:
            logger.warning("Account linker landing reached without token or valid session_ref")
            return HttpResponse(_INVALID_LINK_MESSAGE, status=400)
        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            logger.warning("Account linker session_ref contained unknown or inactive user_id=%s", user_id)
            return HttpResponse(_INVALID_LINK_MESSAGE, status=400)

    # Each linking attempt gets its own session key, passed as OAuth state
    # so concurrent flows in different tabs cannot collide.
    link_attempt = secrets.token_urlsafe(32)
    request.session[f"{SESSION_KEY_PREFIX}{link_attempt}"] = str(user.id)

    callback_url = request.build_absolute_uri(reverse(ACCOUNT_LINKER_CALLBACK_URL_NAME))
    return _account_linker_auth0_client.auth0.authorize_redirect(
        request,
        callback_url,
        state=link_attempt,
    )


@csrf_exempt
@require_enabled_idp_configs(message=_IDP_NOT_ENABLED_MESSAGE, status=400)
def account_linker_callback(request):
    """Handle the Auth0 callback: exchange the authorization code, link the
    user's Auth0 identity, and add them to the tenant's Auth0 organization."""

    error = request.GET.get("error")
    if error:
        error_description = request.GET.get("error_description", "")
        logger.warning("Auth0 returned error during account linking: %s - %s", error, error_description)
        return HttpResponse(
            _UNABLE_TO_LINK_MESSAGE,
            status=400,
        )

    link_attempt = request.GET.get("state")
    user_id = request.session.pop(f"{SESSION_KEY_PREFIX}{link_attempt}", None) if link_attempt else None
    if not user_id:
        logger.error("No valid link_attempt in session during account linker callback")
        return HttpResponse(
            _UNABLE_TO_LINK_MESSAGE,
            status=400,
        )

    try:
        token = _account_linker_auth0_client.auth0.authorize_access_token(request)
    except Exception:
        logger.exception("Error exchanging authorization code in account linker")
        return HttpResponse(
            _UNABLE_TO_LINK_MESSAGE,
            status=400,
        )

    try:
        userinfo = token.get("userinfo")
        if not userinfo:
            raise ValueError("No userinfo in token response")
        auth0_sub = userinfo["sub"]
    except (TypeError, KeyError, ValueError):
        logger.exception("Could not extract sub claim from Auth0 token")
        return HttpResponse(
            _UNABLE_TO_LINK_MESSAGE,
            status=400,
        )

    try:
        user = User.objects.get(id=user_id, is_active=True)
    except User.DoesNotExist:
        logger.error("User %s not found during account linker callback", user_id)
        return HttpResponse(
            _UNABLE_TO_LINK_MESSAGE,
            status=400,
        )

    if user.auth0_id:
        if user.auth0_id != auth0_sub:
            logger.warning(
                "Auth0 subject mismatch during account linker callback for user %s: "
                "persisted auth0_id=%s, authenticated sub=%s",
                user.username,
                user.auth0_id,
                auth0_sub,
            )
            return HttpResponse(
                _UNABLE_TO_LINK_MESSAGE,
                status=400,
            )
        logger.info("User %s already has auth0_id=%s, skipping linking", user.username, user.auth0_id)

    # When auth0_id is not yet set, save and org-add run atomically — if either
    # fails, both roll back. The unique constraint on auth0_id rejects duplicates
    # at save time, preventing a stolen sub from reaching the org-add call.
    # When already linked (matching sub), only the org-add runs (idempotent).
    try:
        with transaction.atomic():
            if not user.auth0_id:
                user.auth0_id = auth0_sub
                user.save(update_fields=["auth0_id"])
                logger.info("Linked user %s to Auth0 sub %s", user.username, auth0_sub)
            org_id = get_tenant_settings().feature_flags.idp_org_id
            _add_user_to_auth0_org(user.auth0_id, org_id)
            logger.info("Added user %s to Auth0 org %s", user.username, org_id)
    except IntegrityError:
        logger.warning(
            "Auth0 sub %s is already linked to another user; cannot link to user %s",
            auth0_sub,
            user.username,
        )
        return HttpResponse(_UNABLE_TO_LINK_MESSAGE, status=400)
    except Exception:
        logger.exception("Failed to link user %s to Auth0", user.username)
        return HttpResponse(_UNABLE_TO_LINK_MESSAGE, status=400)

    return redirect("/")


def _add_user_to_auth0_org(auth0_sub, org_id):
    """Add an Auth0 user to an Auth0 organization via the Management API."""
    token = get_auth0_management_api_access_token()
    domain = get_auth0_custom_domain()
    client = Auth0Management(domain, token)
    client.organizations.create_organization_members(org_id, {"members": [auth0_sub]})

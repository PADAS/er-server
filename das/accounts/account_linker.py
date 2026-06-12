"""
Account Linker: binds an ER user account to an Auth0 identity via a dedicated
public Auth0 client that does NOT require Auth0 organization membership.

Two entry points converge on the same PKCE OAuth flow and callback:
1. Magic link (new users): signed token in URL identifies the user
2. Session (existing users): user_id in session before redirecting here
"""

import logging
import secrets

from authlib.integrations.django_client import OAuth

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models.functions import Trim
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from accounts.models import User
from utils.auth0.helpers import get_auth0_custom_domain
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
_EMAIL_COLLISION_MESSAGE = (
    "This email address is already associated with another account on this site. Please contact support."
)


def _is_org_scoped_site() -> bool:
    """Return True if this tenant is org-scoped (has an idp_org_id configured).

    Org-scoped sites manage Auth0 organisation membership through other means;
    the account linker only operates on common-DB sites where idp_org_id is
    absent.
    """
    org_id = get_tenant_settings().feature_flags.idp_org_id
    return bool(org_id and org_id.strip())


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
    if _is_org_scoped_site():
        return HttpResponse(_IDP_NOT_ENABLED_MESSAGE, status=400)

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

    # Reject the link if the user is already bound to an Auth0 identity.
    # This makes magic links effectively single-use: once the Account Linker
    # flow completes and sets auth0_id, the same link cannot start another
    # PKCE round trip. The callback also checks auth0_id to guard against
    # races where linking completes between this check and the callback.
    if user.auth0_id:
        logger.warning(
            "Account linker landing for user %s who is already linked (auth0_id=%s)", user.username, user.auth0_id
        )
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
        connection=get_tenant_settings().slug_name,
        prompt="login",  # assure user can login; do not reuse any prior Auth0 UL session
    )


@csrf_exempt
@require_enabled_idp_configs(message=_IDP_NOT_ENABLED_MESSAGE, status=400)
def account_linker_callback(request):
    """Handle the Auth0 callback: exchange the authorization code and link the
    user's Auth0 identity."""

    if _is_org_scoped_site():
        return HttpResponse(_IDP_NOT_ENABLED_MESSAGE, status=400)

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

    userinfo = token.get("userinfo")
    if not userinfo:
        logger.error("No userinfo in Auth0 token response")
        return HttpResponse(
            _UNABLE_TO_LINK_MESSAGE,
            status=400,
        )

    auth0_sub = (userinfo.get("sub") or "").strip()
    auth0_email = (userinfo.get("email") or "").strip()

    if not auth0_sub:
        logger.warning("Auth0 token has missing or empty sub claim")
        return HttpResponse(
            _UNABLE_TO_LINK_MESSAGE,
            status=400,
        )

    if not auth0_email:
        logger.warning("Auth0 token missing email claim for sub %s", auth0_sub)
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

    colliding_user = (
        User.objects.annotate(trimmed_email=Trim("email"))
        .filter(trimmed_email__iexact=auth0_email)
        .exclude(id=user.id)
        .values("id", "username", "is_active")
        .first()
    )
    if colliding_user:
        logger.warning(
            "Email collision during account linking: user '%s' cannot use email '%s' "
            "because it belongs to user '%s' (id=%s, active=%s)",
            user.username,
            auth0_email,
            colliding_user["username"],
            colliding_user["id"],
            colliding_user["is_active"],
        )
        return HttpResponse(_EMAIL_COLLISION_MESSAGE, status=400)

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

    current_email = user.email
    should_notify = (
        bool(current_email and current_email.strip()) and current_email.strip().lower() != auth0_email.strip().lower()
    )

    # The unique constraint on auth0_id rejects duplicates at save time,
    # preventing a stolen sub from being persisted.
    try:
        with transaction.atomic():
            if not user.auth0_id:
                user.auth0_id = auth0_sub
                logger.info("Linked user %s to Auth0 sub %s", user.username, auth0_sub)
            if user.email != auth0_email:
                user.email = auth0_email
                logger.info("Updated email for user %s to %s", user.username, auth0_email)
            user.save(update_fields=["auth0_id", "email"])

            if should_notify:
                transaction.on_commit(lambda: _send_email_changed_notification(current_email))
    except (IntegrityError, ValidationError):
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


def _send_email_changed_notification(prior_email: str) -> None:
    """Send a notification to the prior email address about the change.

    Failures are logged but swallowed — the link has already been committed
    and a send error must not turn a successful link into a 500.
    """
    try:
        site_name = get_tenant_settings().domain
        recipient = prior_email.strip()
        context = {"site_name": site_name}
        subject = render_to_string("registration/account_linker_email_changed_subject.txt", context).strip()
        body = render_to_string("registration/account_linker_email_changed_email.html", context)
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
    except Exception:
        logger.exception("Failed to send email-changed notification to %s", prior_email)

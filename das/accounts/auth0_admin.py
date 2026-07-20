"""
Auth0 integration for Django Admin authentication with feature flag control.

This module provides conditional Auth0 authentication for Django Admin based on the
tenant's require_idp feature flag. When require_idp=True, admin authentication is
delegated to Auth0. When require_idp=False, Django's built-in admin authentication
is used.
"""

import logging
import urllib.parse

# https://github.com/python/typeshed/issues/15145
# noinspection PyUnresolvedReferences
from authlib.integrations.django_client import OAuth

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import BACKEND_SESSION_KEY, login
from django.contrib.auth import logout as django_logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from accounts.backends import Auth0BackendForStaffUsers
from accounts.mfa import ACR_CLAIM, MFA_TIME_CLAIM, OIDC_PAPE_MFA_URI, mfa_time_is_fresh
from accounts.models import User
from utils.efb_token import set_efb_token_cookie
from utils.tenant import get_tenant_settings


def _get_backend_path(backend_class):
    return f"{backend_class.__module__}.{backend_class.__qualname__}"


AUTH0_BACKEND_PATH = _get_backend_path(Auth0BackendForStaffUsers)

logger = logging.getLogger(__name__)

_admin_auth0_client = OAuth()
_admin_auth0_client.register(
    "auth0",
    client_id=settings.AUTH0_CLIENT_ID_FOR_DJANGO_ADMIN,
    client_secret=settings.AUTH0_CLIENT_SECRET_FOR_DJANGO_ADMIN,
    client_kwargs={
        "scope": "openid profile email",
    },
    server_metadata_url=f"https://{settings.AUTH0_CUSTOM_DOMAIN}/.well-known/openid-configuration",
)

DEFAULT_ADMIN_NEXT = "/admin/"


def _get_safe_next_url(request, default=None):
    if default is None:
        default = DEFAULT_ADMIN_NEXT
    next_param = request.GET.get("next", default)
    if url_has_allowed_host_and_scheme(next_param, allowed_hosts={request.get_host()}):
        return next_param
    return default


def admin_login_entrypoint(request):
    """
    Conditional admin login entrypoint that checks the tenant's require_idp flag.

    If require_idp=True and the user is already authenticated, creates the token cookie and redirects
    to the intended destination without a redundant Auth0 round-trip.

    If require_idp=True and the user is not authenticated, redirects to Auth0 login. When the ER site
    has an idp_org_id (org-based connection), the organization is passed through to the initiator;
    otherwise the org_id is omitted.
    If require_idp=False, uses Django's default admin login.

    This function replaces the default admin login URL handler.
    """
    try:
        tenant_settings = get_tenant_settings()
        require_idp = tenant_settings.feature_flags.require_idp
        org_id = tenant_settings.feature_flags.idp_org_id
    except Exception as e:
        logger.error("Failed to get tenant settings in admin login: %s", e)
        return _use_default_django_admin_login(request)

    user = getattr(request, "user", None)
    next_param = _get_safe_next_url(request)

    if require_idp:
        session = getattr(request, "session", {})
        authenticated_via_auth0 = (
            user and user.is_authenticated and user.is_staff and session.get(BACKEND_SESSION_KEY) == AUTH0_BACKEND_PATH
        )
        if not authenticated_via_auth0:
            logger.debug("Redirecting to Auth0 admin login for tenant with require_idp=True")
            query_params = {"next": next_param}
            if org_id:
                query_params["org_id"] = org_id
            query = urllib.parse.urlencode(query_params)
            return redirect(f"{reverse(INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME)}?{query}")
    elif not (user and user.is_authenticated and user.is_staff):
        return _use_default_django_admin_login(request)

    response = redirect(next_param)
    set_efb_token_cookie(request, response)
    return response


def admin_logout(request):
    """
    Conditional admin logout that checks the tenant's require_idp flag.

    If require_idp=True, redirects to our Auth0 logout endpoint with a return to URL of the admin index page.
    If require_idp=False, uses Django's default admin logout.

    This function replaces the default admin logout URL handler.
    """

    django_logout(request)

    try:
        tenant_settings = get_tenant_settings()
        require_idp = tenant_settings.feature_flags.require_idp

        if require_idp:
            return_to_url = request.build_absolute_uri(reverse("admin:index"))
            # Construct the Auth0 logout URL
            auth0_logout_url = (
                f"https://{settings.AUTH0_CUSTOM_DOMAIN}/v2/logout?"
                f"client_id={settings.AUTH0_CLIENT_ID_FOR_DJANGO_ADMIN}&"
                f"returnTo={urllib.parse.quote_plus(return_to_url)}"
            )
            return redirect(auth0_logout_url)

    except Exception as e:
        logger.error("Failed to get tenant settings in admin logout: %s", e)

    return redirect(reverse("admin:index"))


def _use_default_django_admin_login(request):
    logger.debug("Using Django default admin login")
    return admin.site.login(request)


def admin_access_denied_response(username: str | None = None) -> HttpResponse:
    """Render the admin access-denied page (HTTP 403).

    Shown when an authenticated Auth0 user is rejected for admin access (non-staff, or an
    ambiguous multi-user match). The page offers a sign-out link routed through admin_logout
    (-> Auth0 /v2/logout) so the user can sign out and sign back in with a different account.
    When a single user was resolved, their username is surfaced so they can see which account
    they are signed in as.

    Rendered without a request to skip context processors, mirroring already_linked_response.
    """
    html = render_to_string("registration/admin_access_denied.html", {"username": username})
    return HttpResponse(html, status=403)


# Exported so middleware and URL registration share the same string - keeping
# them from drifting out of sync if this view's URL name ever changes.
INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME = "auth0_admin_login"


@never_cache
def initiate_auth0_admin_login(request):
    """
    Initiates Auth0 login for Django Admin.
    Stores the 'next' parameter in session for retrieval after OAuth callback.

    For org-based connections (org_id present) the organization is passed through to Auth0.
    Common-DB tenants (no org_id) omit the parameter entirely so Auth0 uses the tenant's
    Default Directory.

    On a require_mfa site the authorization request carries acr_values (the OIDC PAPE
    multi-factor URI) so Auth0 issues an MFA challenge. No max_age is sent: admin MFA
    freshness is enforced from the mirrored mfa_time claim, not primary-auth auth_time.
    """
    next_param = _get_safe_next_url(request)
    request.session["auth0_admin_next"] = next_param

    org_id = request.GET.get("org_id")

    try:
        require_mfa = get_tenant_settings().feature_flags.require_mfa
    except Exception as e:
        logger.error("Failed to get tenant settings in Auth0 admin login initiator: %s", e)
        require_mfa = False

    auth0_callback_url = request.build_absolute_uri(reverse("auth0_callback"))

    # Force a fresh Auth0 prompt so a retry cannot silently reuse an existing SSO session and
    # re-assert the same (possibly non-admin) identity, which would trap the user in a login loop.
    extra_params = {"prompt": "login"}
    if org_id:
        extra_params["organization"] = org_id
        logger.debug("Initiating Auth0 admin login with organization %s", org_id)
    if require_mfa:
        extra_params["acr_values"] = OIDC_PAPE_MFA_URI

    return _admin_auth0_client.auth0.authorize_redirect(request, auth0_callback_url, **extra_params)


@never_cache
@csrf_exempt
def auth0_callback(request: HttpRequest) -> HttpResponse:
    """
    Handles Auth0 OAuth callback for Django Admin authentication.

    This function processes the OAuth callback from Auth0, exchanges the authorization
    code for an access token, resolves the staff user via a tenant-scoped lookup on the
    Auth0 subject claim, and redirects to the originally intended admin destination.

    Flow:
        1. Exchange authorization code for OAuth2 access token (wrapped in try/except -> 500)
        2. Extract the Auth0 subject (sub) claim from userinfo
        3. Resolve an active user by auth0_id via the tenant-scoped User manager
        4. Verify the user is staff, log them in, and redirect to the intended admin page

    The lookup is a tenant-scoped User.objects.get(auth0_id=<sub>, is_active=True) followed by
    an is_staff check, classifying each failure mode into a distinct outcome:

        - DoesNotExist (no active user for the sub, incl. an inactive linked user) -> 302 to
          the account-linking on-ramp.
        - MultipleObjectsReturned -> 403 access-denied page (defensive; the per-tenant auth0_id
          constraint makes this unreachable while the DB is healthy).
        - active user found but is_staff=False -> 403 access-denied page (already linked; must not
          be sent to the link page, which rejects already-linked users).

    Returns:
        - HttpResponse (redirect 302): On successful authentication, redirects to intended admin page
        - HttpResponse (redirect 302): On DoesNotExist, redirects to the account-linking page
        - HttpResponse (400): If the Auth0 userinfo is missing the sub claim
        - HttpResponse (403): The rendered access-denied page, if the resolved user lacks admin
          privileges or multiple users match
        - HttpResponse (403): "Multi-factor authentication required", when the site requires MFA
          and the ID token lacks a fresh mirrored MFA claim (acr / mfa_time)
        - HttpResponse (500): If an error occurs during the OAuth token exchange

    Session variables:
        - auth0_admin_next: Contains the originally intended admin destination URL
        - admin_mfa_time: On require_mfa sites, the MFA-completion time from the ID token, stored
          for the admin recency middleware to re-check per request
    """
    try:
        token = _admin_auth0_client.auth0.authorize_access_token(request)
    except Exception as e:
        logger.exception("Error in Auth0 callback: %s", e)
        return HttpResponse("Authentication error", status=500)

    userinfo = token.get("userinfo") or {}
    auth0_id = userinfo.get("sub")
    if not auth0_id:
        logger.warning("Auth0 admin callback: userinfo missing sub claim")
        return HttpResponse("Authentication error", status=400)

    try:
        # Tenant-scoped lookup (auto-isolated by middleware).
        admin_user = User.objects.get(auth0_id=auth0_id, is_active=True)
    except User.DoesNotExist:
        # True no-match for this tenant, which by design includes an inactive linked user
        # (is_active=True filters them out). Send them to the in-product linking on-ramp.
        # This redirect is intentional - do NOT "fix" it to a 403.
        logger.info("Auth0 admin callback: no active user for auth0_id; redirecting to link-accounts")
        return redirect(reverse("link_accounts"))
    except User.MultipleObjectsReturned:
        logger.error("Auth0 admin callback: multiple active users with auth0_id %s", auth0_id)
        return admin_access_denied_response()

    if not admin_user.is_staff:
        logger.error("Non-staff user %s attempted Auth0 admin authentication", admin_user.username)
        return admin_access_denied_response(username=admin_user.username)

    require_mfa = False
    mfa_max_age_seconds = 31_536_000  # 365 days
    try:
        feature_flags = get_tenant_settings().feature_flags
        require_mfa = feature_flags.require_mfa
        if feature_flags.mfa_max_age_seconds is not None:
            mfa_max_age_seconds = feature_flags.mfa_max_age_seconds
    except Exception as e:
        logger.error("Failed to get tenant settings in Auth0 admin callback: %s", e)

    # Gate on require_mfa alone: require_idp is already implied here (this callback is only
    # reachable via the Auth0 OIDC flow). The admin recency middleware additionally checks
    # require_idp because it also guards requests that were never OIDC-seeded.
    mfa_time = userinfo.get(MFA_TIME_CLAIM)
    if require_mfa and not (
        userinfo.get(ACR_CLAIM) == OIDC_PAPE_MFA_URI and mfa_time_is_fresh(mfa_time, mfa_max_age_seconds)
    ):
        logger.warning(
            "Auth0 admin callback: MFA required but token lacks a fresh MFA claim for %s",
            admin_user.username,
        )
        return HttpResponse("Multi-factor authentication required", status=403)

    login(request, admin_user, backend=AUTH0_BACKEND_PATH)
    if require_mfa:
        # Read by the admin recency middleware to re-check MFA freshness on each admin request.
        request.session["admin_mfa_time"] = mfa_time
    logger.info(
        "Successfully authenticated user %s via Auth0 for admin access",
        admin_user.username,
    )
    next_url = request.session.pop("auth0_admin_next", DEFAULT_ADMIN_NEXT)
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = DEFAULT_ADMIN_NEXT
    response = redirect(next_url)
    set_efb_token_cookie(request, response)
    return response

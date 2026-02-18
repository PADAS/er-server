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
from django.contrib.auth import login
from django.contrib.auth import logout as django_logout
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt

from accounts.backends import Auth0BackendForStaffUsers
from utils.efb_token import set_efb_token_cookie
from utils.tenant import get_tenant_settings

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

_auth0_admin_backend = Auth0BackendForStaffUsers()

DEFAULT_ADMIN_NEXT = "/admin/"


def _get_safe_next_url(request, default=None):
    if default is None:
        default = DEFAULT_ADMIN_NEXT
    next_param = request.GET.get("next", default)
    if url_has_allowed_host_and_scheme(next_param, allowed_hosts=request.get_host()):
        return next_param
    return default


def admin_login_entrypoint(request):
    """
    Conditional admin login entrypoint that checks the tenant's require_idp flag.

    If require_idp=True and the user is already authenticated, creates the token cookie and redirects
    to the intended destination without a redundant Auth0 round-trip.

    If require_idp=True and the user is not authenticated, redirects to Auth0 login.
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

    if require_idp and org_id:
        next_param = _get_safe_next_url(request)

        if request.user.is_authenticated and request.user.is_staff:
            response = redirect(next_param)
            set_efb_token_cookie(request, response)
            return response

        logger.debug("Redirecting to Auth0 admin login for tenant with require_idp=True")
        query = urllib.parse.urlencode({"next": next_param, "org_id": org_id})
        return redirect(f"{reverse('auth0_admin_login')}?{query}")
    else:
        return _use_default_django_admin_login(request)


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


def initiate_auth0_admin_login(request):
    """
    Initiates Auth0 login for Django Admin.
    Stores the 'next' parameter in session for retrieval after OAuth callback.
    """
    next_param = _get_safe_next_url(request)
    request.session["auth0_admin_next"] = next_param

    org_id = request.GET.get("org_id")

    auth0_callback_url = request.build_absolute_uri(reverse("auth0_callback"))

    logger.debug("Using organization ID for Auth0 admin login: %s", org_id)
    return _admin_auth0_client.auth0.authorize_redirect(request, auth0_callback_url, organization=org_id)


@csrf_exempt
def auth0_callback(request):
    """
    Handles Auth0 OAuth callback for Django Admin authentication.

    This function processes the OAuth callback from Auth0, exchanges the authorization
    code for an access token, authenticates the user via the Auth0BackendForStaffUsers
    backend, and redirects to the originally intended admin destination.

    Flow:
        1. Exchange authorization code for OAuth2 access token
        2. Authenticate user using Auth0BackendForStaffUsers backend
        3. Log the user into Django session
        4. Retrieve intended destination from session
        5. Redirect to the intended admin page

    Returns:
        - HttpResponse (redirect): On successful authentication, redirects to intended admin page
        - HttpResponse (403): If user authentication fails or user lacks admin privileges
        - HttpResponse (500): If an error occurs during the OAuth callback process

    Session variables:
        - auth0_admin_next: Contains the originally intended admin destination URL
    """
    try:
        token = _admin_auth0_client.auth0.authorize_access_token(request)
        admin_user = _auth0_admin_backend.authenticate(request, token=token)
        if admin_user:
            login(request, admin_user, backend="accounts.backends.Auth0BackendForStaffUsers")
            logger.info(
                "Successfully authenticated user %s via Auth0 for admin access",
                admin_user.username,
            )
            next_url = request.session.pop("auth0_admin_next", DEFAULT_ADMIN_NEXT)
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts=request.get_host()):
                next_url = DEFAULT_ADMIN_NEXT
            return redirect(next_url)
        else:
            logger.error("Auth0 authentication failed or user lacks admin privileges")
            return HttpResponse("Authentication failed - insufficient privileges", status=403)

    except Exception as e:
        logger.exception("Error in Auth0 callback: %s", e)
        return HttpResponse("Authentication error", status=500)

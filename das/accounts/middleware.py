"""Middleware enforcing MFA recency on the Django Admin surfaces."""

from __future__ import annotations

import logging
import urllib.parse
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from accounts.auth0_admin import INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME
from accounts.mfa import mfa_time_is_fresh
from utils.tenant import get_tenant_settings

logger = logging.getLogger(__name__)

_ADMIN_PREFIX = "/admin/"
_MFA_EXEMPT_PATHS = frozenset({"/admin/login/", "/admin/logout/"})
_DEFAULT_MFA_MAX_AGE_SECONDS = 31_536_000  # 365 days


class AdminMfaRecencyMiddleware:
    """Re-check MFA recency on every admin request for require_mfa sites.

    On /admin/* requests, when the tenant requires IdP + MFA, the admin_mfa_time stored
    by the Auth0 callback must be within mfa_max_age_seconds. When it
    is stale or absent, the request is redirected into a fresh Auth0 MFA challenge (not a
    403), so a Django admin session cannot outlive the MFA recency window. Login/logout
    endpoints are exempt so re-auth cannot loop and the user can always sign out.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if _is_guarded_admin_path(request.path) and _mfa_required_but_stale(request):
            return _redirect_to_reauth(request)
        return self.get_response(request)


def _is_guarded_admin_path(path: str) -> bool:
    return path.startswith(_ADMIN_PREFIX) and path not in _MFA_EXEMPT_PATHS


def _mfa_required_but_stale(request: HttpRequest) -> bool:
    try:
        flags = get_tenant_settings().feature_flags
    except Exception as e:
        # Fail open: if tenant settings can't be resolved, let the request through to the normal
        # flow rather than blocking all admin access on a transient lookup failure. This mirrors
        # the admin Auth0 login/callback, which also degrade gracefully when settings are absent.
        logger.error("Failed to get tenant settings in admin MFA recency middleware: %s", e)
        return False
    if not (flags.require_idp and flags.require_mfa):
        return False
    max_age_seconds = flags.mfa_max_age_seconds
    if max_age_seconds is None:
        max_age_seconds = _DEFAULT_MFA_MAX_AGE_SECONDS
    return not mfa_time_is_fresh(request.session.get("admin_mfa_time"), max_age_seconds)


def _redirect_to_reauth(request: HttpRequest) -> HttpResponse:
    login_url = reverse(INITIATE_AUTH0_ADMIN_LOGIN_URL_NAME)
    query = urllib.parse.urlencode({"next": request.get_full_path()})
    return redirect(f"{login_url}?{query}")

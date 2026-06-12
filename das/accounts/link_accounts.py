from __future__ import annotations

import logging
import secrets

from django import forms
from django.contrib.auth import authenticate
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from accounts.account_linker import ACCOUNT_LINKER_LANDING_URL_NAME, SESSION_KEY_PREFIX
from utils.tenant import get_tenant_settings
from utils.tenant.decorators import require_enabled_idp_configs

logger = logging.getLogger(__name__)

LINK_ACCOUNTS_URL_NAME = "link_accounts"

_IDP_NOT_ENABLED_MESSAGE = "Account linking is not available for this site. Please contact support."
_ALREADY_LINKED_MESSAGE = "This account is already linked to an identity provider. Please sign in using your IdP."
_INVALID_CREDENTIALS_MESSAGE = "Invalid username or password."


class LinkAccountsForm(forms.Form):
    username = forms.CharField(max_length=30, strip=True)
    password = forms.CharField(widget=forms.PasswordInput, strip=False)


def _is_org_scoped_site() -> bool:
    """Return True if this tenant is org-scoped (has an idp_org_id configured).

    Re-implemented here (rather than imported) because the linker
    treats it as a module-private helper. Keep this in sync if the
    linker changes its definition.
    """
    org_id = get_tenant_settings().feature_flags.idp_org_id
    return bool(org_id and org_id.strip())


@require_enabled_idp_configs(message=_IDP_NOT_ENABLED_MESSAGE, status=400)
def link_accounts(request: HttpRequest) -> HttpResponse:
    """Self-service page: legacy username+password -> Account Linker PKCE flow."""

    if _is_org_scoped_site():
        return HttpResponse(_IDP_NOT_ENABLED_MESSAGE, status=400)

    if request.method == "GET":
        return render(
            request,
            "registration/link_accounts.html",
            {"form": LinkAccountsForm()},
        )

    form = LinkAccountsForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "registration/link_accounts.html",
            {"form": form, "error": _INVALID_CREDENTIALS_MESSAGE},
            status=400,
        )

    user = authenticate(
        request,
        username=form.cleaned_data["username"],
        password=form.cleaned_data["password"],
    )

    # authenticate returns None on bad creds AND when the user is
    # inactive. We deliberately collapse both cases into one generic
    # message so we don't leak which usernames exist.
    if user is None:
        logger.info("link-accounts: failed credential check")
        return render(
            request,
            "registration/link_accounts.html",
            {"form": form, "error": _INVALID_CREDENTIALS_MESSAGE},
            status=400,
        )

    # is_nologin is enforced by NoLoginOAuth2Backend during OAuth, but
    # the model backend used here does not check it. Enforce explicitly.
    if getattr(user, "is_nologin", False):
        logger.info("link-accounts: rejected is_nologin user %s", user.username)
        return render(
            request,
            "registration/link_accounts.html",
            {"form": form, "error": _INVALID_CREDENTIALS_MESSAGE},
            status=400,
        )

    if user.auth0_id:
        logger.info(
            "link-accounts: rejected already-linked user %s (auth0_id=%s)",
            user.username,
            user.auth0_id,
        )
        return render(
            request,
            "registration/link_accounts.html",
            {"form": form, "error": _ALREADY_LINKED_MESSAGE},
            status=400,
        )

    session_ref = secrets.token_urlsafe(32)
    request.session[f"{SESSION_KEY_PREFIX}{session_ref}"] = str(user.id)

    target = reverse(ACCOUNT_LINKER_LANDING_URL_NAME) + f"?session_ref={session_ref}"
    return redirect(target)

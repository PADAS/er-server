"""Tests for the account-linking gate view (GET /api/v1.0/user/linked/)."""

from __future__ import annotations

from typing import Callable
from unittest.mock import Mock, patch

import pytest
from django_multitenant.utils import set_current_tenant

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from rest_framework.test import APIRequestFactory

from accounts.account_linking_gate import AccountLinkingGateView
from accounts.models import User


@pytest.fixture
def das_user_with_auth0_id_for_test(user: User) -> User:
    """Create a DAS user with auth0_id set in the active tenant."""
    user.auth0_id = "auth0|123456789"
    user.save()
    return user


@pytest.fixture
def mock_relevant_token_claims(das_user_with_auth0_id_for_test: User) -> Callable[..., dict[str, object]]:
    """Factory for creating JWT claims with configurable values."""

    def _create_claims(**overrides: object) -> dict[str, object]:
        default_claims: dict[str, object] = {
            "sub": das_user_with_auth0_id_for_test.auth0_id,
        }
        default_claims.update(overrides)
        return default_claims

    return _create_claims


@pytest.fixture(autouse=True)
def mock_tenant_settings() -> object:
    """Mock tenant settings with require_idp enabled, mirroring the auth backend suite."""
    with patch("accounts.backends.get_tenant_settings") as mock_settings:
        mock = Mock()
        mock.feature_flags.require_idp = True
        mock_settings.return_value = mock
        yield mock


def _get_request() -> HttpRequest:
    """Build a GET request carrying a Bearer token."""
    factory = APIRequestFactory()
    return factory.get("/api/v1.0/user/linked/", HTTP_AUTHORIZATION="Bearer some-token")


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAccountLinkingGate:
    """Behavior matrix for the account-linking gate."""

    def test_returns_204_when_active_linked_user_exists(
        self, das_user_with_auth0_id_for_test: User, mock_relevant_token_claims: Callable[..., dict[str, object]]
    ) -> None:
        request = _get_request()
        with patch(
            "accounts.account_linking_gate.ResourceProtector.validate_request",
            return_value=mock_relevant_token_claims(),
        ):
            response: HttpResponse = AccountLinkingGateView.as_view()(request)

        assert response.status_code == 204
        assert response["Cache-Control"] == "no-store"

    def test_returns_200_and_link_url_when_no_matching_user(self) -> None:
        request = _get_request()
        with patch(
            "accounts.account_linking_gate.ResourceProtector.validate_request",
            return_value={"sub": "auth0|nonexistent_user"},
        ):
            response: HttpResponse = AccountLinkingGateView.as_view()(request)

        expected_url = request.build_absolute_uri(reverse("link_accounts"))
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/plain")
        assert response.content.decode() == expected_url
        assert response["Cache-Control"] == "no-store"

    def test_returns_200_when_matching_user_is_inactive(
        self, das_user_with_auth0_id_for_test: User, mock_relevant_token_claims: Callable[..., dict[str, object]]
    ) -> None:
        # An inactive user holding this auth0_id deliberately collapses into the same 200
        # "go link" response (link URL in the body) as a brand-new caller — we do NOT
        # special-case it in the gate. The gate is only a hint; the real linker
        # (/auth/link-accounts/ -> account_linker) is the enforcement chokepoint that rejects
        # inactive/already-linked users, and its per-tenant auth0_id unique constraint blocks
        # re-binding. Keeping the response uniform (not 204, not a distinct status) also avoids
        # disclosing that a deactivated account exists for this Auth0 identity.
        das_user_with_auth0_id_for_test.is_active = False
        das_user_with_auth0_id_for_test.save()

        request = _get_request()
        with patch(
            "accounts.account_linking_gate.ResourceProtector.validate_request",
            return_value=mock_relevant_token_claims(),
        ):
            response: HttpResponse = AccountLinkingGateView.as_view()(request)

        expected_url = request.build_absolute_uri(reverse("link_accounts"))
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/plain")
        assert response.content.decode() == expected_url
        assert response["Cache-Control"] == "no-store"

    def test_returns_400_when_jwt_validation_raises(self) -> None:
        request = _get_request()
        with patch(
            "accounts.account_linking_gate.ResourceProtector.validate_request",
            side_effect=Exception("Invalid token"),
        ):
            response: HttpResponse = AccountLinkingGateView.as_view()(request)

        assert response.status_code == 400
        assert response["Cache-Control"] == "no-store"

    def test_returns_400_when_no_authorization_header(self) -> None:
        request = APIRequestFactory().get("/api/v1.0/user/linked/")
        with patch(
            "accounts.account_linking_gate.ResourceProtector.validate_request",
            side_effect=Exception("missing token"),
        ):
            response: HttpResponse = AccountLinkingGateView.as_view()(request)

        assert response.status_code == 400
        assert response["Cache-Control"] == "no-store"

    def test_returns_400_when_sub_claim_missing(self) -> None:
        request = _get_request()
        with patch(
            "accounts.account_linking_gate.ResourceProtector.validate_request",
            return_value={},
        ):
            response: HttpResponse = AccountLinkingGateView.as_view()(request)

        assert response.status_code == 400
        assert response["Cache-Control"] == "no-store"

    def test_returns_400_when_multiple_users_returned(
        self, mock_relevant_token_claims: Callable[..., dict[str, object]]
    ) -> None:
        request = _get_request()
        with patch(
            "accounts.account_linking_gate.ResourceProtector.validate_request",
            return_value=mock_relevant_token_claims(),
        ):
            with patch(
                "accounts.account_linking_gate.User.objects.get",
                side_effect=User.MultipleObjectsReturned,
            ):
                response: HttpResponse = AccountLinkingGateView.as_view()(request)

        assert response.status_code == 400
        assert response["Cache-Control"] == "no-store"

    def test_returns_405_on_post(self) -> None:
        request = APIRequestFactory().post("/api/v1.0/user/linked/", HTTP_AUTHORIZATION="Bearer some-token")
        # DRF dispatch returns a 405 Response (only ``get`` is defined). When the view is invoked
        # directly via ``as_view()`` this Response is left unrendered, so assert only on the status
        # and the no-store header set by the dispatch-level cache_control decorator — not ``.content``.
        response = AccountLinkingGateView.as_view()(request)

        assert response.status_code == 405
        assert response["Cache-Control"] == "no-store"

    def test_user_lookup_is_tenant_scoped(self, five_tenants: list[object], das_tenant: object) -> None:
        """A user with the same auth0_id in a different tenant must not satisfy the gate.

        The active tenant (das_tenant, via das_tenant_monkeypatch) has no matching user;
        only a foreign tenant does. Because User.objects is scoped to the active tenant,
        the gate must fall into the 200 (not-linked) branch.

        The foreign tenant is assigned explicitly via the ``das_tenant`` kwarg rather than
        ``set_current_tenant`` because ``das_tenant_monkeypatch`` replaces
        ``set_current_tenant`` with a no-op and pins the active tenant to ``das_tenant``.
        """
        auth0_subject = "auth0|cross-tenant"

        User.objects.create_user(
            username="other_tenant_user",
            email="other@example.com",
            password="password",
            auth0_id=auth0_subject,
            das_tenant=five_tenants[0],
        )

        # ``five_tenants`` resets the active tenant to None at setup, so re-pin to ``das_tenant``
        # to exercise the gate's tenant-scoped lookup — mirroring the idiom in test_permissionsets.py.
        set_current_tenant(das_tenant)

        request = _get_request()
        with patch(
            "accounts.account_linking_gate.ResourceProtector.validate_request",
            return_value={"sub": auth0_subject},
        ):
            response: HttpResponse = AccountLinkingGateView.as_view()(request)

        assert response.status_code == 200
        assert response.content.decode() == request.build_absolute_uri(reverse("link_accounts"))

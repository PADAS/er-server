"""Referrer-Policy for third-party map tiles (e.g. OpenStreetMap) that require a Referer."""

import pytest

from django.conf import settings
from django.test import Client


def test_secure_referrer_policy_configured() -> None:
    assert settings.SECURE_REFERRER_POLICY == "strict-origin-when-cross-origin"


@pytest.mark.django_db
def test_referrer_policy_header_on_admin_login_response() -> None:
    client = Client()
    response = client.get("/admin/login/")
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"

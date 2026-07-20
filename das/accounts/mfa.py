"""Shared MFA claim names and freshness logic.

The Auth0 MFA Claim Mirror stamps these namespaced claims on the token when a
multi-factor challenge completes; EarthRanger reads them to enforce MFA recency.
Kept in one place so the JWT backend, the Django Admin OIDC views, and the admin
recency middleware all agree on the claim names and the freshness rule.
"""

from __future__ import annotations

from typing import Final

from django.utils import timezone

OIDC_PAPE_MFA_URI: Final = "http://schemas.openid.net/pape/policies/2007/06/multi-factor"
ACR_CLAIM: Final = "https://pamdas.org/acr"
MFA_TIME_CLAIM: Final = "https://pamdas.org/mfa_time"
MFA_CLOCK_SKEW_SECONDS: Final = 60
DEFAULT_MFA_MAX_AGE_SECONDS: Final = 31_536_000  # 365 days


def mfa_time_is_fresh(mfa_time: object, max_age_seconds: int | None) -> bool:
    """Return True when an MFA-completion timestamp is recent enough.

    ``mfa_time`` is epoch seconds as stamped by the MFA Claim Mirror. It may arrive as
    an int or a numeric string, or be absent/malformed — anything that is not a valid
    epoch value is treated as not fresh. ``max_age_seconds`` of None falls back to
    ``DEFAULT_MFA_MAX_AGE_SECONDS``. ``MFA_CLOCK_SKEW_SECONDS`` is allowed on top of the
    window to absorb small client/server clock drift.
    """
    if max_age_seconds is None:
        max_age_seconds = DEFAULT_MFA_MAX_AGE_SECONDS
    if isinstance(mfa_time, bool) or not isinstance(mfa_time, (int, float, str)):
        return False
    try:
        age_seconds = int(timezone.now().timestamp()) - int(mfa_time)
    except ValueError:
        return False
    return age_seconds <= max_age_seconds + MFA_CLOCK_SKEW_SECONDS

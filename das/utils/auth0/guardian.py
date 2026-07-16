from __future__ import annotations

from typing import Callable

from auth0.management import ManagementClient

from utils.auth0.helpers import create_auth0_management_client


def send_guardian_otp_enrollment_ticket(
    auth0_user_id: str,
    *,
    client_factory: Callable[[], ManagementClient] = create_auth0_management_client,
) -> None:
    """Mint an OTP MFA enrollment ticket for an Auth0 user and have Auth0 email
    the enrollment link to the user's default address.

    ``send_mail=True`` delegates delivery to Auth0; the returned ticket is not
    needed by the caller.
    """
    client = client_factory()
    client.guardian.enrollments.create_ticket(
        user_id=auth0_user_id,
        factor="otp",
        send_mail=True,
    )

from __future__ import annotations

from unittest.mock import Mock, create_autospec

from auth0.management import ManagementClient
from auth0.management.guardian.enrollments.client import EnrollmentsClient

from utils.auth0.guardian import send_guardian_otp_enrollment_ticket


class TestSendGuardianOtpEnrollmentTicket:
    def test_creates_otp_enrollment_ticket_with_send_mail(self):
        mock_enrollments = create_autospec(EnrollmentsClient, instance=True)
        mock_client = Mock(spec=ManagementClient)
        mock_client.guardian.enrollments = mock_enrollments

        send_guardian_otp_enrollment_ticket("auth0|abc123", client_factory=lambda: mock_client)

        mock_enrollments.create_ticket.assert_called_once_with(
            user_id="auth0|abc123",
            factor="otp",
            send_mail=True,
        )

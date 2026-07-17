import logging
from unittest import mock

import pytest
from socketio import server

from rest_framework.exceptions import AuthenticationFailed

from rt_api import views
from rt_api.views import RT_NAMESPACE, create_realtime_handler


@pytest.fixture
def sios():
    return server.Server()


@pytest.fixture
def on_authenticate(sios):
    create_realtime_handler(sios)
    return sios.handlers[RT_NAMESPACE]["authorization"]


class _FailingAuthRequest:
    """Stand-in for the DRF request whose ``.user`` access triggers a failed
    authentication, mimicking an expired/invalid Bearer token."""

    @property
    def user(self):
        raise AuthenticationFailed("Token is invalid or expired")


_STEP_UP_CHALLENGE = (
    'Bearer error="insufficient_user_authentication", '
    'acr_values="http://schemas.openid.net/pape/policies/2007/06/multi-factor", '
    'max_age="31536000"'
)


class _StepUpRequest:
    """Stand-in for the DRF request whose ``.user`` access records an RFC 9470
    step-up challenge (exactly as the Auth0 MFA gate does) and then raises,
    mimicking a token that lacks valid/fresh MFA on a require_mfa site."""

    @property
    def user(self):
        self._auth0_step_up_challenge = _STEP_UP_CHALLENGE
        raise AuthenticationFailed("Multi-factor authentication required")


class TestOnAuthenticateSignalsMfaStepUp:
    """When the MFA gate records a step-up challenge on the request, the socket
    handler must surface it so the client can tell a step-up 401 apart from an
    ordinary invalid-credentials 401. A missing-MFA and a stale-MFA token both
    reach this path carrying the same challenge; that distinction is made and
    tested in the auth gate, not here."""

    DATA = {"type": "authorization", "authorization": "Bearer no-mfa-token", "id": "req-2"}

    def _invoke(self, on_authenticate):
        client_data = mock.MagicMock()
        client_data.domain = "test.example.com"
        with (
            mock.patch.object(views, "client") as client_mock,
            mock.patch.object(views, "TenantContextManager"),
            mock.patch.object(views, "DummyRequest"),
            mock.patch.object(views, "wrap_dummy_request_with_drf_request", return_value=_StepUpRequest()),
        ):
            client_mock.get_client.return_value = client_data
            on_authenticate("sid-456", self.DATA)

    def test_emits_step_up_challenge_as_www_authenticate(self, on_authenticate, sios):
        with mock.patch.object(sios, "emit") as emit_mock:
            self._invoke(on_authenticate)

        emit_mock.assert_called_once()
        payload = emit_mock.call_args.args[1]
        assert payload["status"]["code"] == 401
        # Additive contract: the step-up field is added without changing code/message.
        assert payload["status"]["message"] == "Invalid credentials"
        assert "www_authenticate" in payload["status"]
        assert payload["status"]["www_authenticate"] == _STEP_UP_CHALLENGE

    def test_does_not_admit_client_to_rooms(self, on_authenticate, sios):
        # Signalling only: a step-up rejection must still be a rejection — the client
        # is never entered into any rt_api room. MFA stays enforced over the socket.
        with (
            mock.patch.object(sios, "emit"),
            mock.patch.object(sios.manager, "enter_room") as enter_room_mock,
        ):
            self._invoke(on_authenticate)

        enter_room_mock.assert_not_called()


class TestOnAuthenticateRejectsInvalidToken:
    DATA = {"type": "authorization", "authorization": "Bearer expired-token", "id": "req-1"}

    def _invoke(self, on_authenticate):
        client_data = mock.MagicMock()
        client_data.domain = "test.example.com"
        with (
            mock.patch.object(views, "client") as client_mock,
            mock.patch.object(views, "TenantContextManager"),
            mock.patch.object(views, "DummyRequest"),
            mock.patch.object(views, "wrap_dummy_request_with_drf_request", return_value=_FailingAuthRequest()),
        ):
            client_mock.get_client.return_value = client_data
            on_authenticate("sid-123", self.DATA)

    def test_emits_401_invalid_credentials(self, on_authenticate, sios):
        with mock.patch.object(sios, "emit") as emit_mock:
            self._invoke(on_authenticate)

        emit_mock.assert_called_once()
        payload = emit_mock.call_args.args[1]
        assert payload["status"]["code"] == 401
        assert payload["status"]["message"] == "Invalid credentials"

    def test_generic_401_carries_no_step_up_challenge(self, on_authenticate, sios):
        # An ordinary invalid/expired-token 401 records no step-up challenge, so the
        # www_authenticate field is added only for genuine step-up rejections.
        with mock.patch.object(sios, "emit") as emit_mock:
            self._invoke(on_authenticate)

        payload = emit_mock.call_args.args[1]
        assert "www_authenticate" not in payload["status"]

    def test_does_not_log_traceback_at_error_level(self, on_authenticate, sios, caplog):
        with caplog.at_level(logging.INFO, logger="rt_api"), mock.patch.object(sios, "emit"):
            self._invoke(on_authenticate)

        # The expected-condition message is logged at INFO, not via logger.exception (ERROR + traceback).
        assert not any(record.levelno >= logging.ERROR and record.exc_info is not None for record in caplog.records)
        info_records = [r for r in caplog.records if r.levelno == logging.INFO and "Socket auth rejected" in r.message]
        assert len(info_records) == 1
        assert info_records[0].exc_info is None

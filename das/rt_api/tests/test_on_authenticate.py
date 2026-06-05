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

    def test_does_not_log_traceback_at_error_level(self, on_authenticate, sios, caplog):
        with caplog.at_level(logging.INFO, logger="rt_api"), mock.patch.object(sios, "emit"):
            self._invoke(on_authenticate)

        # The expected-condition message is logged at INFO, not via logger.exception (ERROR + traceback).
        assert not any(record.levelno >= logging.ERROR and record.exc_info is not None for record in caplog.records)
        info_records = [r for r in caplog.records if r.levelno == logging.INFO and "Socket auth rejected" in r.message]
        assert len(info_records) == 1
        assert info_records[0].exc_info is None

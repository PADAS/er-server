"""Tests for audit logging in _act_as_user_in_request (accounts/backends.py)."""

from __future__ import annotations

import logging

import pytest

from django.test import RequestFactory
from rest_framework.exceptions import PermissionDenied

from accounts.backends import _act_as_user_in_request

LOGGER_NAME = "accounts.act_as"


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestActAsUserInRequestLogging:

    @staticmethod
    def _make_request(profile_header: str | None = None) -> object:
        factory = RequestFactory()
        kwargs: dict[str, str] = {}
        if profile_header is not None:
            kwargs["HTTP_USER_PROFILE"] = profile_header
        return factory.get("/api/test/", **kwargs)

    def test_logs_info_on_successful_impersonation(self, user, create_user, caplog: pytest.LogCaptureFixture) -> None:
        """Successful act_as emits an INFO record with structured extra fields."""
        profile_user = create_user()
        user.act_as_profiles.add(profile_user)
        request = self._make_request(profile_header=str(profile_user.pk))

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            result = _act_as_user_in_request(user, request)

        assert result == profile_user

        info_records = [r for r in caplog.records if r.levelno == logging.INFO and "act_as:" in r.getMessage()]
        assert len(info_records) == 1
        record = info_records[0]
        assert record.act_as_user == str(profile_user.pk)
        assert record.authenticated_user == str(user.pk)
        assert record.reason == "success"

    def test_logs_warning_when_profile_not_in_act_as_profiles(
        self, user, create_user, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Unauthorized target emits a WARNING with reason='not_in_act_as_profiles'."""
        profile_user = create_user()
        request = self._make_request(profile_header=str(profile_user.pk))

        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            with pytest.raises(PermissionDenied):
                _act_as_user_in_request(user, request)

        warning_records = [
            r for r in caplog.records if r.levelno == logging.WARNING and "act_as denied" in r.getMessage()
        ]
        assert len(warning_records) == 1
        record = warning_records[0]
        assert record.act_as_user == str(profile_user.pk)
        assert record.authenticated_user == str(user.pk)
        assert record.reason == "not_in_act_as_profiles"

    @pytest.mark.parametrize(
        "is_staff, is_superuser",
        [
            pytest.param(True, False, id="staff"),
            pytest.param(False, True, id="superuser"),
            pytest.param(True, True, id="staff_and_superuser"),
        ],
    )
    def test_logs_warning_when_profile_is_privileged(
        self, is_staff: bool, is_superuser: bool, user, create_user, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Privileged target emits a WARNING with reason='privileged_target'."""
        profile_user = create_user(is_staff=is_staff, is_superuser=is_superuser)
        user.act_as_profiles.add(profile_user)
        request = self._make_request(profile_header=str(profile_user.pk))

        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            with pytest.raises(PermissionDenied):
                _act_as_user_in_request(user, request)

        warning_records = [
            r for r in caplog.records if r.levelno == logging.WARNING and "act_as denied" in r.getMessage()
        ]
        assert len(warning_records) == 1
        record = warning_records[0]
        assert record.act_as_user == str(profile_user.pk)
        assert record.authenticated_user == str(user.pk)
        assert record.reason == "privileged_target"

    def test_no_log_when_no_profile_header(self, user, caplog: pytest.LogCaptureFixture) -> None:
        """No HTTP_USER_PROFILE header means no impersonation log records."""
        request = self._make_request()

        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            result = _act_as_user_in_request(user, request)

        assert result is user
        act_as_records = [r for r in caplog.records if "act_as" in r.getMessage()]
        assert act_as_records == []

    def test_no_log_when_profile_is_self(self, user, caplog: pytest.LogCaptureFixture) -> None:
        """Profile == self emits only a DEBUG self-profile record, no INFO/WARNING."""
        request = self._make_request(profile_header=str(user.pk))

        with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
            result = _act_as_user_in_request(user, request)

        assert result is user
        info_or_warning = [r for r in caplog.records if r.levelno >= logging.INFO]
        assert info_or_warning == []

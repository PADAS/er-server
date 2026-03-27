"""Tests for MigrationLogger, EventTypeMigrationLogger, and LogContext."""

import re
from unittest.mock import MagicMock, patch

import pytest

from rest_framework.test import APIRequestFactory

from activity.schemas.migration.logger import ErrorCode, LogContext, MigrationLogger

# =============================================================================
# LogContext
# =============================================================================


class TestLogContext:
    def test_from_request_uses_explicit_header(self):
        request = APIRequestFactory().post(
            "/",
            {},
            format="json",
            HTTP_X_MIGRATION_REQUEST_ID="migration-batch-123",
            HTTP_HOST="tenant.test",
        )

        context = LogContext.from_request(request, dry_run=True)

        assert context.migration_request_id == "migration-batch-123"

    @patch("activity.schemas.migration.logger.get_tenant_settings")
    def test_from_request_uses_thread_tenant_settings(self, mock_get_tenant_settings):
        mock_get_tenant_settings.return_value = type("TenantStub", (), {"domain": "thread.test"})()
        request = APIRequestFactory().post("/", {}, format="json")

        context = LogContext.from_request(request, dry_run=True)

        assert context.tenant_name == "thread.test"
        assert re.match(r"^MR-thread-test-[0-9a-f]{8}$", context.migration_request_id)

    def test_build_migration_request_id_format(self):
        mid = LogContext.build_migration_request_id("my-tenant")
        assert re.match(r"^MR-my-tenant-[0-9a-f]{8}$", mid)

    def test_normalize_id_component_strips_special_chars(self):
        assert LogContext._normalize_id_component("My Tenant!@#") == "my-tenant"

    def test_normalize_id_component_empty_returns_default(self):
        assert LogContext._normalize_id_component("!!!") == "tenant"


# =============================================================================
# MigrationLogger
# =============================================================================


class TestMigrationLogger:
    @pytest.fixture
    def context(self):
        return LogContext(
            migration_request_id="MR-test-00000000",
            tenant_name="test-tenant",
            dry_run=True,
        )

    @pytest.fixture
    def sink(self):
        return MagicMock()

    @pytest.fixture
    def migration_logger(self, context, sink):
        return MigrationLogger(context=context, sink=sink)

    def test_error_returns_message(self, migration_logger):
        msg = migration_logger.error(ErrorCode.UNKNOWN, "something broke")
        assert msg == "something broke"

    def test_warning_returns_message(self, migration_logger):
        msg = migration_logger.warning(ErrorCode.UNKNOWN, "heads up")
        assert msg == "heads up"

    def test_error_emits_to_sink(self, migration_logger, sink):
        migration_logger.error(ErrorCode.EVENT_TYPE_NOT_FOUND, "not found")

        sink.log.assert_called_once()
        args, kwargs = sink.log.call_args
        assert "not found" in args[1]
        assert kwargs["extra"]["error_code"] == "event_type_not_found"
        assert kwargs["extra"]["tenant_name"] == "test-tenant"

    def test_exception_includes_traceback_in_extra(self, migration_logger, sink):
        try:
            raise ValueError("boom")
        except ValueError as exc:
            migration_logger.exception(exc, ErrorCode.EXCEPTION, "failed")

        extra = sink.log.call_args.kwargs["extra"]
        assert extra["exception_type"] == "ValueError"
        assert "exception_traceback" in extra

    def test_info_returns_none(self, migration_logger):
        result = migration_logger.info(ErrorCode.PERSIST_SUCCESS, "done")
        assert result is None

    def test_sink_error_is_best_effort(self, migration_logger, sink):
        """Logger should not raise if the underlying sink fails."""
        sink.log.side_effect = RuntimeError("sink exploded")

        with pytest.raises(RuntimeError):
            migration_logger.error(ErrorCode.UNKNOWN, "test")

    def test_context_required_for_emit(self):
        logger = MigrationLogger()
        with pytest.raises(ValueError, match="LogContext not set"):
            logger.error(ErrorCode.UNKNOWN, "no context")

    def test_fingerprint_is_stable(self, migration_logger):
        """Same inputs produce the same fingerprint."""
        migration_logger.error(ErrorCode.UNKNOWN, "msg1", event_type="et1")
        migration_logger.error(ErrorCode.UNKNOWN, "msg1", event_type="et1")

        fp1 = migration_logger._sink.log.call_args_list[0].kwargs["extra"]["fingerprint"]
        fp2 = migration_logger._sink.log.call_args_list[1].kwargs["extra"]["fingerprint"]
        assert fp1 == fp2

    def test_fingerprint_differs_for_different_messages(self, migration_logger):
        migration_logger.error(ErrorCode.UNKNOWN, "msg1")
        migration_logger.error(ErrorCode.UNKNOWN, "msg2")

        fp1 = migration_logger._sink.log.call_args_list[0].kwargs["extra"]["fingerprint"]
        fp2 = migration_logger._sink.log.call_args_list[1].kwargs["extra"]["fingerprint"]
        assert fp1 != fp2


# =============================================================================
# EventTypeMigrationLogger
# =============================================================================


class TestEventTypeMigrationLogger:
    @pytest.fixture
    def context(self):
        return LogContext(
            migration_request_id="MR-test-00000000",
            tenant_name="test-tenant",
            dry_run=True,
        )

    @pytest.fixture
    def sink(self):
        return MagicMock()

    @pytest.fixture
    def et_logger(self, context, sink):
        parent = MigrationLogger(context=context, sink=sink)
        return parent.for_event_type("fire_rep")

    def test_auto_tags_event_type(self, et_logger, sink):
        et_logger.error(ErrorCode.UNKNOWN, "oops")

        extra = sink.log.call_args.kwargs["extra"]
        assert extra["event_type"] == "fire_rep"

    def test_returns_message(self, et_logger):
        msg = et_logger.warning(ErrorCode.SCHEMA_TRANSFORM, "field skipped")
        assert msg == "field skipped"

    def test_delegates_to_parent_context(self, et_logger):
        assert et_logger.context.tenant_name == "test-tenant"

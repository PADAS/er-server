from __future__ import annotations

import hashlib
import logging
import re
import traceback
import uuid
from dataclasses import dataclass, field
from enum import Enum

from django.utils import timezone
from rest_framework.request import Request

from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    EVENT_TYPE = "event_type"
    TRANSFORM = "transform"
    CHOICES_RESOLUTION = "choices_resolution"  # All hardcoded choice resolution errors
    PERSISTENCE = "persistence"
    REPAIR = "repair"  # V2 schema collection repair (tiered classification + execution)
    GENERAL = "general"


class ErrorCode(tuple[ErrorCategory, str], Enum):
    UNKNOWN = (ErrorCategory.GENERAL, "unknown")

    # Event type
    EVENT_TYPE_NOT_FOUND = (ErrorCategory.EVENT_TYPE, "event_type_not_found")
    PERMISSION_DENIED = (ErrorCategory.EVENT_TYPE, "permission_denied")
    VERSION_VALIDATION = (ErrorCategory.EVENT_TYPE, "version_validation")
    SCHEMA_PARSE = (ErrorCategory.EVENT_TYPE, "schema_parse")

    # Schema transformation
    SCHEMA_TRANSFORM = (ErrorCategory.TRANSFORM, "schema_transform")
    UNSUPPORTED_FEATURES = (ErrorCategory.TRANSFORM, "unsupported_features")

    # Hardcoded choice resolution
    CHOICE_RESOLUTION_REQUIRED = (ErrorCategory.CHOICES_RESOLUTION, "choice_resolution_required")
    DUPLICATE_RESOLUTION = (ErrorCategory.CHOICES_RESOLUTION, "duplicate_resolution")
    UNKNOWN_RESOLUTION_PATH = (ErrorCategory.CHOICES_RESOLUTION, "unknown_resolution_path")
    INVALID_RESOLUTION = (ErrorCategory.CHOICES_RESOLUTION, "invalid_resolution")
    CHOICE_FIELD_EXISTS = (ErrorCategory.CHOICES_RESOLUTION, "choice_field_exists")
    CHOICE_FIELD_BATCH_CONFLICT = (ErrorCategory.CHOICES_RESOLUTION, "choice_field_batch_conflict")
    DEPENDENCY_NOT_FOUND = (ErrorCategory.CHOICES_RESOLUTION, "dependency_not_found")
    DEPENDENCY_ORDER = (ErrorCategory.CHOICES_RESOLUTION, "dependency_order")
    DEPENDENCY_INVALID = (ErrorCategory.CHOICES_RESOLUTION, "dependency_invalid")
    DEPENDENCY_NOT_PERSISTED = (ErrorCategory.CHOICES_RESOLUTION, "dependency_not_persisted")
    REPLACE_REF_FAILED = (ErrorCategory.CHOICES_RESOLUTION, "replace_ref_failed")

    # Persistence
    CHOICE_CREATION_FAILED = (ErrorCategory.PERSISTENCE, "choice_creation_failed")
    PERSIST_FAILED = (ErrorCategory.PERSISTENCE, "persist_failed")

    # Repair (V2 schema collection repair).
    #
    # The set is deliberately small: only emit signals that are actually actionable.
    #
    # INFO codes record *successful applies* - one per concrete repair strategy.
    # These are the only routine events worth recording at info severity; everything
    # else either lives in the report (skips, not-migrated) or warrants warning/error
    # severity.
    REPAIR_REBUILT_FROM_V1 = (ErrorCategory.REPAIR, "repair_rebuilt_from_v1")
    REPAIR_RECONSTRUCTED_FROM_JSON = (ErrorCategory.REPAIR, "repair_reconstructed_from_json")
    # WARNING - classification surfaced a diagnostic note (e.g. multiple
    # candidate migration revisions, snapshot anomalies). Operators want
    # to see these but they don't block the run.
    REPAIR_AMBIGUOUS_HISTORY = (ErrorCategory.REPAIR, "repair_ambiguous_history")
    # ERROR - apply layer reported an error_* action, or classification
    # itself raised.
    REPAIR_FAILED = (ErrorCategory.REPAIR, "repair_failed")

    # General
    EXCEPTION = (ErrorCategory.GENERAL, "exception")

    @property
    def category(self) -> ErrorCategory:
        return self.value[0]

    @property
    def code(self) -> str:
        return self.value[1]


@dataclass(frozen=True)
class LogContext:
    migration_request_id: str
    tenant_name: str
    dry_run: bool

    @staticmethod
    def _normalize_id_component(value: str) -> str:
        normalized_value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return normalized_value or "tenant"

    @classmethod
    def build_migration_request_id(cls, tenant_name: str) -> str:
        tenant_component = cls._normalize_id_component(tenant_name)
        unique_component = uuid.uuid4().hex[:8]
        return f"MR-{tenant_component}-{unique_component}"

    @classmethod
    def build_repair_request_id(cls, tenant_name: str) -> str:
        tenant_component = cls._normalize_id_component(tenant_name)
        unique_component = uuid.uuid4().hex[:8]
        return f"RP-{tenant_component}-{unique_component}"

    @classmethod
    def for_repair(cls, tenant_name: str, dry_run: bool, request_id: str = "") -> LogContext:
        """Build a LogContext for a repair run (no HTTP request required).

        Used by the management command that walks revisions and classifies/repairs
        EventTypes outside of any user-initiated request.
        """
        request_id = (request_id or "").strip() or cls.build_repair_request_id(tenant_name=tenant_name)
        return cls(migration_request_id=request_id, tenant_name=tenant_name, dry_run=dry_run)

    @classmethod
    def resolve_migration_request_id(cls, headers: dict, tenant_name: str) -> str:
        migration_request_id = headers.get("X-Migration-Request-Id", "")
        migration_request_id = str(migration_request_id).strip()
        if migration_request_id:
            return migration_request_id
        return cls.build_migration_request_id(tenant_name=tenant_name)

    @classmethod
    def from_request(cls, request: Request, dry_run: bool) -> LogContext:
        raw_request = getattr(request, "_request", request)
        headers = getattr(request, "headers", None) or getattr(raw_request, "headers", {}) or {}
        tenant_name = ""
        try:
            tenant_name = str(get_tenant_settings().domain or "")
        except TenantNotFoundInLocalThreadException:
            tenant_name = ""
        if not tenant_name:
            tenant_name = str(getattr(raw_request, "META", {}).get("HTTP_HOST", "") or "")

        return cls(
            migration_request_id=cls.resolve_migration_request_id(headers=headers, tenant_name=tenant_name),
            tenant_name=tenant_name,
            dry_run=dry_run,
        )


@dataclass(frozen=True)
class LogEntry:
    """Internal record of a single log event.

    The message is shared between Cloud Logging and the API response
    (MigrationResult).  Structured extra fields (tenant, event_type,
    code, fingerprint, …) provide the filtering and dedup dimensions
    in Cloud Logging — no need to bake them into the message text.
    """

    severity: int
    code: ErrorCode
    message: str
    event_type: str = ""
    timestamp: str = field(default_factory=lambda: timezone.now().isoformat())
    fingerprint: str = ""
    extra: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code.category.value}:{self.code.code} - {self.message}"


class MigrationLogger:
    """Root migration logger — owns context, emits structured logs, creates scoped children.

    Every log call simultaneously:
    1. Emits a structured record to Python logging (→ Cloud Logging)
       with rich structured extra (tenant, event_type, code, fingerprint)
    2. Returns the same message string so the caller can append it to
       MigrationResult.errors / .warnings inline, preserving flow control.
    """

    def __init__(self, *, context: LogContext | None = None, sink: logging.Logger | None = None):
        self._context = context
        self._sink = sink or logger

    @classmethod
    def from_request(
        cls, request: Request, *, dry_run: bool = True, sink: logging.Logger | None = None
    ) -> MigrationLogger:
        return cls(context=LogContext.from_request(request, dry_run=dry_run), sink=sink)

    @property
    def context(self) -> LogContext:
        if self._context is None:
            raise ValueError("LogContext not set — call from_request() or pass context= to __init__")
        return self._context

    # ── Scoped child ────────────────────────────────────────────────

    def for_event_type(self, event_type_value: str) -> EventTypeMigrationLogger:
        """Create a child logger scoped to a specific EventType."""
        return EventTypeMigrationLogger(parent=self, event_type=event_type_value)

    # ── Public logging methods (emit + return) ──────────────────────

    def error(self, code: ErrorCode, message: str, *, event_type: str = "", **extra) -> str:
        return self._emit(logging.ERROR, code, message, event_type=event_type, **extra)

    def warning(self, code: ErrorCode, message: str, *, event_type: str = "", **extra) -> str:
        return self._emit(logging.WARNING, code, message, event_type=event_type, **extra)

    def critical(self, code: ErrorCode, message: str, *, event_type: str = "", **extra) -> str:
        return self._emit(logging.CRITICAL, code, message, event_type=event_type, **extra)

    def info(self, code: ErrorCode, message: str, *, event_type: str = "", **extra) -> None:
        self._emit(logging.INFO, code, message, event_type=event_type, **extra)

    def exception(self, exc: BaseException, code: ErrorCode, message: str, *, event_type: str = "", **extra) -> str:
        extra["exception_type"] = type(exc).__qualname__
        extra["exception_traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
        return self._emit(logging.ERROR, code, message, event_type=event_type, **extra)

    # ── Internal ────────────────────────────────────────────────────

    def _emit(
        self,
        severity: int,
        code: ErrorCode,
        message: str,
        *,
        event_type: str = "",
        **extra,
    ) -> str:
        """Build a LogEntry, emit to Python logging, return message."""
        fingerprint = self._build_fingerprint(code=code, event_type=event_type, message=message)

        entry = LogEntry(
            severity=severity,
            code=code,
            message=message,
            event_type=event_type,
            fingerprint=fingerprint,
            extra=extra,
        )
        self._emit_to_sink(entry)
        return message

    def _emit_to_sink(self, entry: LogEntry) -> None:
        """Send structured log record to the Python logger."""
        structured_extra = {
            "migration_request_id": self.context.migration_request_id,
            "tenant_name": self.context.tenant_name,
            "dry_run": self.context.dry_run,
            "event_type": entry.event_type,
            "error_code": entry.code.code,
            "error_category": entry.code.category.value,
            "fingerprint": entry.fingerprint,
        }
        if entry.extra:
            structured_extra.update(entry.extra)

        self._sink.log(entry.severity, entry.message, extra=structured_extra)

    def _build_fingerprint(self, *, code: ErrorCode, event_type: str, message: str) -> str:
        """SHA-256 of tenant|event_type|code|message for Cloud Logging dedup."""
        tenant = self._context.tenant_name if self._context else ""
        canonical = "|".join([tenant, event_type, code.code, message])
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class EventTypeMigrationLogger:
    """Scoped child logger that auto-tags all entries with a specific event_type.

    Delegates entirely to the parent MigrationLogger — no separate state.
    """

    def __init__(self, parent: MigrationLogger, event_type: str):
        self._parent = parent
        self._event_type = event_type

    @property
    def context(self) -> LogContext:
        return self._parent.context

    def error(self, code: ErrorCode, message: str, **extra) -> str:
        return self._parent.error(code, message, event_type=self._event_type, **extra)

    def warning(self, code: ErrorCode, message: str, **extra) -> str:
        return self._parent.warning(code, message, event_type=self._event_type, **extra)

    def critical(self, code: ErrorCode, message: str, **extra) -> str:
        return self._parent.critical(code, message, event_type=self._event_type, **extra)

    def info(self, code: ErrorCode, message: str, **extra) -> None:
        self._parent.info(code, message, event_type=self._event_type, **extra)

    def exception(self, exc: BaseException, code: ErrorCode, message: str, **extra) -> str:
        return self._parent.exception(exc, code, message, event_type=self._event_type, **extra)

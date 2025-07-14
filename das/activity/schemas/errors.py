"""Structured error definitions for schema-related operations.

This module centralises all error data-structures so that every component
(rendering, retrieving, validation, high-level services) can surface
consistent, machine-readable errors to the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class StrEnum(str, Enum):
    """Enum that can be compared to str values directly."""

    def __str__(self) -> str:  # noqa: D401 (simple override)
        return str(self.value)


class ErrorCategory(StrEnum):
    """High-level categories for schema processing errors."""

    VALIDATION = "validation"
    RESOLUTION = "resolution"
    RETRIEVAL = "retrieval"
    RENDERING = "rendering"
    INTERNAL = "internal"


class ErrorCode(StrEnum):
    """Stable codes to allow i18n and programmatic handling."""

    # Validation
    SCHEMA_PARSING_ERROR = "schema_parsing_error"
    MISSING_SCHEMA_STRUCTURE = "missing_schema_structure"
    SCHEMA_VALIDATION_ERROR = "schema_validation_error"  # jsonschema validation

    # Resolution (during dereferencing)
    UNRESOLVABLE_REFERENCE = "unresolvable_reference"  # no resolvers found for $ref
    RESOLVER_CONFIGURATION_ERROR = "resolver_configuration_error"  # resolver config error, e.g. required token or etc.

    # Retrieval (dynamic schema)
    VIEW_NOT_FOUND = "view_not_found"
    VIEW_IS_NOT_DYNAMIC = "view_is_not_dynamic"
    SOURCE_VIEW_ERROR = "source_view_error"

    # Rendering
    SCHEMA_RENDERING_ERROR = "schema_rendering_error"

    # Internal fallback
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass
class ErrorHint:  # pylint: disable=too-many-instance-attributes
    """Actionable hint for the UI/user."""

    message: str
    action_type: str = "fix"  # e.g., fix / check / contact_support
    details: Optional[Dict[str, Any]] = None


@dataclass
class SchemaError:
    """Structured error object."""

    category: ErrorCategory
    code: ErrorCode
    message: str
    context: Dict[str, Any]
    # "severity" needs to be iterated:
    # - the schema is not procesable, or is rendered but invalid
    # - the schema is valid, but the not resolved reference makes it unusable
    # - the schema is valid, and the not resolved reference is for a not required field, the less severe
    severity: str = "error"
    hints: List[ErrorHint] = field(default_factory=list)
    cause: Optional[Exception] = None  # raw exception for logging only

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serialisable dict for API responses."""
        return {
            "category": self.category.value,
            "severity": self.severity,
            "code": self.code.value,
            "message": self.message,
            "hints": [
                {
                    "message": hint.message,
                    "action_type": hint.action_type,
                    "details": hint.details or {},
                }
                for hint in self.hints
            ],
            "context": self.context,
        }

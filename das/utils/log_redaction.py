from __future__ import annotations

from typing import Final
from urllib.parse import parse_qsl, urlencode

_REDACTED: Final[str] = "***REDACTED***"

_SENSITIVE_QUERY_PARAMS: Final[frozenset[str]] = frozenset(
    {
        "auth",
        "token",
        "access_token",
        "api_key",
        "apikey",
        "key",
        "jwt",
        "bearer",
    }
)


def redact_sensitive_query_string(query_string: str) -> str:
    """Return ``query_string`` with credential-bearing values replaced.

    Key order is preserved. Non-sensitive keys pass through unchanged.
    Key comparison is case-insensitive (``AUTH=`` and ``auth=`` are both
    redacted).

    Returns the input verbatim when no sensitive keys are present, so the
    common case incurs no re-encoding cost.
    """
    if not query_string:
        return query_string
    pairs = parse_qsl(query_string, keep_blank_values=True)
    if not any(k.lower() in _SENSITIVE_QUERY_PARAMS for k, _ in pairs):
        return query_string
    return urlencode([(k, _REDACTED if k.lower() in _SENSITIVE_QUERY_PARAMS else v) for k, v in pairs])


def redact_sensitive_query_in_path(path: str) -> str:
    """Like :func:`redact_sensitive_query_string` but accepts ``path?query``."""
    if "?" not in path:
        return path
    base, _, query = path.partition("?")
    redacted = redact_sensitive_query_string(query)
    return f"{base}?{redacted}" if redacted else base

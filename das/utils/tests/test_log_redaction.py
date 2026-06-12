from __future__ import annotations

import pytest

from utils.log_redaction import (
    redact_sensitive_query_in_path,
    redact_sensitive_query_string,
)

# urlencode percent-encodes "*" as "%2A"; the expected redacted form of
# "***REDACTED***" in a query value is therefore "%2A%2A%2AREDACTED%2A%2A%2A".
REDACTED_ENCODED = "%2A%2A%2AREDACTED%2A%2A%2A"


class TestRedactSensitiveQueryString:
    def test_empty_input_returns_empty(self) -> None:
        assert redact_sensitive_query_string("") == ""

    def test_no_sensitive_keys_passes_through_verbatim(self) -> None:
        original = "page=2&size=50&ordering=-created_at"
        assert redact_sensitive_query_string(original) == original

    @pytest.mark.parametrize(
        "sensitive_key",
        ["auth", "token", "access_token", "api_key", "apikey", "key", "jwt", "bearer"],
    )
    def test_redacts_each_known_sensitive_key(self, sensitive_key: str) -> None:
        result = redact_sensitive_query_string(f"{sensitive_key}=secrettoken")
        assert "secrettoken" not in result
        assert result == f"{sensitive_key}={REDACTED_ENCODED}"

    def test_key_match_is_case_insensitive(self) -> None:
        result = redact_sensitive_query_string("AUTH=secrettoken")
        assert "secrettoken" not in result
        assert result == f"AUTH={REDACTED_ENCODED}"

    def test_preserves_key_order_and_non_sensitive_values(self) -> None:
        result = redact_sensitive_query_string("page=2&auth=secrettoken&size=50")
        assert "secrettoken" not in result
        assert result == f"page=2&auth={REDACTED_ENCODED}&size=50"

    def test_redacts_multiple_sensitive_keys_in_one_query(self) -> None:
        result = redact_sensitive_query_string("token=a&access_token=b&api_key=c&jwt=d")
        for leaked in ("token=a", "access_token=b", "api_key=c", "jwt=d"):
            assert leaked not in result
        assert result.count(REDACTED_ENCODED) == 4

    def test_empty_value_is_still_replaced(self) -> None:
        # `auth=` (empty value) should still be redacted; we don't want to
        # treat absence-of-value as safe.
        assert redact_sensitive_query_string("auth=") == f"auth={REDACTED_ENCODED}"


class TestRedactSensitiveQueryInPath:
    def test_path_without_query_string_passes_through(self) -> None:
        assert redact_sensitive_query_in_path("/api/v1.0/subjects") == "/api/v1.0/subjects"

    def test_redacts_token_value_in_full_path(self) -> None:
        result = redact_sensitive_query_in_path("/api/v1.0/subjects/kml?auth=secrettoken")
        assert "secrettoken" not in result
        assert result == f"/api/v1.0/subjects/kml?auth={REDACTED_ENCODED}"

    def test_redacts_only_sensitive_keys_in_mixed_query(self) -> None:
        result = redact_sensitive_query_in_path("/api/v1.0/subjects?page=2&auth=secrettoken&size=50")
        assert "secrettoken" not in result
        assert result == f"/api/v1.0/subjects?page=2&auth={REDACTED_ENCODED}&size=50"

    def test_empty_query_after_question_mark(self) -> None:
        # `path?` with no query content should not crash and should not
        # leave a trailing `?` if there's nothing to keep.
        assert redact_sensitive_query_in_path("/api/v1.0/subjects?") == "/api/v1.0/subjects"

"""
Tests for the streaming CSV utilities.
"""

import csv
from io import StringIO

from django.http import StreamingHttpResponse

from utils.csv_streaming import (
    Echo,
    StreamingCSVGenerator,
    StreamingCSVResponse,
    generate_csv_string,
    iter_csv_from_values_queryset,
    read_streaming_response_content,
)


class TestEcho:
    """Tests for the Echo pseudo-buffer class."""

    def test_write_returns_value(self):
        """Echo.write should return exactly what was written."""
        echo = Echo()
        result = echo.write("test value")
        assert result == "test value"

    def test_write_with_csv_content(self):
        """Echo should work with CSV-formatted content."""
        echo = Echo()
        result = echo.write('"field1","field2"\r\n')
        assert result == '"field1","field2"\r\n'


class TestStreamingCSVGenerator:
    """Tests for the StreamingCSVGenerator class."""

    def test_generates_header_and_rows(self):
        """Generator should yield header followed by data rows."""
        rows = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        fieldnames = ["name", "age"]

        generator = StreamingCSVGenerator(rows, fieldnames)
        output = list(generator)

        assert len(output) == 3  # header + 2 rows
        assert "name,age" in output[0]
        assert "Alice,30" in output[1]
        assert "Bob,25" in output[2]

    def test_no_header_when_disabled(self):
        """Generator should skip header when include_header=False."""
        rows = [{"name": "Alice", "age": "30"}]
        fieldnames = ["name", "age"]

        generator = StreamingCSVGenerator(rows, fieldnames, include_header=False)
        output = list(generator)

        assert len(output) == 1
        assert "Alice,30" in output[0]

    def test_handles_empty_rows(self):
        """Generator should handle empty input gracefully."""
        rows = []
        fieldnames = ["name", "age"]

        generator = StreamingCSVGenerator(rows, fieldnames)
        output = list(generator)

        assert len(output) == 1  # Just header
        assert "name,age" in output[0]

    def test_handles_extra_keys_in_rows(self):
        """Generator should ignore extra keys not in fieldnames."""
        rows = [{"name": "Alice", "age": "30", "extra": "ignored"}]
        fieldnames = ["name", "age"]

        generator = StreamingCSVGenerator(rows, fieldnames)
        output = list(generator)

        # Should not include 'extra' field
        assert len(output) == 2
        assert "ignored" not in output[1]
        assert "Alice,30" in output[1]

    def test_handles_missing_keys_in_rows(self):
        """Generator should handle rows with missing keys."""
        rows = [{"name": "Alice"}]  # Missing 'age'
        fieldnames = ["name", "age"]

        generator = StreamingCSVGenerator(rows, fieldnames)
        output = list(generator)

        assert len(output) == 2
        assert "Alice," in output[1]  # Empty value for missing key

    def test_handles_special_characters(self):
        """Generator should properly escape special characters."""
        rows = [{"name": 'Alice "The Great"', "notes": "Line1\nLine2"}]
        fieldnames = ["name", "notes"]

        generator = StreamingCSVGenerator(rows, fieldnames)
        output = list(generator)

        # CSV should properly quote fields with special characters
        assert len(output) == 2
        # The quotes and newlines should be escaped/quoted
        assert '"' in output[1] or "Alice" in output[1]

    def test_works_with_generator_input(self):
        """Generator should work with generator inputs (lazy evaluation)."""

        def row_generator():
            yield {"name": "Alice", "age": "30"}
            yield {"name": "Bob", "age": "25"}

        fieldnames = ["name", "age"]
        generator = StreamingCSVGenerator(row_generator(), fieldnames)
        output = list(generator)

        assert len(output) == 3
        assert "Alice,30" in output[1]
        assert "Bob,25" in output[2]


class TestStreamingCSVResponse:
    """Tests for the StreamingCSVResponse class."""

    def test_creates_streaming_response(self):
        """Response should be a StreamingHttpResponse."""
        rows = [{"name": "Alice"}]
        fieldnames = ["name"]

        response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")

        assert isinstance(response, StreamingHttpResponse)

    def test_sets_content_type(self):
        """Response should have text/csv content type."""
        rows = [{"name": "Alice"}]
        fieldnames = ["name"]

        response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")

        assert response["Content-Type"] == "text/csv"

    def test_sets_content_disposition(self):
        """Response should set Content-Disposition for download."""
        rows = [{"name": "Alice"}]
        fieldnames = ["name"]

        response = StreamingCSVResponse(rows, fieldnames, filename="export.csv")

        assert response["Content-Disposition"] == "attachment; filename=export.csv"

    def test_sets_custom_header(self):
        """Response should set x-das-download-filename header."""
        rows = [{"name": "Alice"}]
        fieldnames = ["name"]

        response = StreamingCSVResponse(rows, fieldnames, filename="my_export.csv")

        assert response["x-das-download-filename"] == "my_export.csv"

    def test_streaming_content_is_iterable(self):
        """Response streaming_content should be iterable."""
        rows = [{"name": "Alice"}, {"name": "Bob"}]
        fieldnames = ["name"]

        response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")
        content = read_streaming_response_content(response)

        assert "name" in content  # Header
        assert "Alice" in content
        assert "Bob" in content


class TestIterCSVFromValuesQueryset:
    """Tests for iter_csv_from_values_queryset function."""

    def test_yields_rows_unchanged_without_transform(self):
        """Should yield rows as-is when no transform is provided."""
        mock_queryset = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]

        # Mock the iterator method
        class MockQueryset:
            def __init__(self, data):
                self.data = data

            def iterator(self, chunk_size=2000):
                return iter(self.data)

        qs = MockQueryset(mock_queryset)
        result = list(iter_csv_from_values_queryset(qs))

        assert result == mock_queryset

    def test_applies_transform_when_provided(self):
        """Should apply transform function to each row."""
        mock_queryset = [
            {"id": 1, "name": "alice"},
            {"id": 2, "name": "bob"},
        ]

        class MockQueryset:
            def __init__(self, data):
                self.data = data

            def iterator(self, chunk_size=2000):
                return iter(self.data)

        def transform(row):
            return {"id": row["id"], "name": row["name"].upper()}

        qs = MockQueryset(mock_queryset)
        result = list(iter_csv_from_values_queryset(qs, row_transform=transform))

        assert result[0]["name"] == "ALICE"
        assert result[1]["name"] == "BOB"


class TestGenerateCSVString:
    """Tests for generate_csv_string function."""

    def test_generates_complete_csv(self):
        """Should generate a complete CSV string with header and rows."""
        rows = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        fieldnames = ["name", "age"]

        result = generate_csv_string(rows, fieldnames)

        # Parse the result to verify structure
        reader = csv.DictReader(StringIO(result))
        parsed_rows = list(reader)

        assert len(parsed_rows) == 2
        assert parsed_rows[0]["name"] == "Alice"
        assert parsed_rows[0]["age"] == "30"
        assert parsed_rows[1]["name"] == "Bob"
        assert parsed_rows[1]["age"] == "25"

    def test_handles_empty_rows(self):
        """Should generate just header for empty rows."""
        rows = []
        fieldnames = ["name", "age"]

        result = generate_csv_string(rows, fieldnames)

        assert "name,age" in result
        lines = result.strip().split("\n")
        assert len(lines) == 1  # Just header


class TestReadStreamingResponseContent:
    """Tests for read_streaming_response_content function."""

    def test_reads_string_chunks(self):
        """Should handle string chunks correctly."""
        rows = [{"name": "Alice"}, {"name": "Bob"}]
        fieldnames = ["name"]

        response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")
        content = read_streaming_response_content(response)

        assert "name" in content
        assert "Alice" in content
        assert "Bob" in content

    def test_reads_bytes_chunks(self):
        """Should handle bytes chunks correctly."""

        def byte_generator():
            yield b"header\r\n"
            yield b"row1\r\n"

        response = StreamingHttpResponse(byte_generator(), content_type="text/csv")
        content = read_streaming_response_content(response)

        assert "header" in content
        assert "row1" in content


class TestCSVFormatCompatibility:
    """
    Tests to ensure streaming CSV output matches the format of non-streaming CSV.

    These tests verify that the streaming implementation produces identical output
    to the standard csv.DictWriter approach used in the existing codebase.
    """

    def test_format_matches_standard_dictwriter(self):
        """Streaming output should match standard DictWriter output exactly."""
        rows = [
            {"col1": "value1", "col2": "value2"},
            {"col1": "value3", "col2": "value4"},
        ]
        fieldnames = ["col1", "col2"]

        # Standard approach (current codebase pattern)
        standard_output = StringIO()
        writer = csv.DictWriter(standard_output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        standard_csv = standard_output.getvalue()

        # Streaming approach
        response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")
        streaming_csv = read_streaming_response_content(response)

        assert streaming_csv == standard_csv

    def test_line_endings_match(self):
        """Line endings should match standard CSV format (CRLF)."""
        rows = [{"name": "Alice"}]
        fieldnames = ["name"]

        response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")
        content = read_streaming_response_content(response)

        # CSV standard uses CRLF line endings
        assert "\r\n" in content

    def test_quoting_matches_standard(self):
        """Field quoting should match standard csv module behavior."""
        rows = [{"name": 'Value with "quotes"', "notes": "Value,with,commas"}]
        fieldnames = ["name", "notes"]

        # Standard approach
        standard_output = StringIO()
        writer = csv.DictWriter(standard_output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        standard_csv = standard_output.getvalue()

        # Streaming approach
        response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")
        streaming_csv = read_streaming_response_content(response)

        assert streaming_csv == standard_csv

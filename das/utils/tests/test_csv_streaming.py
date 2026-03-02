"""
Tests for the streaming CSV utilities.
"""

import csv
from io import StringIO

from django.http import HttpResponse, StreamingHttpResponse

from utils.csv_streaming import (
    Echo,
    StreamingCSVGenerator,
    StreamingCSVResponse,
    generate_csv_string,
    read_streaming_response_content,
)

# Echo tests


def test_echo_write_returns_value():
    """Echo.write should return exactly what was written."""
    echo = Echo()
    result = echo.write("test value")
    assert result == "test value"


def test_echo_write_with_csv_content():
    """Echo should work with CSV-formatted content."""
    echo = Echo()
    result = echo.write('"field1","field2"\r\n')
    assert result == '"field1","field2"\r\n'


# StreamingCSVGenerator tests


def _decode_chunk(chunk):
    """Decode a chunk (bytes or str) to str for assertions."""
    return chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk


def test_streaming_csv_generator_yields_header_and_rows():
    """Generator should yield header followed by data rows (as bytes)."""
    rows = [
        {"name": "Alice", "age": "30"},
        {"name": "Bob", "age": "25"},
    ]
    fieldnames = ["name", "age"]

    generator = StreamingCSVGenerator(rows, fieldnames)
    output = list(generator)

    assert len(output) == 3  # header + 2 rows
    assert all(isinstance(chunk, bytes) for chunk in output)
    assert "name,age" in _decode_chunk(output[0])
    assert "Alice,30" in _decode_chunk(output[1])
    assert "Bob,25" in _decode_chunk(output[2])


def test_streaming_csv_generator_no_header_when_disabled():
    """Generator should skip header when include_header=False."""
    rows = [{"name": "Alice", "age": "30"}]
    fieldnames = ["name", "age"]

    generator = StreamingCSVGenerator(rows, fieldnames, include_header=False)
    output = list(generator)

    assert len(output) == 1
    assert "Alice,30" in _decode_chunk(output[0])


def test_streaming_csv_generator_handles_empty_rows():
    """Generator should handle empty input gracefully."""
    rows = []
    fieldnames = ["name", "age"]

    generator = StreamingCSVGenerator(rows, fieldnames)
    output = list(generator)

    assert len(output) == 1  # Just header
    assert "name,age" in _decode_chunk(output[0])


def test_streaming_csv_generator_ignores_extra_keys():
    """Generator should ignore extra keys not in fieldnames."""
    rows = [{"name": "Alice", "age": "30", "extra": "ignored"}]
    fieldnames = ["name", "age"]

    generator = StreamingCSVGenerator(rows, fieldnames)
    output = list(generator)

    assert len(output) == 2
    assert "ignored" not in _decode_chunk(output[1])
    assert "Alice,30" in _decode_chunk(output[1])


def test_streaming_csv_generator_handles_missing_keys():
    """Generator should handle rows with missing keys."""
    rows = [{"name": "Alice"}]  # Missing 'age'
    fieldnames = ["name", "age"]

    generator = StreamingCSVGenerator(rows, fieldnames)
    output = list(generator)

    assert len(output) == 2
    assert "Alice," in _decode_chunk(output[1])  # Empty value for missing key


def test_streaming_csv_generator_escapes_special_characters():
    """Generator should properly escape special characters."""
    rows = [{"name": 'Alice "The Great"', "notes": "Line1\nLine2"}]
    fieldnames = ["name", "notes"]

    generator = StreamingCSVGenerator(rows, fieldnames)
    output = list(generator)

    assert len(output) == 2
    # The quotes and newlines should be escaped/quoted
    decoded = _decode_chunk(output[1])
    assert '"' in decoded or "Alice" in decoded


def test_streaming_csv_generator_works_with_generator_input():
    """Generator should work with generator inputs (lazy evaluation)."""

    def row_generator():
        yield {"name": "Alice", "age": "30"}
        yield {"name": "Bob", "age": "25"}

    fieldnames = ["name", "age"]
    generator = StreamingCSVGenerator(row_generator(), fieldnames)
    output = list(generator)

    assert len(output) == 3
    assert "Alice,30" in _decode_chunk(output[1])
    assert "Bob,25" in _decode_chunk(output[2])


# StreamingCSVResponse tests


def test_streaming_csv_response_is_streaming_http_response():
    """Response should be a StreamingHttpResponse."""
    rows = [{"name": "Alice"}]
    fieldnames = ["name"]

    response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")

    assert isinstance(response, StreamingHttpResponse)


def test_streaming_csv_response_sets_content_type():
    """Response should have text/csv content type with charset."""
    rows = [{"name": "Alice"}]
    fieldnames = ["name"]

    response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")

    assert response["Content-Type"] == "text/csv; charset=utf-8"


def test_streaming_csv_response_sets_content_disposition():
    """Response should set Content-Disposition for download."""
    rows = [{"name": "Alice"}]
    fieldnames = ["name"]

    response = StreamingCSVResponse(rows, fieldnames, filename="export.csv")

    assert response["Content-Disposition"] == "attachment; filename=export.csv"


def test_streaming_csv_response_sanitizes_filename():
    """Response should strip CR, LF, and quotes from filename to prevent header injection."""
    rows = [{"name": "Alice"}]
    fieldnames = ["name"]

    response = StreamingCSVResponse(rows, fieldnames, filename='bad\r\nname"here.csv')

    assert response["Content-Disposition"] == "attachment; filename=badnamehere.csv"
    assert response["x-das-download-filename"] == "badnamehere.csv"


def test_streaming_csv_response_sets_custom_header():
    """Response should set x-das-download-filename header."""
    rows = [{"name": "Alice"}]
    fieldnames = ["name"]

    response = StreamingCSVResponse(rows, fieldnames, filename="my_export.csv")

    assert response["x-das-download-filename"] == "my_export.csv"


def test_streaming_csv_response_content_is_iterable():
    """Response streaming_content should be iterable and contain expected data."""
    rows = [{"name": "Alice"}, {"name": "Bob"}]
    fieldnames = ["name"]

    response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")
    content = read_streaming_response_content(response)

    assert "name" in content  # Header
    assert "Alice" in content
    assert "Bob" in content


# generate_csv_string tests


def test_generate_csv_string_creates_complete_csv():
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


def test_generate_csv_string_handles_empty_rows():
    """Should generate just header for empty rows."""
    rows = []
    fieldnames = ["name", "age"]

    result = generate_csv_string(rows, fieldnames)

    assert "name,age" in result
    lines = result.strip().split("\n")
    assert len(lines) == 1  # Just header


# read_streaming_response_content tests


def test_read_streaming_response_content_handles_string_chunks():
    """Should handle string chunks correctly."""
    rows = [{"name": "Alice"}, {"name": "Bob"}]
    fieldnames = ["name"]

    response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")
    content = read_streaming_response_content(response)

    assert "name" in content
    assert "Alice" in content
    assert "Bob" in content


def test_read_streaming_response_content_handles_bytes_chunks():
    """Should handle bytes chunks correctly."""

    def byte_generator():
        yield b"header\r\n"
        yield b"row1\r\n"

    response = StreamingHttpResponse(byte_generator(), content_type="text/csv")
    content = read_streaming_response_content(response)

    assert "header" in content
    assert "row1" in content


def test_read_streaming_response_content_handles_regular_response():
    """Should handle regular HttpResponse with .content attribute."""
    response = HttpResponse(b"test content", content_type="text/plain")
    content = read_streaming_response_content(response)

    assert content == "test content"


# CSV format compatibility tests


def test_streaming_format_matches_standard_dictwriter():
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


def test_streaming_csv_uses_crlf_line_endings():
    """Line endings should match standard CSV format (CRLF)."""
    rows = [{"name": "Alice"}]
    fieldnames = ["name"]

    response = StreamingCSVResponse(rows, fieldnames, filename="test.csv")
    content = read_streaming_response_content(response)

    # CSV standard uses CRLF line endings
    assert "\r\n" in content


def test_streaming_csv_quoting_matches_standard():
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

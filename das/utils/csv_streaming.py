"""
Streaming CSV utilities for large data exports.

This module provides utilities for generating CSV responses that stream data
incrementally, avoiding memory issues with large datasets and preventing
request timeouts.

Usage:
    from utils.csv_streaming import StreamingCSVResponse

    def get_rows():
        for item in queryset.iterator(chunk_size=2000):
            yield {
                'column1': item.field1,
                'column2': item.field2,
            }

    response = StreamingCSVResponse(
        row_generator=get_rows(),
        fieldnames=['column1', 'column2'],
        filename='export.csv'
    )
"""

import csv
import io
import logging
from typing import Dict, Generator, Iterable, List, Union

from django.http import StreamingHttpResponse

logger = logging.getLogger(__name__)


class Echo:
    """
    A file-like object that implements just the write method.

    Used by csv.writer to write rows that can be yielded immediately
    without buffering. This is the recommended approach from Django docs
    for streaming large CSV files.
    """

    def write(self, value: str) -> str:
        """Return the value that was written (for streaming)."""
        return value


class StreamingCSVGenerator:
    """
    Generator that yields CSV rows as strings for streaming.

    This class handles the conversion of dictionaries or lists to CSV format,
    yielding each row immediately for streaming response.
    """

    def __init__(
        self,
        row_generator: Union[Generator[Dict, None, None], Iterable[Dict]],
        fieldnames: List[str],
        include_header: bool = True,
    ):
        """
        Initialize the streaming CSV generator.

        Args:
            row_generator: An iterable or generator that yields dictionaries
                          with keys matching fieldnames.
            fieldnames: List of column names for the CSV header.
            include_header: Whether to include header row (default True).
        """
        self.row_generator = row_generator
        self.fieldnames = fieldnames
        self.include_header = include_header

    def __iter__(self) -> Generator[str, None, None]:
        """
        Iterate over CSV rows, yielding each as a string.

        Yields:
            CSV-formatted strings for each row (including header if enabled).
        """
        pseudo_buffer = Echo()
        writer = csv.DictWriter(
            pseudo_buffer,
            fieldnames=self.fieldnames,
            extrasaction="ignore",  # Ignore extra keys in row dicts
        )

        # Yield header row
        if self.include_header:
            yield writer.writerow(dict(zip(self.fieldnames, self.fieldnames)))

        # Yield data rows
        row_count = 0
        for row in self.row_generator:
            try:
                yield writer.writerow(row)
                row_count += 1
            except Exception as e:
                logger.exception("Error writing CSV row %d: %s", row_count, e)
                # Continue processing other rows rather than failing entirely
                continue

        logger.debug("Streamed %d CSV rows", row_count)


class StreamingCSVResponse(StreamingHttpResponse):
    """
    A StreamingHttpResponse configured for CSV file downloads.

    This response streams CSV data incrementally, which:
    - Reduces memory usage for large exports
    - Prevents request timeouts by sending data continuously
    - Allows the client to start receiving data immediately
    """

    def __init__(
        self,
        row_generator: Union[Generator[Dict, None, None], Iterable[Dict]],
        fieldnames: List[str],
        filename: str,
        include_header: bool = True,
        **kwargs,
    ):
        """
        Initialize the streaming CSV response.

        Args:
            row_generator: An iterable or generator that yields dictionaries
                          with keys matching fieldnames.
            fieldnames: List of column names for the CSV header.
            filename: The filename for the downloaded file.
            include_header: Whether to include header row (default True).
            **kwargs: Additional arguments passed to StreamingHttpResponse.
        """
        csv_generator = StreamingCSVGenerator(
            row_generator=row_generator,
            fieldnames=fieldnames,
            include_header=include_header,
        )

        super().__init__(
            streaming_content=csv_generator,
            content_type="text/csv",
            **kwargs,
        )

        # Sanitize filename to prevent header injection (CR/LF).
        safe_filename = filename.replace("\r", "").replace("\n", "").replace('"', "")

        # Set headers for file download.
        # NOTE: filename is intentionally unquoted to match the existing API
        # contract that the frontend's Content-Disposition parser expects.
        self["Content-Disposition"] = f"attachment; filename={safe_filename}"
        self["x-das-download-filename"] = safe_filename


def generate_csv_string(
    rows: Iterable[Dict],
    fieldnames: List[str],
) -> str:
    """
    Generate a complete CSV string from rows (non-streaming).

    This is useful for testing or small datasets where streaming isn't needed.

    Args:
        rows: Iterable of dictionaries with keys matching fieldnames.
        fieldnames: List of column names for the CSV header.

    Returns:
        Complete CSV content as a string.
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def read_streaming_response_content(response) -> str:
    """
    Read the full content from a response, handling both streaming and regular responses.

    This is primarily useful for testing streaming responses.

    Args:
        response: A StreamingHttpResponse or HttpResponse to read from.

    Returns:
        The complete response content as a string.
    """
    # Handle regular HttpResponse (has .content attribute)
    if hasattr(response, "content") and not hasattr(response, "streaming_content"):
        content = response.content
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content

    # Handle StreamingHttpResponse
    content_parts = []
    for chunk in response.streaming_content:
        if isinstance(chunk, bytes):
            content_parts.append(chunk.decode("utf-8"))
        else:
            content_parts.append(chunk)
    return "".join(content_parts)

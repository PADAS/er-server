"""Unit tests for GCS resumable upload helper (ERA-9210). Mock GCS; no real network."""

from unittest.mock import MagicMock, patch

import pytest

from core import resumable_upload


class TestResumableUploadInitiate:
    @patch("core.resumable_upload._session")
    def test_initiate_returns_location_uri(self, mock_session):
        mock_session.return_value.post.return_value.headers = {"Location": "https://upload.example/session/123"}
        mock_session.return_value.post.return_value.raise_for_status = MagicMock()

        uri = resumable_upload.initiate("tenant/file_uploads/2025/2/26/abc/doc.pdf", 1000)

        assert uri == "https://upload.example/session/123"
        call_kw = mock_session.return_value.post.call_args[1]
        assert "X-Upload-Content-Length" in call_kw["headers"]
        assert call_kw["headers"]["X-Upload-Content-Length"] == "1000"

    @patch("core.resumable_upload._session")
    def test_initiate_no_location_raises(self, mock_session):
        mock_session.return_value.post.return_value.headers = {}
        mock_session.return_value.post.return_value.raise_for_status = MagicMock()

        with pytest.raises(RuntimeError, match="Location"):
            resumable_upload.initiate("path/to/file", 100)


class TestResumableUploadChunk:
    @patch("core.resumable_upload._session")
    def test_upload_chunk_sends_content_range(self, mock_session):
        mock_session.return_value.put.return_value.status_code = 308

        resumable_upload.upload_chunk("https://upload.example/session/1", b"abc", 0, 10)

        call_kw = mock_session.return_value.put.call_args[1]
        assert call_kw["headers"]["Content-Range"] == "bytes 0-2/10"
        assert call_kw["data"] == b"abc"

    @patch("core.resumable_upload._session")
    def test_upload_chunk_200_completes(self, mock_session):
        mock_session.return_value.put.return_value.status_code = 200

        resumable_upload.upload_chunk("https://upload.example/s", b"final", 5, 10)
        # no raise
        mock_session.return_value.put.assert_called_once()

    @patch("core.resumable_upload._session")
    def test_upload_chunk_bad_status_raises(self, mock_session):
        mock_session.return_value.put.return_value.status_code = 400

        with pytest.raises(RuntimeError, match="400"):
            resumable_upload.upload_chunk("https://upload.example/s", b"x", 0, 1)


class TestResumableUploadFinalize:
    @patch("core.resumable_upload._session")
    def test_finalize_sends_bytes_star_total(self, mock_session):
        mock_session.return_value.put.return_value.status_code = 200

        resumable_upload.finalize("https://upload.example/s", 100)

        call_kw = mock_session.return_value.put.call_args[1]
        assert call_kw["headers"]["Content-Range"] == "bytes */100"
        assert call_kw["data"] == b""

    @patch("core.resumable_upload._session")
    def test_finalize_bad_status_raises(self, mock_session):
        mock_session.return_value.put.return_value.status_code = 403

        with pytest.raises(RuntimeError, match="403"):
            resumable_upload.finalize("https://upload.example/s", 100)

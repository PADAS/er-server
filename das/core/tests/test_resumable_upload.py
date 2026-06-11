"""Unit tests for GCS resumable upload helper (ERA-9210). Mock GCS; no real network."""

from unittest.mock import MagicMock, patch

import pytest

from django.test import override_settings

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

    @patch("core.resumable_upload._session")
    def test_upload_chunk_final_chunk_308_raises(self, mock_session):
        """GCS must return 200/201 when the last byte is uploaded; 308 means incomplete."""
        mock_session.return_value.put.return_value.status_code = 308

        with pytest.raises(RuntimeError, match="final chunk returned 308"):
            resumable_upload.upload_chunk("https://upload.example/s", b"abcde", 5, 10)

    @patch("core.resumable_upload._session")
    def test_upload_chunk_non_final_308_succeeds(self, mock_session):
        mock_session.return_value.put.return_value.status_code = 308

        resumable_upload.upload_chunk("https://upload.example/s", b"abcde", 0, 10)

        call_kw = mock_session.return_value.put.call_args[1]
        assert call_kw["headers"]["Content-Range"] == "bytes 0-4/10"


class TestResumableUploadAbort:
    @patch("core.resumable_upload._session")
    def test_abort_issues_delete_to_uri(self, mock_session):
        mock_session.return_value.delete.return_value.status_code = 499

        resumable_upload.abort("https://upload.example/session/abc")

        mock_session.return_value.delete.assert_called_once_with("https://upload.example/session/abc", timeout=120)

    @patch("core.resumable_upload._session")
    def test_abort_treats_499_as_success(self, mock_session):
        """GCS returns 499 on successful session cancellation; must not raise."""
        mock_session.return_value.delete.return_value.status_code = 499

        resumable_upload.abort("https://upload.example/session/abc")
        # no raise

    @patch("core.resumable_upload._session")
    def test_abort_unexpected_status_does_not_raise(self, mock_session):
        """Abort failures are non-fatal; unexpected status codes are logged but not raised."""
        mock_session.return_value.delete.return_value.status_code = 503

        resumable_upload.abort("https://upload.example/session/abc")
        # no raise


class TestGetCredentials:
    @patch("google.auth.default")
    def test_uses_ambient_credentials(self, mock_google_auth_default):
        """_get_credentials() must return ambient Workload Identity credentials."""
        fake_creds = MagicMock()
        mock_google_auth_default.return_value = (fake_creds, "test-project")

        result = resumable_upload._get_credentials()

        mock_google_auth_default.assert_called_once_with(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        assert result is fake_creds

    @patch("google.auth.default")
    def test_never_calls_get_impersonated_credentials_when_tenant_storage_configured(self, mock_google_auth_default):
        """Must not call TenantGoogleCloudStorage.get_impersonated_credentials() even when
        DEFAULT_FILE_STORAGE is TenantGoogleCloudStorage.

        ERA-9210 regression guard: self-impersonation requires roles/iam.serviceAccountTokenCreator
        on the pod SA (not granted). The resumable upload API only needs a bearer token, not the
        signing credentials that TenantGoogleCloudStorage.url() uses for signed GCS URLs.
        """
        fake_creds = MagicMock()
        mock_google_auth_default.return_value = (fake_creds, "test-project")

        with override_settings(DEFAULT_FILE_STORAGE="core.storages.TenantGoogleCloudStorage"):
            with patch("core.storages.TenantGoogleCloudStorage") as mock_storage_cls:
                result = resumable_upload._get_credentials()

        assert result is fake_creds
        mock_storage_cls.assert_not_called()

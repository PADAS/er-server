"""API tests for chunked uploads (ERA-9210); GCS calls mocked."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from core.tests import BaseAPITest
from usercontent.models import FileContent, ImageFileContent

User = get_user_model()


class TestChunkedUploadAPI(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.token = self.create_access_token(self.app_user)
        self.client.credentials(HTTP_AUTHORIZATION=self.create_authorization_header(self.token))
        self.base = f"{self.api_base}/usercontent/chunked-uploads"

    @staticmethod
    def _json_data(response):
        """Payload inside ExtendedJSONRenderer envelope ``{\"data\": ..., \"status\": ...}``."""
        return response.json()["data"]

    @patch("usercontent.chunked_upload.resumable_upload.upload_chunk")
    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_full_flow_creates_filecontent(self, _mock_init, mock_upload_chunk):
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "notes.txt", "size": 10, "chunk_size": 10},
            format="json",
        )
        assert r0.status_code == status.HTTP_201_CREATED, r0.content
        body = self._json_data(r0)
        upload_id = body["upload_id"]
        assert body["num_chunks"] == 1

        r1 = self.client.put(
            f"{self.base}/{upload_id}/chunks/0/",
            data=b"0123456789",
            content_type="application/octet-stream",
        )
        # ExtendedJSONRenderer maps 204 No Content to 200 with data: null
        assert r1.status_code == status.HTTP_200_OK
        mock_upload_chunk.assert_called_once()

        r2 = self.client.post(f"{self.base}/{upload_id}/complete/")
        assert r2.status_code == status.HTTP_200_OK, r2.content
        assert FileContent.objects.filter(id=upload_id).exists()

    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_put_chunk_out_of_order(self, _mock_init):
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "a.txt", "size": 20, "chunk_size": 10},
            format="json",
        )
        upload_id = self._json_data(r0)["upload_id"]
        r1 = self.client.put(
            f"{self.base}/{upload_id}/chunks/1/",
            data=b"0123456789",
            content_type="application/octet-stream",
        )
        assert r1.status_code == status.HTTP_400_BAD_REQUEST

    @patch("usercontent.chunked_upload.resumable_upload.upload_chunk")
    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_idempotent_chunk_retry_skips_second_gcs_put(self, _mock_init, mock_upload_chunk):
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "b.txt", "size": 5, "chunk_size": 5},
            format="json",
        )
        upload_id = self._json_data(r0)["upload_id"]
        chunk = b"abcde"
        url = f"{self.base}/{upload_id}/chunks/0/"
        assert self.client.put(url, data=chunk, content_type="application/octet-stream").status_code == 200
        assert self.client.put(url, data=chunk, content_type="application/octet-stream").status_code == 200
        mock_upload_chunk.assert_called_once()

    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_other_user_cannot_upload_chunk(self, _mock_init):
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "c.txt", "size": 5, "chunk_size": 5},
            format="json",
        )
        upload_id = self._json_data(r0)["upload_id"]

        other = User.objects.create_user(
            "other-uploader",
            "other-uploader@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=self.create_authorization_header(self.create_access_token(other)))
        r1 = other_client.put(
            f"{self.base}/{upload_id}/chunks/0/",
            data=b"abcde",
            content_type="application/octet-stream",
        )
        assert r1.status_code == status.HTTP_403_FORBIDDEN

    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_other_user_cannot_get_status(self, _mock_init):
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "status.txt", "size": 5, "chunk_size": 5},
            format="json",
        )
        upload_id = self._json_data(r0)["upload_id"]

        other = User.objects.create_user(
            "other-status",
            "other-status@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=self.create_authorization_header(self.create_access_token(other)))
        r = other_client.get(f"{self.base}/{upload_id}/")
        assert r.status_code == status.HTTP_403_FORBIDDEN

    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_other_user_cannot_complete(self, _mock_init):
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "complete.txt", "size": 5, "chunk_size": 5},
            format="json",
        )
        upload_id = self._json_data(r0)["upload_id"]

        other = User.objects.create_user(
            "other-complete",
            "other-complete@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=self.create_authorization_header(self.create_access_token(other)))
        r = other_client.post(f"{self.base}/{upload_id}/complete/")
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_post_init_returns_401(self):
        anon = APIClient()
        r = anon.post(
            f"{self.base}/",
            {"filename": "anon.txt", "size": 10, "chunk_size": 10},
            format="json",
        )
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_init_rejects_chunk_size_above_django_request_body_limit(self, _mock_init):
        """chunk_size must stay below DATA_UPLOAD_MAX_MEMORY_SIZE (see _effective_max_chunk_bytes)."""
        r = self.client.post(
            f"{self.base}/",
            {"filename": "huge.txt", "size": 10_000_000, "chunk_size": 3 * 1024 * 1024},
            format="json",
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    @patch("usercontent.chunked_upload.resumable_upload.upload_chunk")
    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_full_flow_image_creates_imagefilecontent(self, _mock_init, _mock_chunk):
        """An image filename routes the completed upload to ImageFileContent, not FileContent."""
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "photo.jpg", "size": 5, "chunk_size": 5},
            format="json",
        )
        assert r0.status_code == status.HTTP_201_CREATED, r0.content
        upload_id = self._json_data(r0)["upload_id"]

        self.client.put(
            f"{self.base}/{upload_id}/chunks/0/",
            data=b"abcde",
            content_type="application/octet-stream",
        )

        r2 = self.client.post(f"{self.base}/{upload_id}/complete/")
        assert r2.status_code == status.HTTP_200_OK, r2.content
        payload = self._json_data(r2)
        assert payload["file_type"] == "image"
        assert ImageFileContent.objects.filter(id=upload_id).exists()
        assert not FileContent.objects.filter(id=upload_id).exists()

    @patch("usercontent.chunked_upload.resumable_upload.upload_chunk")
    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_double_complete_second_call_returns_404(self, _mock_init, _mock_chunk):
        """Session is deleted after the first complete; a second call returns 404, not IntegrityError."""
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "d.txt", "size": 5, "chunk_size": 5},
            format="json",
        )
        upload_id = self._json_data(r0)["upload_id"]
        self.client.put(
            f"{self.base}/{upload_id}/chunks/0/",
            data=b"abcde",
            content_type="application/octet-stream",
        )
        r1 = self.client.post(f"{self.base}/{upload_id}/complete/")
        assert r1.status_code == status.HTTP_200_OK
        r2 = self.client.post(f"{self.base}/{upload_id}/complete/")
        assert r2.status_code == status.HTTP_404_NOT_FOUND

    @patch(
        "usercontent.chunked_upload.resumable_upload.initiate", side_effect=RuntimeError("internal bucket/path detail")
    )
    def test_init_storage_error_returns_client_safe_payload(self, _mock_init):
        r = self.client.post(
            f"{self.base}/",
            {"filename": "x.txt", "size": 100, "chunk_size": 100},
            format="json",
        )
        assert r.status_code == status.HTTP_502_BAD_GATEWAY
        payload = self._json_data(r)
        assert "error_id" in payload
        assert "reason" not in payload
        assert "bucket" not in str(payload)

    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_init_sets_force_download_metadata_for_svg(self, mock_init):
        """SVG (and any USERCONTENT_SETTINGS.force_download_mimetypes type) uploads must be
        initiated with Content-Type=application/octet-stream and Content-Disposition=attachment
        so that direct GCS fetches cannot render active content inline (XSS defense).
        """
        r = self.client.post(
            f"{self.base}/",
            {"filename": "logo.svg", "size": 10, "chunk_size": 10},
            format="json",
        )
        assert r.status_code == status.HTTP_201_CREATED, r.content
        _, kwargs = mock_init.call_args
        assert kwargs["content_type"] == "application/octet-stream"
        assert kwargs["content_disposition"] == "attachment"

    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_init_does_not_set_force_download_metadata_for_safe_types(self, mock_init):
        """Plain types (e.g. .txt, .pdf) must not get the force-download override."""
        r = self.client.post(
            f"{self.base}/",
            {"filename": "notes.txt", "size": 10, "chunk_size": 10},
            format="json",
        )
        assert r.status_code == status.HTTP_201_CREATED, r.content
        _, kwargs = mock_init.call_args
        assert kwargs["content_type"] is None
        assert kwargs["content_disposition"] is None

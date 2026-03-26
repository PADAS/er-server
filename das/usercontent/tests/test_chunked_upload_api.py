"""API tests for chunked uploads (ERA-9210); GCS calls mocked."""

from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

from core.tests import BaseAPITest
from usercontent.models import FileContent

User = get_user_model()


class TestChunkedUploadAPI(BaseAPITest):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.token = self.create_access_token(self.app_user)
        self.client.credentials(HTTP_AUTHORIZATION=self.create_authorization_header(self.token))
        self.base = f"{self.api_base}/usercontent/chunked-uploads"

    @patch("usercontent.chunked_upload.resumable_upload.upload_chunk")
    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_full_flow_creates_filecontent(self, _mock_init, mock_upload_chunk):
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "notes.txt", "size": 10, "chunk_size": 10},
            format="json",
        )
        assert r0.status_code == status.HTTP_201_CREATED, r0.content
        body = r0.json()
        upload_id = body["upload_id"]
        assert body["num_chunks"] == 1

        r1 = self.client.put(
            f"{self.base}/{upload_id}/chunks/0/",
            data=b"0123456789",
            content_type="application/octet-stream",
        )
        assert r1.status_code == status.HTTP_204_NO_CONTENT
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
        upload_id = r0.json()["upload_id"]
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
        upload_id = r0.json()["upload_id"]
        chunk = b"abcde"
        url = f"{self.base}/{upload_id}/chunks/0/"
        assert self.client.put(url, data=chunk, content_type="application/octet-stream").status_code == 204
        assert self.client.put(url, data=chunk, content_type="application/octet-stream").status_code == 204
        mock_upload_chunk.assert_called_once()

    @patch("usercontent.chunked_upload.resumable_upload.initiate", return_value="https://gcs.example/resumable")
    def test_other_user_cannot_upload_chunk(self, _mock_init):
        r0 = self.client.post(
            f"{self.base}/",
            {"filename": "c.txt", "size": 5, "chunk_size": 5},
            format="json",
        )
        upload_id = r0.json()["upload_id"]

        other = User.objects.create_user(
            "other-uploader",
            "other-uploader@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )
        other_client = APIClient()
        other_client.credentials(
            HTTP_AUTHORIZATION=self.create_authorization_header(self.create_access_token(other))
        )
        r1 = other_client.put(
            f"{self.base}/{upload_id}/chunks/0/",
            data=b"abcde",
            content_type="application/octet-stream",
        )
        assert r1.status_code == status.HTTP_403_FORBIDDEN

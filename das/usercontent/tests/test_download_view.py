"""Tests for UserContentDownloadView (ERA-13273).

GCS / storage calls are mocked so tests never touch real storage.

The download endpoint uses tenant-scoped lookup (resolve_usercontent_for_tenant) with
no per-user filtering, so any authenticated user in the tenant can download a file by
UUID regardless of who uploaded it.  Tenant isolation via CommonTenantManager makes
cross-tenant UUIDs 404.  Access control therefore rests on UUID unguessability plus
tenant scope, not on per-user ownership.
"""

from __future__ import annotations

import io
import uuid
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

from core.models import DASTenant
from core.tests import BaseAPITest
from usercontent.models import FileContent, ImageFileContent

User = get_user_model()


def _insert_filecontent(*, user: User, filename: str = "report.pdf") -> FileContent:
    """Insert a FileContent row bypassing GCS upload."""
    uid = uuid.uuid4()
    fc = FileContent(id=uid, filename=filename, created_by=user)
    fc.file.name = f"tenant/file_uploads/2024/1/1/{uid}/{filename}"
    FileContent.objects.bulk_create([fc])
    return FileContent.objects.get(id=uid)


def _insert_imagefilecontent(*, user: User, filename: str = "photo.jpg") -> ImageFileContent:
    """Insert an ImageFileContent row bypassing GCS upload."""
    uid = uuid.uuid4()
    ifc = ImageFileContent(id=uid, filename=filename, created_by=user)
    ifc.file.name = f"tenant/image_fileuploads/2024/1/1/{uid}/{filename}"
    ImageFileContent.objects.bulk_create([ifc])
    return ImageFileContent.objects.get(id=uid)


class TestUserContentDownloadView(BaseAPITest):
    """Tests for GET /api/v1.0/usercontent/<uuid>/"""

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.token = self.create_access_token(self.app_user)
        self.client.credentials(HTTP_AUTHORIZATION=self.create_authorization_header(self.token))
        self.base = f"{self.api_base}/usercontent"

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def test_download_requires_authentication(self) -> None:
        """Anonymous requests must receive 401."""
        anon = APIClient()
        r = anon.get(f"{self.base}/{uuid.uuid4()}/")
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    # ------------------------------------------------------------------
    # Happy path — FileContent (non-image)
    # ------------------------------------------------------------------

    def test_download_filecontent_streams_bytes_200(self) -> None:
        fc = _insert_filecontent(user=self.app_user, filename="notes.pdf")
        fake_fp = io.BytesIO(b"PDF content here")
        with patch.object(fc.__class__.file.field.storage, "open", return_value=fake_fp):
            r = self.client.get(f"{self.base}/{fc.id}/")
        assert r.status_code == status.HTTP_200_OK
        assert "application/pdf" in r["Content-Type"]
        assert 'filename="notes.pdf"' in r["Content-Disposition"]
        assert b"PDF content here" in b"".join(r.streaming_content)

    # ------------------------------------------------------------------
    # Happy path — ImageFileContent
    # ------------------------------------------------------------------

    def test_download_imagefilecontent_streams_bytes_200(self) -> None:
        ifc = _insert_imagefilecontent(user=self.app_user, filename="photo.jpg")
        fake_fp = io.BytesIO(b"\xff\xd8\xff" * 4)
        with patch.object(ifc.__class__.file.field.storage, "open", return_value=fake_fp):
            r = self.client.get(f"{self.base}/{ifc.id}/")
        assert r.status_code == status.HTTP_200_OK
        assert "image/jpeg" in r["Content-Type"]

    # ------------------------------------------------------------------
    # Tenant-scoped download (any teammate in the tenant)
    # ------------------------------------------------------------------

    def test_download_allows_tenant_teammate_who_did_not_upload(self) -> None:
        """User B (same tenant) can download a file uploaded by user A."""
        other_uploader = User.objects.create_user(
            "dl-uploader",
            "dl-uploader@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )
        fc = _insert_filecontent(user=other_uploader, filename="shared_report.pdf")
        fake_fp = io.BytesIO(b"shared content")
        with patch.object(fc.__class__.file.field.storage, "open", return_value=fake_fp):
            # self.app_user (different user) downloads the file uploaded by other_uploader
            r = self.client.get(f"{self.base}/{fc.id}/")
        assert r.status_code == status.HTTP_200_OK

    def test_download_blocks_cross_tenant_access(self) -> None:
        """A finalized FileContent row from another tenant is invisible (404) to the current tenant."""
        other_tenant_id = uuid.uuid4()
        other_das_tenant = DASTenant.objects.create(
            id=other_tenant_id,
            domain=f"other-{other_tenant_id.hex[:12]}.example.com",
        )
        uid = uuid.uuid4()
        fc = FileContent(id=uid, filename="secret.pdf", created_by=self.app_user, das_tenant=other_das_tenant)
        fc.file.name = f"other/file_uploads/2024/1/1/{uid}/secret.pdf"
        # bulk_create bypasses save()/clean() so the row lands in the DB with
        # das_tenant pointing to the other tenant, invisible to the current tenant's manager.
        FileContent.objects.bulk_create([fc])

        r = self.client.get(f"{self.base}/{uid}/")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    # ------------------------------------------------------------------
    # 404 — unknown UUID
    # ------------------------------------------------------------------

    def test_unknown_uuid_returns_404(self) -> None:
        r = self.client.get(f"{self.base}/{uuid.uuid4()}/")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    # ------------------------------------------------------------------
    # 404 — GCS open failure must not 500
    # ------------------------------------------------------------------

    def test_gcs_open_failure_returns_404_not_500(self) -> None:
        fc = _insert_filecontent(user=self.app_user, filename="broken.pdf")
        with patch.object(fc.__class__.file.field.storage, "open", side_effect=Exception("network error")):
            r = self.client.get(f"{self.base}/{fc.id}/")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    # ------------------------------------------------------------------
    # Unicode filename in Content-Disposition
    # ------------------------------------------------------------------

    def test_unicode_filename_in_content_disposition(self) -> None:
        fc = _insert_filecontent(user=self.app_user, filename="résumé.pdf")
        fake_fp = io.BytesIO(b"data")
        with patch.object(fc.__class__.file.field.storage, "open", return_value=fake_fp):
            r = self.client.get(f"{self.base}/{fc.id}/")
        assert r.status_code == status.HTTP_200_OK
        # Django 4.2's content_disposition_header emits filename*=UTF-8''<percent-encoded>
        # for non-ASCII filenames (RFC 6266 §5).
        assert "filename*=UTF-8''r%C3%A9sum%C3%A9.pdf" in r["Content-Disposition"]

    # ------------------------------------------------------------------
    # 404 — cross-tenant: ImageFileContent from another tenant is invisible
    # ------------------------------------------------------------------

    def test_other_tenant_imagefilecontent_returns_404(self) -> None:
        """An ImageFileContent row created under a different tenant is invisible to
        resolve_usercontent_for_tenant, which uses the tenant-scoped ORM manager."""
        other_tenant_id = uuid.uuid4()
        other_das_tenant = DASTenant.objects.create(
            id=other_tenant_id,
            domain=f"other-img-{other_tenant_id.hex[:12]}.example.com",
        )
        uid = uuid.uuid4()
        ifc = ImageFileContent(id=uid, filename="secret.jpg", created_by=self.app_user, das_tenant=other_das_tenant)
        ifc.file.name = f"other/image_fileuploads/2024/1/1/{uid}/secret.jpg"
        ImageFileContent.objects.bulk_create([ifc])

        r = self.client.get(f"{self.base}/{uid}/")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    # ------------------------------------------------------------------
    # XSS defense — active MIME types must be forced to download
    # ------------------------------------------------------------------

    def test_download_svg_forces_attachment_and_octet_stream(self) -> None:
        """SVG files must be served as application/octet-stream attachments to
        prevent browsers from rendering active content inline under the app origin."""
        fc = _insert_filecontent(user=self.app_user, filename="logo.svg")
        fake_fp = io.BytesIO(b"<svg><script>alert(1)</script></svg>")
        with patch.object(fc.__class__.file.field.storage, "open", return_value=fake_fp):
            r = self.client.get(f"{self.base}/{fc.id}/")
        assert r.status_code == status.HTTP_200_OK
        assert "application/octet-stream" in r["Content-Type"]
        assert "attachment" in r["Content-Disposition"]
        assert r["X-Content-Type-Options"] == "nosniff"

    def test_download_sets_nosniff_header(self) -> None:
        """X-Content-Type-Options: nosniff must be present on all responses,
        including the inline (non-forced) path for safe types such as PDF."""
        fc = _insert_filecontent(user=self.app_user, filename="notes.pdf")
        fake_fp = io.BytesIO(b"PDF content here")
        with patch.object(fc.__class__.file.field.storage, "open", return_value=fake_fp):
            r = self.client.get(f"{self.base}/{fc.id}/")
        assert r.status_code == status.HTTP_200_OK
        assert r["X-Content-Type-Options"] == "nosniff"
        assert "attachment" not in r["Content-Disposition"]
        assert 'filename="notes.pdf"' in r["Content-Disposition"]

    # ------------------------------------------------------------------
    # Rendition serving (?rendition=<name>) — images only
    # ------------------------------------------------------------------

    def test_download_image_rendition_streams_bytes_200(self) -> None:
        """Each configured non-original rendition streams its stored bytes for an image."""
        ifc = _insert_imagefilecontent(user=self.app_user, filename="photo.jpg")
        for rendition in ("icon", "thumbnail", "large", "xlarge"):
            fake_fp = io.BytesIO(b"RENDITION-BYTES")
            with (
                patch(
                    "usercontent.views.get_stored_filename",
                    return_value=f"tenant/image_fileuploads/2024/1/1/{ifc.id}/photo__{rendition}.jpg",
                ),
                patch.object(ifc.__class__.file.field.storage, "open", return_value=fake_fp),
            ):
                r = self.client.get(f"{self.base}/{ifc.id}/?rendition={rendition}")
            assert r.status_code == status.HTTP_200_OK, rendition
            assert b"RENDITION-BYTES" in b"".join(r.streaming_content)

    def test_rendition_param_on_non_image_returns_404(self) -> None:
        """A non-image FileContent has no renditions; a rendition request returns 404."""
        fc = _insert_filecontent(user=self.app_user, filename="notes.pdf")
        r = self.client.get(f"{self.base}/{fc.id}/?rendition=thumbnail")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    def test_unknown_rendition_name_returns_404(self) -> None:
        """An unknown rendition name returns 404 even for an image."""
        ifc = _insert_imagefilecontent(user=self.app_user, filename="photo.jpg")
        r = self.client.get(f"{self.base}/{ifc.id}/?rendition=bogus")
        assert r.status_code == status.HTTP_404_NOT_FOUND

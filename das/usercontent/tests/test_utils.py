"""Tests for usercontent.utils (ERA-13273)."""

from __future__ import annotations

import uuid

import pytest

from django.conf import settings
from django.contrib.auth import get_user_model

import utils.tenant.thread as _thread_mod
from core.tests import BaseAPITest
from usercontent import upload_sessions
from usercontent.models import FileContent, ImageFileContent
from usercontent.utils import (
    AttachmentInfo,
    classify_file_type,
    get_attachment_info,
    guess_content_type,
    resolve_attachment_filename_for_user,
    resolve_usercontent_for_tenant,
    resolve_usercontent_for_user,
)
from utils.tenant.thread import get_tenant_settings

USERCONTENT_SETTINGS = getattr(settings, "USERCONTENT_SETTINGS", {})
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(USERCONTENT_SETTINGS.get("allowed_extensions", ()))


def _insert_filecontent(*, user, filename: str = "doc.pdf") -> FileContent:
    uid = uuid.uuid4()
    fc = FileContent(id=uid, filename=filename, created_by=user)
    fc.file.name = f"tenant/file_uploads/2024/1/1/{uid}/{filename}"
    FileContent.objects.bulk_create([fc])
    return FileContent.objects.get(id=uid)


def _insert_imagefilecontent(*, user, filename: str = "photo.jpg") -> ImageFileContent:
    uid = uuid.uuid4()
    ifc = ImageFileContent(id=uid, filename=filename, created_by=user)
    ifc.file.name = f"tenant/image_fileuploads/2024/1/1/{uid}/{filename}"
    ImageFileContent.objects.bulk_create([ifc])
    return ImageFileContent.objects.get(id=uid)


class TestClassifyFileType:
    """Tests for classify_file_type()."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("song.mp3", "audio"),
            ("clip.wav", "audio"),
            ("clip.aac", "audio"),
            ("voice.ogg", "audio"),
            ("sound.flac", "audio"),
            ("track.m4a", "audio"),
            ("speech.opus", "audio"),
            ("notes.pdf", "document"),
            ("report.doc", "document"),
            ("report.docx", "document"),
            ("sheet.xls", "document"),
            ("sheet.xlsx", "document"),
            ("data.csv", "document"),
            ("deck.ppt", "document"),
            ("deck.pptx", "document"),
            ("text.txt", "document"),
            ("rich.rtf", "document"),
            ("image.jpg", "image"),
            ("image.jpeg", "image"),
            ("image.png", "image"),
            ("image.gif", "image"),
            ("image.tif", "image"),
            ("image.tiff", "image"),
            ("image.webp", "image"),
            ("image.heic", "image"),
            ("image.bmp", "image"),
            ("image.svg", "image"),
            ("clip.mp4", "video"),
            ("clip.mov", "video"),
            ("clip.avi", "video"),
            ("clip.mkv", "video"),
            ("clip.wmv", "video"),
            ("clip.webm", "video"),
            ("clip.m4v", "video"),
            ("clip.3gp", "video"),
        ],
    )
    def test_known_extensions(self, filename: str, expected: str) -> None:
        assert classify_file_type(filename) == expected

    def test_unknown_extension_returns_none(self) -> None:
        assert classify_file_type("archive.xyz") is None

    def test_no_extension_returns_none(self) -> None:
        assert classify_file_type("noextension") is None

    @pytest.mark.parametrize("filename", ["Song.MP3", "Photo.JPG", "Report.PDF"])
    def test_case_insensitive(self, filename: str) -> None:
        result = classify_file_type(filename)
        assert result is not None, f"Expected a non-None bucket for {filename}"


class TestGuessContentType:
    """Tests for guess_content_type()."""

    def test_pdf_returns_application_pdf(self) -> None:
        assert guess_content_type("doc.pdf") == "application/pdf"

    def test_jpg_returns_image_jpeg(self) -> None:
        assert "image" in guess_content_type("photo.jpg")

    def test_unknown_extension_returns_octet_stream(self) -> None:
        # .qqq is not registered in any standard MIME database
        assert guess_content_type("mystery.qqq") == "application/octet-stream"

    def test_no_extension_returns_octet_stream(self) -> None:
        assert guess_content_type("noext") == "application/octet-stream"


class TestResolveUsercontentForUser(BaseAPITest):
    """Tests for resolve_usercontent_for_user()."""

    def test_returns_filecontent_for_owner(self) -> None:
        fc = _insert_filecontent(user=self.app_user)
        result = resolve_usercontent_for_user(fc.id, self.app_user)
        assert result is not None
        assert result.id == fc.id
        assert isinstance(result, FileContent)

    def test_returns_imagefilecontent_for_owner(self) -> None:
        ifc = _insert_imagefilecontent(user=self.app_user)
        result = resolve_usercontent_for_user(ifc.id, self.app_user)
        assert result is not None
        assert result.id == ifc.id
        assert isinstance(result, ImageFileContent)

    def test_returns_none_for_other_user(self) -> None:
        other = self._create_other_user()
        fc = _insert_filecontent(user=other)
        result = resolve_usercontent_for_user(fc.id, self.app_user)
        assert result is None

    def test_returns_none_for_unknown_id(self) -> None:
        result = resolve_usercontent_for_user(uuid.uuid4(), self.app_user)
        assert result is None

    def _create_other_user(self):
        U = get_user_model()
        return U.objects.create_user(
            "util-other",
            "util-other@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestResolveAttachmentFilenameForUser:
    """Tests for resolve_attachment_filename_for_user()."""

    @pytest.fixture(autouse=True)
    def _setup_users(self, admin_user, tenant_settings) -> None:
        self.user = admin_user
        self.tenant_id = str(get_tenant_settings().id)

    def _create_other_user(self):
        U = get_user_model()
        suffix = uuid.uuid4().hex[:8]
        return U.objects.create_user(
            f"raf-other-{suffix}",
            f"raf-other-{suffix}@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )

    def _make_session(
        self,
        *,
        upload_id: str | None = None,
        filename: str = "upload.jpg",
        user_id: str | None = None,
    ) -> str:
        uid = upload_id or str(uuid.uuid4())
        upload_sessions.create(
            self.tenant_id,
            uid,
            storage_path=f"tenant/image_fileuploads/2024/1/1/{uid}/{filename}",
            filename=filename,
            size=1024,
            chunk_size=512,
            user_id=user_id or str(self.user.pk),
            is_image=True,
            file_content_id=uid,
        )
        return uid

    def test_returns_filename_for_owned_session(self) -> None:
        uid = self._make_session(filename="photo.jpg")
        result = resolve_attachment_filename_for_user(uid, self.user)
        assert result == "photo.jpg"

    def test_returns_filename_for_finalized_db_row(self) -> None:
        fc = _insert_filecontent(user=self.user, filename="doc.pdf")
        result = resolve_attachment_filename_for_user(fc.id, self.user)
        assert result == "doc.pdf"

    def test_returns_none_for_unknown_id(self) -> None:
        result = resolve_attachment_filename_for_user(str(uuid.uuid4()), self.user)
        assert result is None

    def test_returns_none_for_session_owned_by_other_user(self) -> None:
        other = self._create_other_user()
        uid = self._make_session(user_id=str(other.pk), filename="secret.jpg")
        result = resolve_attachment_filename_for_user(uid, self.user)
        assert result is None

    def test_session_in_different_tenant_is_not_visible(self) -> None:
        """A session created under a different tenant is invisible to the current one.

        Tenant isolation in the upload-session store comes from the KEY_FUNCTION
        (utils.tenant.cache.make_cache_key), which embeds the thread-local tenant ID
        in every Redis/LocMem key at the moment of the cache call.  Patching
        ``get_tenant_settings`` on the module is not sufficient because
        ``make_cache_key`` imports the function directly and therefore bypasses a
        module-attribute patch.  The correct approach is to mutate
        ``_local_thread.tenant_object`` directly — this is the same object that
        ``_get_local_thread()`` returns, so both ``get_tenant_settings()`` and
        ``make_cache_key`` see the same value.
        """
        import dataclasses

        other_tenant_id = uuid.uuid4()
        uid = str(uuid.uuid4())

        # Build an alternative Tenant dataclass with a different ID.
        current_tenant = _thread_mod.get_tenant_settings()
        other_tenant = dataclasses.replace(current_tenant, id=other_tenant_id)

        # Temporarily swap the thread-local tenant so that make_cache_key prefixes
        # the session key with other_tenant_id.
        local_thread = _thread_mod._get_local_thread()
        setattr(local_thread, _thread_mod.TENANT_DEFAULT_KEY, other_tenant)
        try:
            upload_sessions.create(
                str(other_tenant_id),
                uid,
                storage_path=f"other/path/{uid}/other.jpg",
                filename="other.jpg",
                size=512,
                chunk_size=256,
                user_id=str(self.user.pk),
                is_image=True,
                file_content_id=uid,
            )
        finally:
            # Restore the primary tenant so subsequent cache calls use the correct key.
            setattr(local_thread, _thread_mod.TENANT_DEFAULT_KEY, current_tenant)

        # Under the primary tenant, the session stored under other_tenant_id is invisible.
        result = resolve_attachment_filename_for_user(uid, self.user)
        assert result is None

    def test_finalized_db_row_not_visible_for_other_user(self) -> None:
        other = self._create_other_user()
        fc = _insert_filecontent(user=other, filename="others.pdf")
        result = resolve_attachment_filename_for_user(fc.id, self.user)
        assert result is None


class TestResolveUsercontentForTenant(BaseAPITest):
    """Tests for resolve_usercontent_for_tenant() — tenant-scoped, no user filter."""

    def _create_other_user(self):
        U = get_user_model()
        return U.objects.create_user(
            "tenant-other",
            "tenant-other@test.com",
            "x",
            last_name="l",
            first_name="f",
            is_staff=True,
        )

    def test_returns_filecontent_owned_by_self(self) -> None:
        fc = _insert_filecontent(user=self.app_user)
        result = resolve_usercontent_for_tenant(fc.id)
        assert result is not None
        assert result.id == fc.id

    def test_returns_filecontent_owned_by_other_user_in_same_tenant(self) -> None:
        """Unlike resolve_usercontent_for_user, no user filter is applied."""
        other = self._create_other_user()
        fc = _insert_filecontent(user=other)
        result = resolve_usercontent_for_tenant(fc.id)
        assert result is not None
        assert result.id == fc.id

    def test_returns_imagefilecontent_when_only_image_row_exists(self) -> None:
        ifc = _insert_imagefilecontent(user=self.app_user)
        result = resolve_usercontent_for_tenant(ifc.id)
        assert result is not None
        assert result.id == ifc.id
        assert isinstance(result, ImageFileContent)

    def test_returns_none_for_unknown_id(self) -> None:
        result = resolve_usercontent_for_tenant(uuid.uuid4())
        assert result is None


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestGetAttachmentInfo:
    """Tests for get_attachment_info() — resolves status/file_type for a UUID."""

    @pytest.fixture(autouse=True)
    def _setup_user(self, admin_user, tenant_settings) -> None:
        self.user = admin_user
        self.tenant_id = str(get_tenant_settings().id)

    def test_returns_complete_for_finalized_image_row(self) -> None:
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        info = get_attachment_info(str(ifc.id))
        assert info.status == "complete"
        assert info.file_type == "image"
        assert info.filename == "photo.jpg"

    def test_returns_complete_for_finalized_file_row(self) -> None:
        fc = _insert_filecontent(user=self.user, filename="notes.pdf")
        info = get_attachment_info(str(fc.id))
        assert info.status == "complete"
        assert info.file_type == "document"

    def test_returns_in_progress_for_live_session(self) -> None:
        uid = str(uuid.uuid4())
        upload_sessions.create(
            self.tenant_id,
            uid,
            storage_path=f"tenant/image_fileuploads/2024/1/1/{uid}/photo.jpg",
            filename="photo.jpg",
            size=1024,
            chunk_size=512,
            user_id=str(self.user.pk),
            is_image=True,
            file_content_id=uid,
        )
        info = get_attachment_info(uid)
        assert info.status == "in_progress"
        assert info.file_type == "image"

    def test_returns_unknown_for_missing_uuid(self) -> None:
        info = get_attachment_info(str(uuid.uuid4()))
        assert info.status == "unknown"
        assert info.file_type is None
        assert info.filename is None

    def test_complete_takes_precedence_over_session(self) -> None:
        """If both a DB row and a Redis session exist, the DB row (complete) wins."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        uid = str(ifc.id)
        # Also seed a session for the same UUID (shouldn't normally happen, but defensive)
        upload_sessions.create(
            self.tenant_id,
            uid,
            storage_path=f"tenant/image_fileuploads/2024/1/1/{uid}/photo.jpg",
            filename="photo.jpg",
            size=1024,
            chunk_size=512,
            user_id=str(self.user.pk),
            is_image=True,
            file_content_id=uid,
        )
        info = get_attachment_info(uid)
        assert info.status == "complete"

    def test_attachment_info_is_dataclass(self) -> None:
        info = get_attachment_info(str(uuid.uuid4()))
        assert isinstance(info, AttachmentInfo)

    def test_has_renditions_true_for_imagefilecontent(self) -> None:
        """has_renditions is True when the stored instance is ImageFileContent."""
        ifc = _insert_imagefilecontent(user=self.user, filename="photo.jpg")
        info = get_attachment_info(str(ifc.id))
        assert info.has_renditions is True

    def test_has_renditions_false_for_filecontent(self) -> None:
        """has_renditions is False when the stored instance is plain FileContent."""
        fc = _insert_filecontent(user=self.user, filename="doc.pdf")
        info = get_attachment_info(str(fc.id))
        assert info.has_renditions is False

    def test_has_renditions_false_for_webp_stored_as_filecontent(self) -> None:
        """A .webp row stored as FileContent (not ImageFileContent) has has_renditions=False.

        webp appears in image_extensions (file_type="image") but not in imagefile_extensions,
        so it is stored as plain FileContent and cannot serve renditions.
        """
        fc = _insert_filecontent(user=self.user, filename="photo.webp")
        info = get_attachment_info(str(fc.id))
        assert info.file_type == "image"
        assert info.has_renditions is False

    def test_has_renditions_false_for_in_progress_session(self) -> None:
        """has_renditions is False for an in-progress upload session (no DB row yet)."""
        uid = str(uuid.uuid4())
        upload_sessions.create(
            self.tenant_id,
            uid,
            storage_path=f"tenant/image_fileuploads/2024/1/1/{uid}/photo.jpg",
            filename="photo.jpg",
            size=1024,
            chunk_size=512,
            user_id=str(self.user.pk),
            is_image=True,
            file_content_id=uid,
        )
        info = get_attachment_info(uid)
        assert info.has_renditions is False

    def test_has_renditions_false_for_unknown_uuid(self) -> None:
        """has_renditions is False for an unknown UUID."""
        info = get_attachment_info(str(uuid.uuid4()))
        assert info.has_renditions is False


class TestUcontentSettingsPartition:
    """Guard against settings drift between allowed_extensions and the partition sets."""

    def test_partition_covers_all_allowed_extensions(self) -> None:
        """Every extension in allowed_extensions must appear in exactly one partition bucket."""
        settings_dict = getattr(settings, "USERCONTENT_SETTINGS", {})
        allowed = frozenset(settings_dict.get("allowed_extensions", ()))
        audio = frozenset(settings_dict.get("audio_extensions", ()))
        document = frozenset(settings_dict.get("document_extensions", ()))
        image = frozenset(settings_dict.get("image_extensions", ()))
        video = frozenset(settings_dict.get("video_extensions", ()))

        union = audio | document | image | video
        missing = allowed - union
        assert not missing, (
            f"These extensions in allowed_extensions are not covered by any " f"partition bucket: {missing}"
        )

    def test_partitions_are_subsets_of_allowed_extensions(self) -> None:
        """No partition bucket should introduce extensions not in allowed_extensions."""
        settings_dict = getattr(settings, "USERCONTENT_SETTINGS", {})
        allowed = frozenset(settings_dict.get("allowed_extensions", ()))
        audio = frozenset(settings_dict.get("audio_extensions", ()))
        document = frozenset(settings_dict.get("document_extensions", ()))
        image = frozenset(settings_dict.get("image_extensions", ()))
        video = frozenset(settings_dict.get("video_extensions", ()))

        for bucket_name, bucket in [("audio", audio), ("document", document), ("image", image), ("video", video)]:
            extra = bucket - allowed
            assert not extra, f"Bucket '{bucket_name}' contains extensions not in allowed_extensions: {extra}"

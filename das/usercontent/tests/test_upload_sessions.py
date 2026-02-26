"""Unit tests for chunked upload session store (ERA-9210)."""

import uuid

import pytest

from usercontent.upload_sessions import append_chunk, create, delete, get, set_gcs_uri


@pytest.fixture
def tenant_id():
    return str(uuid.uuid4())


@pytest.fixture
def upload_id():
    return str(uuid.uuid4())


class TestUploadSessionsCreateGet:
    def test_create_and_get(self, tenant_id, upload_id):
        create(
            tenant_id,
            upload_id,
            storage_path="tenant/file_uploads/2025/2/26/abc/doc.pdf",
            filename="doc.pdf",
            size=1000,
            chunk_size=512,
            user_id=str(uuid.uuid4()),
            is_image=False,
            file_content_id=str(uuid.uuid4()),
        )
        data = get(tenant_id, upload_id)
        assert data is not None
        assert data["storage_path"] == "tenant/file_uploads/2025/2/26/abc/doc.pdf"
        assert data["filename"] == "doc.pdf"
        assert data["size"] == 1000
        assert data["chunk_size"] == 512
        assert data["next_chunk_index"] == 0
        assert data["chunk_hashes"] == {}
        assert data["gcs_resumable_uri"] == ""
        assert data["is_image"] is False
        assert "created_at" in data

    def test_get_missing_returns_none(self, tenant_id, upload_id):
        assert get(tenant_id, upload_id) is None

    def test_different_tenant_same_upload_id_isolated(self, upload_id):
        t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
        create(t1, upload_id, storage_path="p1", filename="a", size=10, chunk_size=10)
        assert get(t1, upload_id) is not None
        assert get(t2, upload_id) is None


class TestUploadSessionsSetGcsUri:
    def test_set_gcs_uri(self, tenant_id, upload_id):
        create(tenant_id, upload_id, storage_path="p", filename="f", size=1, chunk_size=1)
        set_gcs_uri(tenant_id, upload_id, "https://storage.googleapis.com/...")
        data = get(tenant_id, upload_id)
        assert data["gcs_resumable_uri"] == "https://storage.googleapis.com/..."

    def test_set_gcs_uri_missing_session_raises(self, tenant_id, upload_id):
        with pytest.raises(ValueError, match="Upload session not found"):
            set_gcs_uri(tenant_id, upload_id, "https://...")


class TestUploadSessionsAppendChunk:
    def test_append_chunk_in_order(self, tenant_id, upload_id):
        create(tenant_id, upload_id, storage_path="p", filename="f", size=20, chunk_size=10)
        accepted, err = append_chunk(tenant_id, upload_id, 0, b"0123456789")
        assert accepted is True
        assert err is None
        data = get(tenant_id, upload_id)
        assert data["next_chunk_index"] == 1
        assert 0 in data["chunk_hashes"]

        accepted, err = append_chunk(tenant_id, upload_id, 1, b"abcdefghij")
        assert accepted is True
        assert err is None
        data = get(tenant_id, upload_id)
        assert data["next_chunk_index"] == 2

    def test_append_chunk_out_of_order_returns_400(self, tenant_id, upload_id):
        create(tenant_id, upload_id, storage_path="p", filename="f", size=20, chunk_size=10)
        accepted, err = append_chunk(tenant_id, upload_id, 1, b"abcdefghij")
        assert accepted is False
        assert "out of order" in err

    def test_append_chunk_idempotent_same_bytes_204(self, tenant_id, upload_id):
        create(tenant_id, upload_id, storage_path="p", filename="f", size=10, chunk_size=10)
        chunk = b"0123456789"
        accepted, err = append_chunk(tenant_id, upload_id, 0, chunk)
        assert accepted is True and err is None
        accepted, err = append_chunk(tenant_id, upload_id, 0, chunk)
        assert accepted is True and err is None

    def test_append_chunk_same_index_different_bytes_400(self, tenant_id, upload_id):
        create(tenant_id, upload_id, storage_path="p", filename="f", size=20, chunk_size=10)
        append_chunk(tenant_id, upload_id, 0, b"0123456789")
        accepted, err = append_chunk(tenant_id, upload_id, 0, b"different!")
        assert accepted is False
        assert "different content" in err

    def test_append_chunk_missing_session(self, tenant_id, upload_id):
        accepted, err = append_chunk(tenant_id, upload_id, 0, b"bytes")
        assert accepted is False
        assert "not found" in err or "expired" in err


class TestUploadSessionsDelete:
    def test_delete_removes_session(self, tenant_id, upload_id):
        create(tenant_id, upload_id, storage_path="p", filename="f", size=1, chunk_size=1)
        assert get(tenant_id, upload_id) is not None
        delete(tenant_id, upload_id)
        assert get(tenant_id, upload_id) is None

"""Unit tests for chunked upload session store (ERA-9210)."""

import threading
import uuid

import pytest

from usercontent.upload_sessions import (
    append_chunk,
    create,
    delete,
    get,
    session_write_lock,
    set_gcs_uri,
)


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

    def test_delete_removes_locmem_fallback_lock_entry(self, tenant_id, upload_id):
        """After finalize, drop per-session threading.Lock so the registry cannot grow forever."""
        import usercontent.upload_sessions as us

        create(tenant_id, upload_id, storage_path="p", filename="f", size=1, chunk_size=1)
        with us.session_write_lock(tenant_id, upload_id):
            pass
        key = (tenant_id, upload_id)
        assert key in us._thread_locks
        delete(tenant_id, upload_id)
        assert key not in us._thread_locks


class TestUploadSessionsThreadLockRegistry:
    def test_thread_lock_for_session_returns_singleton_per_key(self, tenant_id, upload_id):
        import usercontent.upload_sessions as us

        lock_ids: list[int] = []
        barrier = threading.Barrier(2)

        def record() -> None:
            barrier.wait()
            lock_ids.append(id(us._thread_lock_for_session(tenant_id, upload_id)))

        t1 = threading.Thread(target=record)
        t2 = threading.Thread(target=record)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert lock_ids[0] == lock_ids[1]


class TestUploadSessionsSessionWriteLock:
    def test_concurrent_append_chunk_zero_serializes(self, tenant_id, upload_id):
        """Two threads appending the same first chunk under session_write_lock stay consistent."""
        create(
            tenant_id,
            upload_id,
            storage_path="p",
            filename="f",
            size=10,
            chunk_size=10,
            user_id=str(uuid.uuid4()),
            is_image=False,
            file_content_id=str(uuid.uuid4()),
        )
        chunk = b"0123456789"
        results = []
        barrier = threading.Barrier(2)

        def worker() -> None:
            barrier.wait()
            with session_write_lock(tenant_id, upload_id):
                results.append(append_chunk(tenant_id, upload_id, 0, chunk))

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert all(r[0] for r in results), results
        data = get(tenant_id, upload_id)
        assert data is not None
        assert data["next_chunk_index"] == 1
        assert 0 in data["chunk_hashes"]

"""
DRF API for ERA-9210 chunked uploads: Redis session + GCS resumable + FileContent / ImageFileContent.

Client flow: POST init → PUT each chunk (raw body) → POST complete.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import Any

from versatileimagefield.fields import VersatileImageField
from versatileimagefield.files import VersatileImageFieldFile

from django.conf import settings
from django.db.models.fields.files import FieldFile
from rest_framework import serializers, status
from rest_framework.parsers import BaseParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core import resumable_upload
from usercontent import upload_sessions
from usercontent.models import FileContent, ImageFileContent
from usercontent.serializers import FileContentSerializer, ImageFileContentSerializer
from usercontent.storage_paths import build_usercontent_storage_path, is_image_filename
from utils.tenant.thread import get_tenant_settings

logger = logging.getLogger(__name__)

MAX_SIZE = getattr(settings, "CHUNKED_UPLOAD_MAX_FILE_SIZE", 500 * 1024 * 1024)
PROHIBITED = set(
    getattr(settings, "USERCONTENT_SETTINGS", {}).get(
        "prohibited_extensions",
        (),
    )
)


def _effective_max_chunk_bytes() -> int:
    """
    Upper bound for a single chunk request body.

    Django rejects bodies larger than DATA_UPLOAD_MAX_MEMORY_SIZE (default 2621440) with
    RequestDataTooBig / SuspiciousOperation; keep a margin below that ceiling so production
    does not fail after parsing headers.
    """
    django_limit = int(getattr(settings, "DATA_UPLOAD_MAX_MEMORY_SIZE", 2621440))
    margin = 64 * 1024
    ceiling = max(django_limit - margin, 1)
    configured = int(getattr(settings, "CHUNKED_UPLOAD_CHUNK_SIZE", 2 * 1024 * 1024))
    return min(configured, ceiling)


def _chunk_size_validation_message() -> str:
    cap = _effective_max_chunk_bytes()
    return (
        f"chunk_size must not exceed {cap} bytes (effective maximum: the lesser of "
        "CHUNKED_UPLOAD_CHUNK_SIZE and Django DATA_UPLOAD_MAX_MEMORY_SIZE with a safety margin)."
    )


class ChunkedUploadOctetStreamParser(BaseParser):
    """Accept raw bytes for chunk PUTs; default DRF parsers only allow JSON/form and would return 415."""

    media_type = "application/octet-stream"

    def parse(self, stream, media_type=None, parser_context=None) -> bytes:
        return stream.read()


class ChunkedUploadInitSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=512)
    size = serializers.IntegerField(min_value=1, max_value=MAX_SIZE)
    chunk_size = serializers.IntegerField(required=False, min_value=1)

    def validate_chunk_size(self, value: int | None) -> int | None:
        if value is None:
            return value
        cap = _effective_max_chunk_bytes()
        if value > cap:
            raise serializers.ValidationError(_chunk_size_validation_message())
        return value

    def validate_filename(self, value: str) -> str:
        ext = value.rsplit(".", 1)[-1].lower() if "." in value else ""
        if ext in PROHIBITED:
            raise serializers.ValidationError(f"Prohibited file extension: {ext}")
        return value


def _tenant_key() -> str:
    return str(get_tenant_settings().id)


def _expected_num_chunks(total: int, chunk_size: int) -> int:
    return max(1, math.ceil(total / chunk_size))


def _chunk_byte_length(chunk_index: int, total: int, chunk_size: int) -> int:
    n = _expected_num_chunks(total, chunk_size)
    if chunk_index < 0 or chunk_index >= n:
        return 0
    if chunk_index == n - 1:
        return total - chunk_index * chunk_size
    return chunk_size


def _attach_existing_file(instance: Any, storage_path: str) -> None:
    field = instance._meta.get_field("file")
    if isinstance(field, VersatileImageField):
        instance.file = VersatileImageFieldFile(instance, field, storage_path)
    else:
        instance.file = FieldFile(instance, field, storage_path)
    instance.file._committed = True


def _chunk_request_validation_response(data: dict[str, Any], chunk_index: int, chunk_body: bytes) -> Response | None:
    """Return an error Response, or None if the chunk index and body length are valid."""
    total = data["size"]
    csize = data["chunk_size"]
    n = _expected_num_chunks(total, csize)
    if chunk_index < 0 or chunk_index >= n:
        return Response(
            {"detail": f"chunk_index out of range (0..{n - 1})."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    expected_len = _chunk_byte_length(chunk_index, total, csize)
    if len(chunk_body) != expected_len:
        return Response(
            {
                "detail": "Chunk size mismatch.",
                "expected_length": expected_len,
                "actual_length": len(chunk_body),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


class ChunkedUploadInitView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        ser = ChunkedUploadInitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        filename = ser.validated_data["filename"]
        size = ser.validated_data["size"]
        max_chunk = _effective_max_chunk_bytes()
        preferred = int(getattr(settings, "CHUNKED_UPLOAD_CHUNK_SIZE", 2 * 1024 * 1024))
        chunk_size = min(ser.validated_data.get("chunk_size") or preferred, max_chunk)

        upload_id = uuid.uuid4()
        uploads_root = "image_fileuploads" if is_image_filename(filename) else "file_uploads"
        storage_path = build_usercontent_storage_path(upload_id, filename, uploads_root=uploads_root)
        tenant_id = _tenant_key()

        try:
            gcs_uri = resumable_upload.initiate(storage_path, size)
        except Exception:
            error_id = str(uuid.uuid4())
            logger.exception(
                "chunked_upload init failed error_id=%s tenant=%s upload_id=%s path=%s size=%s",
                error_id,
                tenant_id,
                upload_id,
                storage_path,
                size,
            )
            return Response(
                {"detail": "Could not start upload with storage.", "error_id": error_id},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        upload_sessions.create(
            tenant_id,
            str(upload_id),
            storage_path=storage_path,
            filename=filename,
            size=size,
            chunk_size=chunk_size,
            user_id=str(request.user.pk),
            is_image=is_image_filename(filename),
            file_content_id=str(upload_id),
        )
        upload_sessions.set_gcs_uri(tenant_id, str(upload_id), gcs_uri)

        return Response(
            {
                "upload_id": str(upload_id),
                "chunk_size": chunk_size,
                "size": size,
                "num_chunks": _expected_num_chunks(size, chunk_size),
                "storage_path": storage_path,
            },
            status=status.HTTP_201_CREATED,
        )


class ChunkedUploadStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, upload_id, *args, **kwargs):
        tenant_id = _tenant_key()
        data = upload_sessions.get(tenant_id, str(upload_id))
        if not data:
            return Response({"detail": "Upload session not found or expired."}, status=status.HTTP_404_NOT_FOUND)
        if data.get("user_id") != str(request.user.pk):
            return Response(status=status.HTTP_403_FORBIDDEN)

        n = _expected_num_chunks(data["size"], data["chunk_size"])
        return Response(
            {
                "upload_id": str(upload_id),
                "next_chunk_index": data["next_chunk_index"],
                "num_chunks": n,
                "complete": data["next_chunk_index"] >= n,
                "size": data["size"],
                "chunk_size": data["chunk_size"],
            }
        )


class ChunkedUploadChunkView(APIView):
    permission_classes = (IsAuthenticated,)
    parser_classes = (ChunkedUploadOctetStreamParser,)

    def put(self, request, upload_id, chunk_index: int, *args, **kwargs):
        tenant_id = _tenant_key()
        uid = str(upload_id)
        data = upload_sessions.get(tenant_id, uid)
        if not data:
            return Response({"detail": "Upload session not found or expired."}, status=status.HTTP_404_NOT_FOUND)
        if data.get("user_id") != str(request.user.pk):
            return Response(status=status.HTTP_403_FORBIDDEN)

        chunk_body = bytes(request.data)
        bad = _chunk_request_validation_response(data, chunk_index, chunk_body)
        if bad is not None:
            return bad

        with upload_sessions.session_write_lock(tenant_id, uid):
            data = upload_sessions.get(tenant_id, uid)
            if not data:
                return Response({"detail": "Upload session not found or expired."}, status=status.HTTP_404_NOT_FOUND)
            if data.get("user_id") != str(request.user.pk):
                return Response(status=status.HTTP_403_FORBIDDEN)

            bad2 = _chunk_request_validation_response(data, chunk_index, chunk_body)
            if bad2 is not None:
                return bad2

            next_idx = data["next_chunk_index"]
            uri = data.get("gcs_resumable_uri")
            if not uri:
                logger.error("chunked_upload missing gcs uri tenant=%s upload_id=%s", tenant_id, upload_id)
                return Response({"detail": "Upload session is invalid."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if chunk_index < next_idx:
                accepted, err = upload_sessions.append_chunk(tenant_id, uid, chunk_index, chunk_body)
                if not accepted:
                    logger.warning(
                        "chunked_upload idempotent chunk rejected tenant=%s upload_id=%s index=%s reason=%s",
                        tenant_id,
                        upload_id,
                        chunk_index,
                        err,
                    )
                    return Response({"detail": err or "Chunk rejected."}, status=status.HTTP_400_BAD_REQUEST)
                return Response(status=status.HTTP_204_NO_CONTENT)

            if chunk_index > next_idx:
                logger.warning(
                    "chunked_upload out-of-order tenant=%s upload_id=%s index=%s expected=%s",
                    tenant_id,
                    upload_id,
                    chunk_index,
                    next_idx,
                )
                return Response({"detail": "Chunk out of order."}, status=status.HTTP_400_BAD_REQUEST)

            start = chunk_index * data["chunk_size"]
            try:
                resumable_upload.upload_chunk(uri, chunk_body, start, data["size"])
            except Exception:
                error_id = str(uuid.uuid4())
                logger.exception(
                    "chunked_upload GCS chunk failed error_id=%s tenant=%s upload_id=%s index=%s start=%s",
                    error_id,
                    tenant_id,
                    upload_id,
                    chunk_index,
                    start,
                )
                return Response(
                    {"detail": "Storage chunk upload failed.", "error_id": error_id},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            accepted, err = upload_sessions.append_chunk(tenant_id, uid, chunk_index, chunk_body)
            if not accepted:
                error_id = str(uuid.uuid4())
                logger.error(
                    "chunked_upload session update failed after GCS success error_id=%s tenant=%s "
                    "upload_id=%s index=%s err=%s",
                    error_id,
                    tenant_id,
                    upload_id,
                    chunk_index,
                    err,
                )
                return Response(
                    {"detail": "Upload session could not be updated after storage write.", "error_id": error_id},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            return Response(status=status.HTTP_204_NO_CONTENT)


class ChunkedUploadCompleteView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request, upload_id, *args, **kwargs):
        tenant_id = _tenant_key()
        uid = str(upload_id)
        data = upload_sessions.get(tenant_id, uid)
        if not data:
            return Response({"detail": "Upload session not found or expired."}, status=status.HTTP_404_NOT_FOUND)
        if data.get("user_id") != str(request.user.pk):
            return Response(status=status.HTTP_403_FORBIDDEN)

        with upload_sessions.session_write_lock(tenant_id, uid):
            data = upload_sessions.get(tenant_id, uid)
            if not data:
                return Response({"detail": "Upload session not found or expired."}, status=status.HTTP_404_NOT_FOUND)
            if data.get("user_id") != str(request.user.pk):
                return Response(status=status.HTTP_403_FORBIDDEN)

            total = data["size"]
            csize = data["chunk_size"]
            n = _expected_num_chunks(total, csize)
            if data["next_chunk_index"] != n:
                return Response(
                    {
                        "detail": "Upload incomplete.",
                        "next_chunk_index": data["next_chunk_index"],
                        "num_chunks": n,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            storage_path = data["storage_path"]
            content_id = uuid.UUID(data.get("file_content_id") or str(upload_id))
            is_image = data.get("is_image", False)

            try:
                if is_image:
                    instance = ImageFileContent(id=content_id, created_by=request.user)
                    _attach_existing_file(instance, storage_path)
                    instance.save()
                    out = ImageFileContentSerializer(instance, context={"request": request}).data
                else:
                    instance = FileContent(id=content_id, created_by=request.user)
                    _attach_existing_file(instance, storage_path)
                    instance.save()
                    out = FileContentSerializer(instance, context={"request": request}).data
            except Exception:
                error_id = str(uuid.uuid4())
                logger.exception(
                    "chunked_upload finalize model save failed error_id=%s tenant=%s upload_id=%s path=%s",
                    error_id,
                    tenant_id,
                    upload_id,
                    storage_path,
                )
                return Response(
                    {"detail": "Failed to register uploaded file.", "error_id": error_id},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            upload_sessions.delete(tenant_id, uid)
            out["file_type"] = "image" if is_image else "file"
            return Response(out, status=status.HTTP_200_OK)

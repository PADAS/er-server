"""
Programmatic REST API for the CSV observation import feature.

Mirrors the admin wizard, but as three endpoints intended for use by external
scripts and integrations:

  POST /source/{id}/csvdata/                 — upload a CSV (returns storage_path + columns + sample)
  POST /source/{id}/csvdata/import/          — kick off an async import (storage_path + mappings)
  GET  /source/{id}/csvdata/status/{task_id} — poll task status

The upload step persists the file to default_storage (tenant-scoped via
TenantGoogleCloudStorage in production); the import step accepts the returned
storage_path and queues the same Celery task the admin uses.
"""

import csv
import io
import logging
import uuid

from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from observations.csv_import_jobs import get_job_status
from observations.models import Source
from observations.tasks import process_csv_observations
from utils import add_base_url

logger = logging.getLogger(__name__)

CSV_IMPORT_FOLDER = "csv-imports"
MAX_CSV_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
CSV_PREVIEW_BYTES = 1024 * 1024  # 1 MB read budget for preview/sample

# Observation fields a CSV column can be mapped to
OBSERVATION_TARGET_FIELDS = [
    {"value": "recorded_at", "label": "Recorded At (timestamp)"},
    {"value": "latitude", "label": "Latitude"},
    {"value": "longitude", "label": "Longitude"},
    {"value": "additional", "label": "Additional data (uses column name as key)"},
]


def _is_safe_storage_path(storage_path):
    """Restrict imports to paths the upload endpoint produced.

    The worker calls default_storage.delete(storage_path) on success, so we must
    refuse arbitrary paths from clients — otherwise a caller with add_observation
    could delete any tenant-scoped file just by submitting its path here.
    """
    if not isinstance(storage_path, str) or not storage_path:
        return False
    if ".." in storage_path.split("/"):
        return False
    return storage_path.startswith(f"{CSV_IMPORT_FOLDER}/")


class CSVObservationUploadView(APIView):
    """
    POST a CSV file. Persists it to default_storage and returns the storage path
    along with column headers and a few preview rows. The client passes the
    storage path back to the import step.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request, id, *args, **kwargs):
        if not request.user.has_perm("observations.add_observation"):
            raise PermissionDenied
        get_object_or_404(Source, id=id)

        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            return Response({"error": "No csv_file provided."}, status=status.HTTP_400_BAD_REQUEST)

        if csv_file.size and csv_file.size > MAX_CSV_UPLOAD_BYTES:
            limit_mb = MAX_CSV_UPLOAD_BYTES // (1024 * 1024)
            return Response(
                {"error": f"File exceeds the {limit_mb} MB upload limit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        storage_path = default_storage.save(
            f"{CSV_IMPORT_FOLDER}/{uuid.uuid4().hex}-{csv_file.name or 'upload.csv'}",
            csv_file,
        )

        # Read just enough to surface column headers and a 5-row sample.
        try:
            with default_storage.open(storage_path, "rb") as f:
                preview = f.read(CSV_PREVIEW_BYTES)
        except Exception as exc:
            default_storage.delete(storage_path)
            logger.exception("Failed to read uploaded CSV for preview")
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            text = preview.decode("utf-8-sig")
        except UnicodeDecodeError:
            default_storage.delete(storage_path)
            return Response(
                {"error": "File must be UTF-8 encoded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reader = csv.DictReader(io.StringIO(text))
        columns = list(reader.fieldnames or [])
        if not columns:
            default_storage.delete(storage_path)
            return Response({"error": "CSV has no column headers."}, status=status.HTTP_400_BAD_REQUEST)

        sample_rows = []
        for i, row in enumerate(reader):
            if i >= 5:
                break
            sample_rows.append(dict(row))

        return Response(
            {
                "storage_path": storage_path,
                "columns": columns,
                "sample_rows": sample_rows,
                "target_fields": OBSERVATION_TARGET_FIELDS,
            },
            status=status.HTTP_200_OK,
        )


class CSVObservationImportView(APIView):
    """
    POST { storage_path, mappings } to kick off the async import.
    storage_path: value returned by the upload endpoint (must live under
                  the csv-imports/ prefix).
    mappings: dict of { csv_column_name: target_field }.
    target_field is one of: recorded_at | latitude | longitude | additional
    Required mappings: recorded_at, latitude, longitude.
    """

    permission_classes = (IsAuthenticated,)

    def post(self, request, id, *args, **kwargs):
        if not request.user.has_perm("observations.add_observation"):
            raise PermissionDenied
        get_object_or_404(Source, id=id)

        storage_path = request.data.get("storage_path")
        mappings = request.data.get("mappings") or {}

        if not storage_path:
            return Response({"error": "storage_path is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not _is_safe_storage_path(storage_path):
            # Refuse arbitrary paths — see _is_safe_storage_path docstring.
            return Response(
                {"error": "storage_path must be a value returned by the upload endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mapped_targets = set(mappings.values())
        required = {"recorded_at", "latitude", "longitude"}
        missing = required - mapped_targets
        if missing:
            return Response(
                {"error": f"Required fields not mapped: {', '.join(sorted(missing))}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            async_result = process_csv_observations.apply_async(
                args=(storage_path, mappings),
                kwargs={"source_id": str(id)},
            )
        except Exception as exc:
            logger.exception("Failed to queue CSV import task")
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        status_url = add_base_url(
            request,
            reverse("csv-import-status", kwargs={"id": id, "task_id": async_result.id}),
        )
        return Response(
            {"task_id": async_result.id, "task_url": status_url},
            status=status.HTTP_201_CREATED,
        )


class CSVImportStatusView(APIView):
    """Poll the status of a running CSV import task."""

    permission_classes = (IsAuthenticated,)

    def get(self, request, id, task_id, **kwargs):
        if not request.user.has_perm("observations.add_observation"):
            raise PermissionDenied
        get_object_or_404(Source, id=id)

        job = get_job_status(task_id)
        job_status = job.get("status", "PENDING")
        result = job.get("error") if job_status == "FAILURE" else job.get("result")
        data = {
            "task_result": result,
            "task_status": job_status.title(),
            "task_success": job_status == "SUCCESS",
            "task_failed": job_status == "FAILURE",
        }
        return Response(data, status=status.HTTP_200_OK)

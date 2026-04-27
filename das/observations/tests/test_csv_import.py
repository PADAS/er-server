"""
Tests for the CSV observation import feature:
  - CSVObservationUploadView   (POST /api/v1.0/source/{id}/csvdata/)
  - CSVObservationImportView   (POST /api/v1.0/source/{id}/csvdata/import/)
  - CSVImportStatusView        (GET  /api/v1.0/source/{id}/csvdata/status/{task_id}/)
  - process_csv_observations   (Celery task)
  - ObservationAdmin import views (admin pages)
  - csv_import_jobs Redis-backed pending list
"""

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse

from factories import SourceFactory, SubjectFactory, UserFactory
from observations.models import Observation, Source, SubjectSource

# ── helpers ──────────────────────────────────────────────────────────────────

VALID_CSV = (
    "recorded_at,latitude,longitude,speed\n"
    "2024-01-01T00:00:00Z,1.0,2.0,10\n"
    "2024-01-01T01:00:00Z,1.1,2.1,20\n"
    "2024-01-01T02:00:00Z,1.2,2.2,30\n"
)

MINIMAL_CSV = "recorded_at,latitude,longitude\n2024-06-01T12:00:00Z,10.0,20.0\n"

SUBJECT_CSV = (
    "recorded_at,latitude,longitude,subject_name\n"
    "2024-01-01T00:00:00Z,1.0,2.0,Lion\n"
    "2024-01-01T01:00:00Z,1.1,2.1,Elephant\n"
    "2024-01-01T02:00:00Z,1.2,2.2,Lion\n"
)


def _csv_file(content=VALID_CSV):
    return io.BytesIO(content.encode())


def _store_csv(content=VALID_CSV):
    """Save CSV content to default_storage and return the storage path."""
    return default_storage.save(
        f"csv-imports/{uuid.uuid4().hex}.csv",
        ContentFile(content.encode()),
    )


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def source():
    return SourceFactory()


# ── CSVObservationUploadView ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestCSVObservationUploadView:
    def _url(self, source_id):
        return reverse("csv-upload", kwargs={"id": source_id})

    def test_upload_returns_columns_and_storage_path(self, superuser_client, source):
        f = _csv_file()
        f.name = "obs.csv"
        response = superuser_client.post(self._url(source.id), {"csv_file": f}, format="multipart")
        assert response.status_code == 200
        assert set(response.data["columns"]) == {"recorded_at", "latitude", "longitude", "speed"}
        assert response.data["storage_path"]
        assert default_storage.exists(response.data["storage_path"])
        assert len(response.data["sample_rows"]) == 3

    def test_upload_returns_target_fields(self, superuser_client, source):
        f = _csv_file()
        f.name = "obs.csv"
        response = superuser_client.post(self._url(source.id), {"csv_file": f}, format="multipart")
        assert response.status_code == 200
        values = {tf["value"] for tf in response.data["target_fields"]}
        assert {"recorded_at", "latitude", "longitude", "additional"} == values

    def test_upload_strips_bom(self, superuser_client, source):
        content = "recorded_at,latitude,longitude\n2024-01-01T00:00:00Z,1.0,2.0\n"
        f = io.BytesIO(content.encode("utf-8-sig"))
        f.name = "bom.csv"
        response = superuser_client.post(self._url(source.id), {"csv_file": f}, format="multipart")
        assert response.status_code == 200
        assert "recorded_at" in response.data["columns"]

    def test_upload_rejects_missing_file(self, superuser_client, source):
        response = superuser_client.post(self._url(source.id), {}, format="multipart")
        assert response.status_code == 400
        assert "error" in response.data

    def test_upload_rejects_empty_csv(self, superuser_client, source):
        f = io.BytesIO(b"")
        f.name = "empty.csv"
        response = superuser_client.post(self._url(source.id), {"csv_file": f}, format="multipart")
        assert response.status_code == 400

    def test_upload_rejects_oversized_file(self, superuser_client, source):
        f = _csv_file()
        f.name = "big.csv"
        with patch("observations.views.csv_import.MAX_CSV_UPLOAD_BYTES", 10):
            response = superuser_client.post(self._url(source.id), {"csv_file": f}, format="multipart")
        assert response.status_code == 400
        assert "limit" in response.data["error"].lower()

    def test_upload_requires_authentication(self, source):
        from rest_framework.test import APIClient

        anon = APIClient()
        f = _csv_file()
        f.name = "obs.csv"
        response = anon.post(self._url(source.id), {"csv_file": f}, format="multipart")
        assert response.status_code in (401, 403)

    def test_upload_requires_add_observation_permission(self, user_client, source):
        f = _csv_file()
        f.name = "obs.csv"
        response = user_client.post(self._url(source.id), {"csv_file": f}, format="multipart")
        assert response.status_code == 403

    def test_upload_nonexistent_source_returns_404(self, superuser_client):
        url = reverse("csv-upload", kwargs={"id": uuid.uuid4()})
        f = _csv_file()
        f.name = "obs.csv"
        response = superuser_client.post(url, {"csv_file": f}, format="multipart")
        assert response.status_code == 404


# ── CSVObservationImportView ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestCSVObservationImportView:
    def _url(self, source_id):
        return reverse("csv-import", kwargs={"id": source_id})

    def _good_mappings(self):
        return {
            "recorded_at": "recorded_at",
            "latitude": "latitude",
            "longitude": "longitude",
        }

    def test_import_kicks_off_task(self, superuser_client, source):
        mock_result = MagicMock()
        mock_result.id = str(uuid.uuid4())
        storage_path = _store_csv()

        with patch("observations.views.csv_import.process_csv_observations") as mock_task:
            mock_task.apply_async.return_value = mock_result
            response = superuser_client.post(
                self._url(source.id),
                {"storage_path": storage_path, "mappings": self._good_mappings()},
                format="json",
            )

        assert response.status_code == 201
        assert response.data["task_id"] == mock_result.id
        assert "task_url" in response.data
        mock_task.apply_async.assert_called_once()

    def test_import_passes_mappings_to_task(self, superuser_client, source):
        mock_result = MagicMock()
        mock_result.id = str(uuid.uuid4())
        mappings = {**self._good_mappings(), "speed": "additional"}
        storage_path = _store_csv()

        with patch("observations.views.csv_import.process_csv_observations") as mock_task:
            mock_task.apply_async.return_value = mock_result
            superuser_client.post(
                self._url(source.id),
                {"storage_path": storage_path, "mappings": mappings},
                format="json",
            )

        args = mock_task.apply_async.call_args[1].get("args") or mock_task.apply_async.call_args[0][0]
        assert args[0] == storage_path
        assert mappings == args[1]
        kwargs = mock_task.apply_async.call_args[1].get("kwargs") or {}
        assert kwargs.get("source_id") == str(source.id)

    def test_import_rejects_missing_recorded_at(self, superuser_client, source):
        response = superuser_client.post(
            self._url(source.id),
            {
                "storage_path": _store_csv(),
                "mappings": {"latitude": "latitude", "longitude": "longitude"},
            },
            format="json",
        )
        assert response.status_code == 400
        assert "recorded_at" in response.data["error"]

    def test_import_rejects_missing_latitude(self, superuser_client, source):
        response = superuser_client.post(
            self._url(source.id),
            {
                "storage_path": _store_csv(),
                "mappings": {"recorded_at": "recorded_at", "longitude": "longitude"},
            },
            format="json",
        )
        assert response.status_code == 400
        assert "latitude" in response.data["error"]

    def test_import_rejects_missing_storage_path(self, superuser_client, source):
        response = superuser_client.post(
            self._url(source.id),
            {"mappings": self._good_mappings()},
            format="json",
        )
        assert response.status_code == 400

    def test_import_rejects_storage_path_outside_csv_imports_folder(self, superuser_client, source):
        """A client cannot trick the worker into deleting an arbitrary tenant file."""
        response = superuser_client.post(
            self._url(source.id),
            {"storage_path": "user-uploads/secret.txt", "mappings": self._good_mappings()},
            format="json",
        )
        assert response.status_code == 400
        assert "storage_path" in response.data["error"]

    def test_import_rejects_storage_path_with_traversal(self, superuser_client, source):
        response = superuser_client.post(
            self._url(source.id),
            {"storage_path": "csv-imports/../etc/passwd", "mappings": self._good_mappings()},
            format="json",
        )
        assert response.status_code == 400

    def test_import_requires_authentication(self, source):
        from rest_framework.test import APIClient

        anon = APIClient()
        response = anon.post(self._url(source.id), {}, format="json")
        assert response.status_code in (401, 403)

    def test_import_requires_add_observation_permission(self, user_client, source):
        response = user_client.post(
            self._url(source.id),
            {"storage_path": _store_csv(), "mappings": self._good_mappings()},
            format="json",
        )
        assert response.status_code == 403


# ── CSVImportStatusView ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCSVImportStatusView:
    def _url(self, source_id, task_id):
        return reverse("csv-import-status", kwargs={"id": source_id, "task_id": str(task_id)})

    def test_returns_success_status(self, superuser_client, source):
        task_id = uuid.uuid4()
        job = {"status": "SUCCESS", "result": "Successfully created 3 observations"}

        with patch("observations.views.csv_import.get_job_status", return_value=job):
            response = superuser_client.get(self._url(source.id, task_id))

        assert response.status_code == 200
        assert response.data["task_success"] is True
        assert response.data["task_failed"] is False

    def test_returns_pending_status(self, superuser_client, source):
        task_id = uuid.uuid4()
        job = {"status": "PENDING"}

        with patch("observations.views.csv_import.get_job_status", return_value=job):
            response = superuser_client.get(self._url(source.id, task_id))

        assert response.status_code == 200
        assert response.data["task_status"] == "Pending"

    def test_returns_failure_status(self, superuser_client, source):
        task_id = uuid.uuid4()
        job = {"status": "FAILURE", "error": "bad data"}

        with patch("observations.views.csv_import.get_job_status", return_value=job):
            response = superuser_client.get(self._url(source.id, task_id))

        assert response.status_code == 200
        assert response.data["task_failed"] is True
        assert "bad data" in str(response.data["task_result"])

    def test_requires_authentication(self, source):
        from rest_framework.test import APIClient

        anon = APIClient()
        response = anon.get(self._url(source.id, uuid.uuid4()))
        assert response.status_code in (401, 403)


# ── process_csv_observations task ─────────────────────────────────────────────


@pytest.mark.django_db
class TestProcessCsvObservationsTask:
    """Test the Celery task directly (synchronous call)."""

    def test_creates_observations(self, source):
        from observations.tasks import process_csv_observations

        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}
        process_csv_observations.run(_store_csv(MINIMAL_CSV), mappings, source_id=str(source.id))

        assert Observation.objects.filter(source=source).count() == 1

    def test_creates_multiple_observations(self, source):
        from observations.tasks import process_csv_observations

        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}
        process_csv_observations.run(_store_csv(VALID_CSV), mappings, source_id=str(source.id))

        assert Observation.objects.filter(source=source).count() == 3

    def test_stores_additional_columns(self, source):
        from observations.tasks import process_csv_observations

        mappings = {
            "recorded_at": "recorded_at",
            "latitude": "latitude",
            "longitude": "longitude",
            "speed": "additional",
        }
        process_csv_observations.run(_store_csv(VALID_CSV), mappings, source_id=str(source.id))

        obs = Observation.objects.filter(source=source).first()
        assert obs.additional.get("speed") is not None

    def test_skips_duplicate_timestamps(self, source):
        from observations.tasks import process_csv_observations

        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}

        process_csv_observations.run(_store_csv(MINIMAL_CSV), mappings, source_id=str(source.id))
        assert Observation.objects.filter(source=source).count() == 1

        process_csv_observations.run(_store_csv(MINIMAL_CSV), mappings, source_id=str(source.id))
        assert Observation.objects.filter(source=source).count() == 1

    def test_skips_intra_batch_duplicates(self, source):
        from observations.tasks import process_csv_observations

        duplicate_csv = (
            "recorded_at,latitude,longitude\n" "2024-03-01T00:00:00Z,1.0,2.0\n" "2024-03-01T00:00:00Z,3.0,4.0\n"
        )
        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}
        process_csv_observations.run(_store_csv(duplicate_csv), mappings, source_id=str(source.id))

        assert Observation.objects.filter(source=source).count() == 1

    def test_skips_rows_with_invalid_timestamps(self, source):
        from observations.tasks import process_csv_observations

        bad_csv = "recorded_at,latitude,longitude\n" "not-a-date,1.0,2.0\n" "2024-05-01T00:00:00Z,5.0,6.0\n"
        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}
        process_csv_observations.run(_store_csv(bad_csv), mappings, source_id=str(source.id))

        assert Observation.objects.filter(source=source).count() == 1

    def test_returns_success_message(self, source):
        from observations.tasks import process_csv_observations

        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}
        result = process_csv_observations.run(_store_csv(MINIMAL_CSV), mappings, source_id=str(source.id))

        assert "1" in result

    def test_sets_correct_location(self, source):
        from observations.tasks import process_csv_observations

        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}
        process_csv_observations.run(_store_csv(MINIMAL_CSV), mappings, source_id=str(source.id))

        obs = Observation.objects.get(source=source)
        assert abs(obs.location.x - 20.0) < 0.001
        assert abs(obs.location.y - 10.0) < 0.001

    def test_deletes_storage_file_on_success(self, source):
        from observations.tasks import process_csv_observations

        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}
        path = _store_csv(MINIMAL_CSV)
        assert default_storage.exists(path)

        process_csv_observations.run(path, mappings, source_id=str(source.id))

        assert not default_storage.exists(path)

    def test_subject_name_col_creates_source_and_subject_source(self):
        from observations.tasks import process_csv_observations

        mappings = {
            "recorded_at": "recorded_at",
            "latitude": "latitude",
            "longitude": "longitude",
            "subject_name": "subject_name",
        }
        process_csv_observations.run(_store_csv(SUBJECT_CSV), mappings, subject_name_col=True)

        # Two unique subject names: Lion, Elephant
        assert Source.objects.filter(manufacturer_id="Lion").exists()
        assert Source.objects.filter(manufacturer_id="Elephant").exists()
        assert SubjectSource.objects.filter(source__manufacturer_id="Lion").exists()
        assert SubjectSource.objects.filter(source__manufacturer_id="Elephant").exists()

    def test_subject_name_col_creates_correct_observation_count(self):
        from observations.tasks import process_csv_observations

        mappings = {
            "recorded_at": "recorded_at",
            "latitude": "latitude",
            "longitude": "longitude",
            "subject_name": "subject_name",
        }
        process_csv_observations.run(_store_csv(SUBJECT_CSV), mappings, subject_name_col=True)

        lion_source = Source.objects.get(manufacturer_id="Lion")
        elephant_source = Source.objects.get(manufacturer_id="Elephant")
        assert Observation.objects.filter(source=lion_source).count() == 2
        assert Observation.objects.filter(source=elephant_source).count() == 1

    def test_subject_name_col_reuses_existing_source(self):
        from observations.tasks import process_csv_observations

        mappings = {
            "recorded_at": "recorded_at",
            "latitude": "latitude",
            "longitude": "longitude",
            "subject_name": "subject_name",
        }
        process_csv_observations.run(_store_csv(SUBJECT_CSV), mappings, subject_name_col=True)
        source_count_before = Source.objects.count()
        subject_source_count_before = SubjectSource.objects.count()

        # Re-importing with a different CSV but same subject names should not create new sources
        second_csv = "recorded_at,latitude,longitude,subject_name\n" "2024-02-01T00:00:00Z,2.0,3.0,Lion\n"
        process_csv_observations.run(_store_csv(second_csv), mappings, subject_name_col=True)

        assert Source.objects.count() == source_count_before
        assert SubjectSource.objects.count() == subject_source_count_before

    def test_manual_subject_creates_new_source(self):
        from observations.tasks import process_csv_observations

        subject = SubjectFactory()
        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}
        source_count_before = Source.objects.count()

        process_csv_observations.run(_store_csv(MINIMAL_CSV), mappings, subject_id=str(subject.id))

        assert Source.objects.count() == source_count_before + 1
        new_source = Source.objects.order_by("-created_at").first()
        assert SubjectSource.objects.filter(source=new_source, subject=subject).exists()

    def test_manual_subject_observations_assigned_to_new_source(self):
        from observations.tasks import process_csv_observations

        subject = SubjectFactory()
        mappings = {"recorded_at": "recorded_at", "latitude": "latitude", "longitude": "longitude"}

        process_csv_observations.run(_store_csv(MINIMAL_CSV), mappings, subject_id=str(subject.id))

        new_source = Source.objects.order_by("-created_at").first()
        assert Observation.objects.filter(source=new_source).count() == 1


# ── Admin ObservationAdmin import views ───────────────────────────────────────


@pytest.mark.django_db
class TestAdminObservationImportCsvView:
    """Tests for the multi-step Django admin import view on ObservationAdmin."""

    @pytest.fixture
    def admin_client(self):
        from django.test import Client

        admin_user = UserFactory(is_superuser=True, is_staff=True)
        c = Client()
        c.force_login(admin_user)
        return c

    def _upload_url(self):
        return reverse("admin:observations_observation_import_csv")

    def _map_url(self):
        return reverse("admin:observations_observation_import_csv_map_columns")

    def _select_url(self):
        return reverse("admin:observations_observation_import_csv_select_subject")

    def _do_step1(self, admin_client, content=VALID_CSV):
        """POST step 1, return the redirect response (Location has ?key=...)."""
        f = _csv_file(content)
        f.name = "obs.csv"
        return admin_client.post(self._upload_url(), {"csv_file": f})

    def _do_step2_get(self, admin_client, session_key):
        return admin_client.get(f"{self._map_url()}?key={session_key}")

    def _session_key_from_redirect(self, response):
        location = response["Location"]
        return location.split("key=")[1]

    # Step 1 ──────────────────────────────────────────────────────────────────

    def test_get_renders_step1(self, admin_client):
        response = admin_client.get(self._upload_url())
        assert response.status_code == 200
        assert response.context["step"] == 1

    def test_step1_post_without_file_shows_error(self, admin_client):
        response = admin_client.post(self._upload_url(), {})
        assert response.status_code == 200
        assert response.context["step"] == 1
        assert response.context["error"]

    def test_step1_post_with_csv_redirects_to_map_columns(self, admin_client):
        response = self._do_step1(admin_client)
        assert response.status_code == 302
        assert "map-columns" in response["Location"]
        assert "key=" in response["Location"]

    def test_step1_rejects_oversized_file(self, admin_client):
        f = _csv_file()
        f.name = "big.csv"
        with patch("observations.admin.MAX_CSV_UPLOAD_BYTES", 10):
            response = admin_client.post(self._upload_url(), {"csv_file": f})
        assert response.status_code == 200
        assert response.context["step"] == 1
        assert "limit" in response.context["error"].lower()

    # Step 2 ──────────────────────────────────────────────────────────────────

    def test_map_columns_get_renders_step2(self, admin_client):
        r1 = self._do_step1(admin_client)
        key = self._session_key_from_redirect(r1)
        response = self._do_step2_get(admin_client, key)
        assert response.status_code == 200
        assert response.context["step"] == 2
        col_names = [c["name"] for c in response.context["columns"]]
        assert "recorded_at" in col_names

    def test_map_columns_auto_maps_subject_name_column(self, admin_client):
        csv_with_subject = "recorded_at,latitude,longitude,subject_name\n2024-01-01T00:00:00Z,1.0,2.0,Lion\n"
        r1 = self._do_step1(admin_client, csv_with_subject)
        key = self._session_key_from_redirect(r1)
        response = self._do_step2_get(admin_client, key)
        autos = {c["name"]: c["auto"] for c in response.context["columns"]}
        assert autos["subject_name"] == "subject_name"

    def test_map_columns_missing_required_shows_error(self, admin_client):
        r1 = self._do_step1(admin_client, MINIMAL_CSV)
        key = self._session_key_from_redirect(r1)
        response = admin_client.post(
            self._map_url(),
            {
                "temp_key": key,
                "map_latitude": "latitude",
                "map_longitude": "longitude",
                # recorded_at omitted
            },
        )
        assert response.status_code == 200
        assert response.context["step"] == 2
        assert "recorded_at" in response.context["error"]

    def test_map_columns_with_subject_name_queues_task_directly(self, admin_client):
        csv_with_subject = "recorded_at,latitude,longitude,subject_name\n2024-01-01T00:00:00Z,1.0,2.0,Lion\n"
        r1 = self._do_step1(admin_client, csv_with_subject)
        key = self._session_key_from_redirect(r1)
        with patch("observations.admin.ObservationAdmin._csv_queue_task") as mock_queue:
            response = admin_client.post(
                self._map_url(),
                {
                    "temp_key": key,
                    "map_recorded_at": "recorded_at",
                    "map_latitude": "latitude",
                    "map_longitude": "longitude",
                    "map_subject_name": "subject_name",
                },
            )
        assert response.status_code == 302
        assert "import-csv" in response["Location"]
        mock_queue.assert_called_once()
        _, kwargs = mock_queue.call_args
        assert kwargs.get("subject_name_col") is True

    def test_map_columns_without_subject_name_redirects_to_select_subject(self, admin_client):
        r1 = self._do_step1(admin_client, MINIMAL_CSV)
        key = self._session_key_from_redirect(r1)
        response = admin_client.post(
            self._map_url(),
            {
                "temp_key": key,
                "map_recorded_at": "recorded_at",
                "map_latitude": "latitude",
                "map_longitude": "longitude",
            },
        )
        assert response.status_code == 302
        assert "select-subject" in response["Location"]

    # Step 3 ──────────────────────────────────────────────────────────────────

    def test_select_subject_get_renders_subjects(self, admin_client):
        subject = SubjectFactory()
        r1 = self._do_step1(admin_client, MINIMAL_CSV)
        key = self._session_key_from_redirect(r1)
        # Advance to step 2 to store mappings in session
        admin_client.post(
            self._map_url(),
            {
                "temp_key": key,
                "map_recorded_at": "recorded_at",
                "map_latitude": "latitude",
                "map_longitude": "longitude",
            },
        )
        response = admin_client.get(f"{self._select_url()}?key={key}")
        assert response.status_code == 200
        assert response.context["step"] == 3
        subject_names = [s.name for s in response.context["subjects"]]
        assert subject.name in subject_names

    def test_select_subject_post_queues_task_and_redirects(self, admin_client):
        subject = SubjectFactory()
        r1 = self._do_step1(admin_client, MINIMAL_CSV)
        key = self._session_key_from_redirect(r1)
        admin_client.post(
            self._map_url(),
            {
                "temp_key": key,
                "map_recorded_at": "recorded_at",
                "map_latitude": "latitude",
                "map_longitude": "longitude",
            },
        )
        with patch("observations.admin.ObservationAdmin._csv_queue_task") as mock_queue:
            response = admin_client.post(
                self._select_url(),
                {
                    "temp_key": key,
                    "subject_id": str(subject.id),
                },
            )
        assert response.status_code == 302
        assert "import-csv" in response["Location"]
        mock_queue.assert_called_once()
        _, kwargs = mock_queue.call_args
        assert kwargs.get("subject_id") == str(subject.id)

    def test_select_subject_expired_session_shows_error(self, admin_client):
        response = admin_client.post(
            self._select_url(),
            {
                "temp_key": "csv_import_nonexistent",
                "subject_id": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 200
        assert response.context["step"] == 1
        assert response.context["error"]

    # Access control ──────────────────────────────────────────────────────────

    def test_requires_staff_login(self):
        from django.test import Client

        anon = Client()
        response = anon.get(self._upload_url())
        assert response.status_code == 302
        assert "/login" in response["Location"] or "/admin/login" in response["Location"]

    def test_staff_without_add_permission_is_denied(self):
        """Staff users lacking observations.add_observation cannot reach the wizard."""
        from django.test import Client

        staff_no_perms = UserFactory(is_superuser=False, is_staff=True, username="staff_no_perms")
        c = Client()
        c.force_login(staff_no_perms)
        response = c.get(self._upload_url())
        assert response.status_code == 403

    def test_changelist_contains_import_link(self, admin_client):
        url = reverse("admin:observations_observation_changelist")
        response = admin_client.get(url)
        assert response.status_code == 200
        assert "import-csv" in response.content.decode()


# ── Pending list tenant scoping ─────────────────────────────────────────────


@pytest.mark.django_db
class TestPendingListTenantScoping:
    """The pending-jobs list is shared across all staff in a tenant — not per-session."""

    @pytest.fixture
    def staff_a(self):
        return UserFactory(is_superuser=True, is_staff=True, username="staff_a")

    @pytest.fixture
    def staff_b(self):
        return UserFactory(is_superuser=True, is_staff=True, username="staff_b")

    def _client(self, user):
        from django.test import Client

        c = Client()
        c.force_login(user)
        return c

    def _pending_url(self):
        return reverse("admin:observations_observation_import_csv_pending")

    def _dismiss_url(self, task_id):
        return reverse(
            "admin:observations_observation_import_csv_dismiss",
            kwargs={"task_id": task_id},
        )

    def test_dismiss_removes_task_from_list(self, staff_a, multitenant_cache_client):
        from observations.csv_import_jobs import (
            add_pending_task,
            list_pending_tasks,
            set_job_status,
        )

        task_id = str(uuid.uuid4())
        set_job_status(task_id, "QUEUED")
        add_pending_task(task_id)
        assert task_id in list_pending_tasks()

        response = self._client(staff_a).post(self._dismiss_url(task_id))
        assert response.status_code == 200
        assert task_id not in list_pending_tasks()

    def test_pending_list_visible_across_sessions(self, staff_a, staff_b, multitenant_cache_client):
        """Two different staff users in the same tenant see the same pending list."""
        from observations.csv_import_jobs import add_pending_task, set_job_status

        task_id = str(uuid.uuid4())
        set_job_status(task_id, "QUEUED")
        add_pending_task(task_id)

        for user in (staff_a, staff_b):
            response = self._client(user).get(self._pending_url())
            assert response.status_code == 200
            assert task_id in response.json()["task_ids"]

    def test_expired_status_pruned_from_list(self, staff_a, multitenant_cache_client):
        from observations.csv_import_jobs import (
            add_pending_task,
            delete_job_status,
            list_pending_tasks,
            set_job_status,
        )

        live_id = str(uuid.uuid4())
        stale_id = str(uuid.uuid4())
        set_job_status(live_id, "QUEUED")
        set_job_status(stale_id, "QUEUED")
        add_pending_task(live_id)
        add_pending_task(stale_id)

        # Simulate the 1-hour status TTL elapsing for stale_id while it's still in the SET.
        delete_job_status(stale_id)

        result = list_pending_tasks()
        assert live_id in result
        assert stale_id not in result

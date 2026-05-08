from __future__ import annotations

from unittest.mock import patch

import pytest

from django.core.cache import cache
from django.urls import reverse
from rest_framework import status

from core.tasks import SOURCE_DELETING_CACHE_KEY, delete_source_task
from factories import ObservationFactory, SourceFactory, SubjectSourceFactory
from observations.models import (
    LatestObservationSource,
    Message,
    Observation,
    Source,
    SubjectSource,
)
from utils.tenant import get_tenant_settings


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestAsyncDelete:
    def test_delete_source_async(self, superuser_client, source, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        settings.CELERY_TASK_STORE_EAGER_RESULT = True

        delete_url = reverse("source-view", kwargs={"identifier": source.id})
        delete_url += "?async=true"

        response = superuser_client.delete(delete_url)
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert "task_id" in response.data
        assert "location" in response.data

        status_url = response.data["location"]
        status_response = superuser_client.get(status_url)
        assert status_response.status_code == status.HTTP_200_OK
        assert "status" in status_response.data
        with pytest.raises(Source.DoesNotExist):
            Source.objects.get(id=source.id)
        assert status_response.data["status"] in ("SUCCESS", "PENDING")


@pytest.mark.django_db
@pytest.mark.usefixtures("tenant_settings", "das_tenant_monkeypatch")
class TestDeleteSourceTask:
    """Direct unit tests for delete_source_task — independent of the API entrypoint
    so we can assert task-internal contracts (batching, cache cleanup, subject
    reconciliation) without coupling to view behavior."""

    def _set_marker(self, source_id):
        cache.set(SOURCE_DELETING_CACHE_KEY.format(source_id), True, 60)

    def _marker_set(self, source_id) -> bool:
        return bool(cache.get(SOURCE_DELETING_CACHE_KEY.format(source_id)))

    def _run(self, source_id):
        # TenantTask requires a `domain` kwarg — same shape as the production callers
        # (SourceAdmin.delete_model, SourceView.delete).
        delete_source_task(str(source_id), domain=get_tenant_settings().domain)

    def test_deletes_source_and_observations(self):
        source = SourceFactory()
        ObservationFactory.create_batch(3, source=source)
        self._set_marker(source.id)

        self._run(source.id)

        assert not Source.objects.filter(id=source.id).exists()
        assert not Observation.objects.filter(source_id=source.id).exists()
        assert not self._marker_set(source.id), "cache marker must be cleared on success"

    def test_clears_cache_marker_when_source_missing(self):
        # No Source row exists, but the admin set the marker before enqueueing.
        # The task must still clear the marker so the UI doesn't get stuck.
        missing_id = "00000000-0000-0000-0000-000000000000"
        self._set_marker(missing_id)

        self._run(missing_id)

        assert not self._marker_set(missing_id)

    def test_clears_cache_marker_on_unexpected_exception(self):
        # If _raw_delete raises (DB error, etc.), the marker must still be cleared
        # via try/finally — otherwise the admin refuses to show the source for the
        # full TTL even though it may still exist.
        from django.db.models.query import QuerySet

        source = SourceFactory()
        ObservationFactory(source=source)
        self._set_marker(source.id)

        with patch.object(QuerySet, "_raw_delete", side_effect=RuntimeError("simulated DB failure")):
            with pytest.raises(RuntimeError):
                self._run(source.id)

        assert not self._marker_set(source.id), "cache marker must be cleared even on exception"

    def test_enqueues_one_subject_status_task_per_subject(self):
        source = SourceFactory()
        # Two distinct SubjectSource rows pointing at this source.
        ss_a = SubjectSourceFactory(source=source)
        ss_b = SubjectSourceFactory(source=source)
        # Many observations — should NOT result in per-observation enqueue.
        ObservationFactory.create_batch(5, source=source)
        self._set_marker(source.id)

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async") as mock_apply:
            self._run(source.id)

        enqueued_subject_ids = {call.kwargs["args"][0] for call in mock_apply.call_args_list}
        assert enqueued_subject_ids == {str(ss_a.subject_id), str(ss_b.subject_id)}
        assert mock_apply.call_count == 2, "must enqueue exactly once per unique subject, not per observation"

    def test_cascades_to_subjectsource_and_observations(self):
        # The shared cascade helper (delete_source_cascade) must remove related rows
        # explicitly — Django's app-level on_delete=CASCADE is bypassed by
        # _raw_delete, and the deferred FK constraint would otherwise blow up at
        # COMMIT in production.
        source = SourceFactory()
        ss = SubjectSourceFactory(source=source)
        ObservationFactory.create_batch(2, source=source)
        self._set_marker(source.id)

        # Don't actually fire the per-subject enqueue, just verify the cascade.
        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            self._run(source.id)

        assert not Source.objects.filter(id=source.id).exists()
        assert not Observation.objects.filter(source_id=source.id).exists()
        assert not SubjectSource.objects.filter(
            id=ss.id
        ).exists(), (
            "SubjectSource must be cleaned up explicitly — _raw_delete on Source does not cascade at the DB level"
        )

    def test_nulls_message_device_on_source_delete(self):
        # Message.device is a SET_NULL FK to Source. Without explicit cleanup,
        # _raw_delete on Source leaves dangling references and the deferred FK
        # constraint fails at COMMIT in production.
        from datetime import datetime, timezone

        source = SourceFactory()
        # Build the Message directly — MessageFactory carries stale fields.
        message = Message.objects.create(
            device=source,
            text="ping",
            message_type="outbox",
            message_time=datetime.now(tz=timezone.utc),
        )
        assert message.device_id == source.id, "precondition: message points at source"
        self._set_marker(source.id)

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            self._run(source.id)

        message.refresh_from_db()
        assert message.device_id is None, "Message.device must be nulled when its Source is deleted"
        assert not Source.objects.filter(id=source.id).exists()

    def test_removes_latestobservationsource_row(self):
        # LatestObservationSource has on_delete=CASCADE but Django's collector is
        # bypassed by _raw_delete. The helper must drop the row explicitly so the
        # cascade contract is self-contained, not dependent on a DB trigger.
        source = SourceFactory()
        # Creating an Observation triggers the DB-side LatestObservationSource maintenance.
        ObservationFactory(source=source)
        # Defensive: ensure the trigger ran. If the test infra doesn't fire triggers,
        # create the row manually so we still cover the explicit-delete code path.
        if not LatestObservationSource.objects.filter(source_id=source.id).exists():
            obs = Observation.objects.filter(source_id=source.id).first()
            LatestObservationSource.objects.create(source=source, observation=obs, recorded_at=obs.recorded_at)
        self._set_marker(source.id)

        with patch("observations.tasks.maintain_subjectstatus_for_subject.apply_async"):
            self._run(source.id)

        assert not LatestObservationSource.objects.filter(source_id=source.id).exists()
        assert not Source.objects.filter(id=source.id).exists()

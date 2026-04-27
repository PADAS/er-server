"""Performance-oriented Source deletion that bypasses Django's ORM collector.

Background: Django's ``on_delete=CASCADE`` is enforced in Python by the ORM
collector — which loads every cascade row into memory and fires a
``post_delete`` signal per row. For a Source with 100k+ Observations this is
catastrophically slow. Using ``_raw_delete`` skips the collector but also
skips Django's cascade logic, so the related tables must be deleted here
explicitly. The PostgreSQL FK constraints Django creates by default are
``DEFERRABLE INITIALLY DEFERRED``, meaning a missed cascade row only
manifests as a violation at COMMIT — easy to ship a regression that looks
fine in tests.

Shared by:
  - ``core.tasks.delete_source_task`` (admin/API async deletion)
  - ``observations.management.commands.purge_observation`` (CLI bulk purge)

Callers are responsible for enqueueing per-subject status reconciliation —
different call sites enqueue at different scopes.
"""

from __future__ import annotations

import logging
import uuid

from django.db import transaction

logger = logging.getLogger(__name__)

OBSERVATION_DELETE_BATCH_SIZE = 10_000


def delete_source_cascade(
    source_id: str | uuid.UUID,
    *,
    delete_subject_sources: bool = True,
    log_label: str | None = None,
) -> tuple[int, list[uuid.UUID]]:
    """Delete a Source plus everything that references it.

    Args:
        source_id: PK of the Source to delete.
        delete_subject_sources: If False, skips SubjectSource cleanup. Used by
            ``purge_observation.remove_subject``, which removes the subject's
            SubjectSource rows up-front before iterating sources.
        log_label: Human-readable label used in log lines (e.g. manufacturer
            id). Defaults to the source id.

    Returns:
        ``(observations_deleted, affected_subject_ids)``. Returns ``(0, [])``
        if the Source no longer exists.
    """
    from observations.models import (
        LatestObservationSource,
        Message,
        Observation,
        Source,
        SubjectSource,
    )
    from tracking.models import SourcePlugin

    label = log_label or str(source_id)

    source = Source.objects.filter(id=source_id).first()
    if source is None:
        logger.warning("Source %s does not exist; skipping cascade delete", label)
        return 0, []

    # Capture affected subjects BEFORE any deletion so the caller can reconcile
    # SubjectStatus after the cascade has run.
    subject_ids = list(
        SubjectSource.objects.filter(source_id=source_id).values_list("subject_id", flat=True).distinct()
    )

    if delete_subject_sources:
        _raw_delete(SubjectSource.objects.filter(source_id=source_id))

    # Drop M2M group memberships via the through-table.
    source.groups.clear()

    # Null out Message.device (SET_NULL FK). Without this, _raw_delete on Source
    # leaves dangling references and the deferred FK constraint fails at COMMIT.
    Message.objects.filter(device_id=source_id).update(device=None)

    # Remove the LatestObservationSource row explicitly. The model is normally
    # maintained by DB triggers, but we don't want the cascade contract to depend
    # on a trigger we don't control — drop it here so the helper is self-contained.
    _raw_delete(LatestObservationSource.objects.filter(source_id=source_id))

    # Batch-delete observations to avoid one long-running DB transaction; each
    # batch is its own atomic block so a failure mid-deletion still commits the
    # progress made so far.
    obs_qs = Observation.objects.filter(source_id=source_id)
    db = obs_qs.db
    deleted_total = 0
    while True:
        with transaction.atomic(using=db):
            ids = list(obs_qs.values_list("id", flat=True)[:OBSERVATION_DELETE_BATCH_SIZE])
            if not ids:
                break
            Observation.objects.filter(id__in=ids)._raw_delete(db)
        deleted_total += len(ids)
        logger.info("Deleted %d observation(s) for source %s (%d total)", len(ids), label, deleted_total)

    _raw_delete(SourcePlugin.objects.filter(source_id=source_id))
    _raw_delete(Source.objects.filter(id=source_id))
    logger.info("Removed source %s (%d observations)", label, deleted_total)

    return deleted_total, subject_ids


def _raw_delete(qs) -> None:
    qs._raw_delete(qs.db)

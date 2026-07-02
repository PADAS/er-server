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

from django_multitenant.utils import get_current_tenant

from django.db import connections, transaction

from observations.models import (
    LatestObservationSource,
    Message,
    Observation,
    ObservationSegment,
    Source,
    SubjectSource,
)
from tracking.models import SourcePlugin

logger = logging.getLogger(__name__)

OBSERVATION_DELETE_BATCH_SIZE = 10_000


def _delete_observations_and_segments(
    source_id: str | uuid.UUID,
    label: str,
) -> int:
    """Raw-delete ObservationSegments and Observations for a source.

    ObservationSegment has no direct FK to Source; it references Observations
    via start_observation and end_observation (both TenantForeignKey with
    on_delete=CASCADE).  Because we use server-side batched deletes to skip the
    ORM collector, those cascade rules are bypassed.  The FK constraints are
    DEFERRABLE INITIALLY DEFERRED, so the violation only surfaces at COMMIT —
    not in tests that roll back.  We must therefore drop segments explicitly
    before deleting observations.

    Returns the total number of observations deleted.
    """
    tenant = get_current_tenant()
    if tenant is None:
        raise RuntimeError(
            "_delete_observations_and_segments called without a tenant context; " "raw SQL would operate cross-tenant."
        )
    tenant_id = tenant.id

    # Remove LatestObservationSource here so both delete_source_cascade and
    # delete_source_observations share the same cleanup point.
    _raw_delete(LatestObservationSource.objects.filter(source_id=source_id))

    # ObservationSegment references Observations via start_observation_id and
    # end_observation_id (both TenantForeignKey, on_delete=CASCADE).  The
    # server-side batched delete on Observation bypasses the ORM cascade, so
    # segments that reference those observations would dangle and violate the
    # deferred FK at COMMIT.  Delete them in bounded batches before the
    # observations are removed.
    #
    # The match condition: a segment belongs to this source if either its
    # start_observation or end_observation is an observation for this source.
    # ObservationSegment has no direct FK to Source, so we EXISTS-join to the
    # Observation table on the tenant-scoped composite FK columns.
    seg_table = ObservationSegment._meta.db_table
    obs_table = Observation._meta.db_table
    seg_db = ObservationSegment.objects.db

    seg_sql = f"""
        DELETE FROM {seg_table} seg
        USING (
            SELECT seg_inner.das_tenant_id, seg_inner.id
            FROM {seg_table} seg_inner
            WHERE seg_inner.das_tenant_id = %s
              AND EXISTS (
                  SELECT 1 FROM {obs_table} ob
                  WHERE ob.das_tenant_id = seg_inner.das_tenant_id
                    AND ob.id IN (
                        seg_inner.start_observation_id,
                        seg_inner.end_observation_id
                    )
                    AND ob.source_id = %s
              )
            LIMIT %s
        ) sub
        WHERE seg.das_tenant_id = sub.das_tenant_id
          AND seg.id = sub.id
    """

    seg_deleted_total = 0
    while True:
        with transaction.atomic(using=seg_db):
            with connections[seg_db].cursor() as cursor:
                cursor.execute(seg_sql, [tenant_id, source_id, OBSERVATION_DELETE_BATCH_SIZE])
                batch_count = cursor.rowcount
        if batch_count == 0:
            break
        seg_deleted_total += batch_count
        logger.info(
            "Deleted %d observation segment(s) for source %s (%d total)",
            batch_count,
            label,
            seg_deleted_total,
        )

    # Delete Observations in bounded server-side batches.  Each batch is a
    # self-contained DELETE … USING (SELECT … LIMIT N) that never ships UUIDs
    # to Python, keeping per-batch transaction size small and allowing a
    # mid-run failure to preserve prior progress.
    obs_db = Observation.objects.db

    obs_sql = f"""
        DELETE FROM {obs_table} o
        USING (
            SELECT das_tenant_id, id
            FROM {obs_table}
            WHERE das_tenant_id = %s
              AND source_id = %s
            LIMIT %s
        ) sub
        WHERE o.das_tenant_id = sub.das_tenant_id
          AND o.id = sub.id
    """

    deleted_total = 0
    while True:
        with transaction.atomic(using=obs_db):
            with connections[obs_db].cursor() as cursor:
                cursor.execute(obs_sql, [tenant_id, source_id, OBSERVATION_DELETE_BATCH_SIZE])
                batch_count = cursor.rowcount
        if batch_count == 0:
            break
        deleted_total += batch_count
        logger.info(
            "Deleted %d observation(s) for source %s (%d total)",
            batch_count,
            label,
            deleted_total,
        )

    return deleted_total


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

    deleted_total = _delete_observations_and_segments(source_id, label)

    _raw_delete(SourcePlugin.objects.filter(source_id=source_id))
    _raw_delete(Source.objects.filter(id=source_id))
    logger.info("Removed source %s (%d observations)", label, deleted_total)

    return deleted_total, subject_ids


def delete_source_observations(
    source_id: str | uuid.UUID,
    *,
    log_label: str | None = None,
) -> tuple[int, list[uuid.UUID]]:
    """Delete all Observations (and their ObservationSegments and LatestObservationSource)
    for a Source while keeping the Source row itself and its SubjectSource /
    SourcePlugin / group memberships intact.

    Args:
        source_id: PK of the Source whose observations should be deleted.
        log_label: Human-readable label used in log lines. Defaults to the
            source id.

    Returns:
        ``(observations_deleted, affected_subject_ids)``. Returns ``(0, [])``
        if the Source no longer exists.
    """

    label = log_label or str(source_id)

    source = Source.objects.filter(id=source_id).first()
    if source is None:
        logger.warning("Source %s does not exist; skipping observation delete", label)
        return 0, []

    # Capture affected subjects BEFORE any deletion so the caller can reconcile
    # SubjectStatus after observations are gone.
    subject_ids = list(
        SubjectSource.objects.filter(source_id=source_id).values_list("subject_id", flat=True).distinct()
    )

    deleted_total = _delete_observations_and_segments(source_id, label)
    logger.info("Removed observations for source %s (%d observations)", label, deleted_total)

    return deleted_total, subject_ids


def _raw_delete(qs) -> None:
    qs._raw_delete(qs.db)

from __future__ import annotations

import csv
import io
import json
import logging
import random
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import xmltodict
from celery_once import QueueOnce
from django_multitenant.utils import get_current_tenant
from google.api_core import exceptions
from google.cloud import storage

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models import F, Max, Min
from django.utils.translation import gettext as _

import utils.db.task_helpers as utils_db_task_helpers
import utils.stats as stats
from das_server import celery, pubsub
from observations.csv_import_jobs import set_job_status
from observations.materialized_views import patrols_view
from observations.message_adapters import SendError, _handle_outbox_message
from observations.models import (
    DEFAULT_ASSIGNED_RANGE,
    Announcement,
    GPXTrackFile,
    Observation,
    ObservationSegment,
    Source,
    SourceProvider,
    Subject,
    SubjectSource,
    SubjectStatus,
)
from observations.serializers import ObservationSerializer
from observations.utils import dateparse
from utils.cache import bump_observation_segment_tile_version
from utils.tenant.celery import OverAllTenantTask, TenantQueueOnceTask, TenantTask

# NOTE: ``observations.signals`` imports from this module at load time, so anything we need
# from there has to be imported inside the function bodies below — top-level imports here
# would deadlock the module load.

logger = logging.getLogger(__name__)

MAX_MAINTAIN_SUBJECTSTATUS_DELAY_SECONDS = 600


def _emit_segment_task_metrics(
    metric_prefix: str,
    domain: str | None,
    batch_size: int,
    oldest_recorded_at: datetime | None,
    duration_ms: float,
) -> None:
    """Emit lag/throughput metrics for a segment maintenance task.

    - ``observation_segment.<prefix>.batch_size``: per-task batch cardinality.
    - ``observation_segment.<prefix>.lag_seconds``: now - oldest obs.recorded_at; proxy for end-to-end
      freshness (observation insert → segment row).
    - ``observation_segment.<prefix>.duration_ms``: wall-clock processing time.
    - ``observation_segment.<prefix>.backlog_threshold_breach``: incremented when lag exceeds
      ``OBSERVATION_SEGMENT_BACKLOG_LAG_WARN_SECONDS`` so log-based alerts can fire.
    """
    tags = [f"domain:{domain}"] if domain else []
    stats.histogram(f"observation_segment.{metric_prefix}.batch_size", batch_size, tags=tags)
    stats.histogram(f"observation_segment.{metric_prefix}.duration_ms", duration_ms, tags=tags)

    if oldest_recorded_at is None:
        return
    lag_seconds = (datetime.now(tz=timezone.utc) - oldest_recorded_at).total_seconds()
    stats.histogram(f"observation_segment.{metric_prefix}.lag_seconds", lag_seconds, tags=tags)
    threshold = int(getattr(django_settings, "OBSERVATION_SEGMENT_BACKLOG_LAG_WARN_SECONDS", 300))
    if lag_seconds > threshold:
        stats.increment(f"observation_segment.{metric_prefix}.backlog_threshold_breach", tags=tags)
        logger.warning(
            "observation_segment.%s lag %.1fs exceeds threshold %ds (batch=%d, domain=%s)",
            metric_prefix,
            lag_seconds,
            threshold,
            batch_size,
            domain,
        )


def _coerce_task_datetime(value: Any) -> datetime | None:
    """Parse Celery-serialized datetimes; return None if value is missing or unparsable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        from django.utils.dateparse import parse_datetime

        parsed = parse_datetime(value)
        if parsed is None:
            logger.warning("Could not parse datetime string for segment recompute task: %r", value)
        return parsed
    return None


@celery.app.task(
    base=TenantQueueOnceTask,
    once={"graceful": True},
)
def recompute_observation_segments_task(source_id=None, lower=None, upper=None, observation_ids=None, **kwargs):
    """Single async entry point for recomputing ObservationSegments.

    Invoke with either:
      - source_id, lower, upper: recompute segments for all observations of that
        source in [lower, upper].  Bounds are clamped to the 3-year partition
        retention window and enable partition pruning on the observation table.
      - observation_ids: recompute segments for those observation IDs.  The task
        loads ``MIN``/``MAX`` ``recorded_at`` for those IDs (one aggregate query),
        merges optional ``lower``/``upper`` kwargs so the window always covers
        every listed row, clamps to the 3-year retention window, then runs the
        main fetch with ``recorded_at`` bounds so PostgreSQL can prune
        partitions.  Optional ``lower``/``upper`` hint a wider window when the
        caller already knows it (e.g. ingest batch time range).

    Used by SubjectSource signals (source_id + range) and by the backfill command.

    The per-tenant segment tile version is bumped **after** the full recompute
    completes; during a long-running job, tiles may be stale until it finishes.
    """
    from observations.signals import (
        _clamp_recompute_bounds,
        recompute_observation_segments,
        recompute_observation_segments_for_source_range,
    )

    if source_id is not None and lower is not None and upper is not None:
        lower_dt = _coerce_task_datetime(lower)
        upper_dt = _coerce_task_datetime(upper)
        if lower_dt is None or upper_dt is None:
            logger.warning(
                "recompute_observation_segments_task: invalid lower/upper for source_id path: %r, %r",
                lower,
                upper,
            )
            return
        recompute_observation_segments_for_source_range(source_id, lower_dt, upper_dt)
    elif observation_ids:
        uuids: list[UUID] = []
        for oid in observation_ids:
            try:
                uuids.append(UUID(str(oid)))
            except ValueError:
                logger.warning("Invalid observation_id for recompute task: %s", oid)
        if not uuids:
            return

        # Don't shadow the imported ``utils.stats`` module — name this aggregate result distinctly.
        range_stats = Observation.objects.filter(pk__in=uuids).aggregate(
            mn=Min("recorded_at"),
            mx=Max("recorded_at"),
        )
        mn, mx = range_stats["mn"], range_stats["mx"]
        if mn is None or mx is None:
            logger.warning("recompute_observation_segments_task: no rows for observation_ids")
            return

        lo, hi = mn, mx
        lower_dt = _coerce_task_datetime(lower)
        upper_dt = _coerce_task_datetime(upper)
        if lower_dt is not None:
            lo = min(lo, lower_dt)
        if upper_dt is not None:
            hi = max(hi, upper_dt)

        lo, hi = _clamp_recompute_bounds(lo, hi)
        recompute_observation_segments(uuids, lower=lo, upper=hi)
    else:
        logger.warning("recompute_observation_segments_task called with no source_id+range or observation_ids")
        return

    tenant = get_current_tenant()
    if tenant:
        bump_observation_segment_tile_version(str(tenant.id))


@celery.app.task(base=TenantTask)
def update_observation_segments_for_observation_task(observation_id: str | UUID, created: bool, **kwargs: Any) -> None:
    """Maintain ObservationSegments for one observation after save.

    Kept for in-flight Celery messages; new post-save work uses
    ``update_observation_segments_batch_task``.

    TODO(ERA-12969): remove after the release that ships this PR has been deployed
    long enough for the realtime_p3 queue to drain its old single-id messages
    (typically one full deploy cycle).  No producer in this codebase still enqueues
    this task — the only callers are pre-deploy messages still in flight.

    Runs in tenant context (domain in kwargs).  Loads the observation by id and
    calls update_segments_for_observation; if the row was deleted before the task
    runs, exits quietly.

    Enqueued from observation_segment_post_save with queue=realtime_p3 for creates
    and updates (legacy single-id path).

    For updates (``created=False``), bumps the per-tenant segment tile version so
    cached tiles become stale.  Creates rely on natural TTL expiry.
    """
    # observations.signals imports from observations.tasks at module load — cycle.
    from observations.signals import (
        RECOMPUTE_OBSERVATION_ONLY_FIELDS,
        update_segments_for_observation,
    )

    try:
        obs_uuid = UUID(str(observation_id))
    except ValueError:
        logger.warning("Invalid observation_id for segment task: %s", observation_id)
        return

    started = time.monotonic()
    obs = Observation.objects.filter(pk=obs_uuid).only(*RECOMPUTE_OBSERVATION_ONLY_FIELDS).first()
    if obs is None:
        logger.debug("Observation %s not found; skipping segment update", observation_id)
        return
    update_segments_for_observation(obs, created=created)

    if not created:
        bump_observation_segment_tile_version(str(obs.das_tenant_id))

    _emit_segment_task_metrics(
        metric_prefix="single",
        domain=kwargs.get("domain"),
        batch_size=1,
        oldest_recorded_at=obs.recorded_at,
        duration_ms=(time.monotonic() - started) * 1000.0,
    )


@celery.app.task(base=TenantTask)
def update_observation_segments_batch_task(observation_ids: list[str], created: bool, **kwargs: Any) -> None:
    """Maintain ObservationSegments for many observations after save (batched post-save path).

    Loads all rows in one query, sorts by ``(subject_id, recorded_at, pk)`` in Python so
    neighbor work runs in chronological order per subject. For ``created=False``, bumps
    the segment tile version at most once for the whole batch (same net effect as N
    single-id tasks without multiplying bumps).

    Emits ``observation_segment.batch.*`` metrics — see ``_emit_segment_task_metrics``.

    ``domain`` must be passed in kwargs for :class:`TenantTask`.
    """
    # observations.signals imports from observations.tasks at module load — cycle.
    from observations.signals import (
        RECOMPUTE_OBSERVATION_ONLY_FIELDS,
        get_subject_for_observation,
        update_segments_for_observation,
    )

    if not observation_ids:
        return

    uuids: list[UUID] = []
    for oid in observation_ids:
        try:
            uuids.append(UUID(str(oid)))
        except ValueError:
            logger.warning("Invalid observation_id in batch segment task: %s", oid)

    if not uuids:
        return

    started = time.monotonic()
    observations = list(Observation.objects.filter(pk__in=uuids).only(*RECOMPUTE_OBSERVATION_ONLY_FIELDS))

    def sort_key(obs: Observation) -> tuple[str, datetime, UUID]:
        subj = get_subject_for_observation(obs)
        sid = str(subj.pk) if subj else ""
        return (sid, obs.recorded_at, obs.pk)

    observations.sort(key=sort_key)

    for obs in observations:
        update_segments_for_observation(obs, created=created)

    if not created:
        tenant = get_current_tenant()
        if tenant:
            bump_observation_segment_tile_version(str(tenant.id))
        elif observations:
            bump_observation_segment_tile_version(str(observations[0].das_tenant_id))

    duration_ms = (time.monotonic() - started) * 1000.0
    oldest = min((o.recorded_at for o in observations), default=None)
    _emit_segment_task_metrics(
        metric_prefix="batch",
        domain=kwargs.get("domain"),
        batch_size=len(observations),
        oldest_recorded_at=oldest,
        duration_ms=duration_ms,
    )


@celery.app.task(base=TenantTask)
def bump_observation_segment_tile_cache_for_tenant_task(**kwargs: Any) -> None:
    """Increment per-tenant segment tile version (O(1) Redis INCR).

    Invalidates observation segment MVT keys (they embed the version) without SCAN.
    Used when operators run ``manage.py bust_observation_tile_cache --enqueue``.
    """
    tenant = get_current_tenant()
    if not tenant:
        logger.warning("bump_observation_segment_tile_cache_for_tenant_task: no current tenant in context")
        return
    bump_observation_segment_tile_version(str(tenant.id))


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def reconcile_observation_segments_task(**kwargs: Any) -> None:
    """Daily safety net: detect and rebuild segment gaps in the recent window.

    For each tenant the OverAllTenantTask runs as, walks every source that had
    activity in the last ``OBSERVATION_SEGMENT_RECONCILE_HOURS`` hours.  Quick gap
    check first: ``count(valid_obs) - 1`` should equal ``count(segments)`` for the
    window.  When the counts diverge we run ``recompute_observation_segments_for_source_range``,
    which is idempotent (``select_for_update`` + ``IntegrityError`` fallback).

    Closes the gap left by paths that bypass post_save (bulk update on
    ``exclusion_flags`` is the known case; this catches the unknowns).

    Logging:
        - Per-source gap: ``WARNING`` (one line per affected source) so log-based
          alerts can fire without metrics access.
        - End-of-run summary: ``WARNING`` if any gaps were found, ``INFO`` otherwise.

    Emits:
        - ``observation_segment.reconcile.sources_checked``
        - ``observation_segment.reconcile.gaps_detected``
        - ``observation_segment.reconcile.duration_ms``
        - ``observation_segment.reconcile.gap_detected`` (counter, only on gap)
    """
    # observations.signals imports from observations.tasks at module load — cycle.
    from observations.signals import recompute_observation_segments_for_source_range

    tenant = get_current_tenant()
    if not tenant:
        logger.warning("reconcile_observation_segments_task: no current tenant; skipping")
        return

    domain = getattr(tenant, "domain", None)
    tags = [f"domain:{domain}"] if domain else []

    started = time.monotonic()
    hours = int(getattr(django_settings, "OBSERVATION_SEGMENT_RECONCILE_HOURS", 6))
    upper = datetime.now(tz=timezone.utc)
    lower = upper - timedelta(hours=hours)

    # Clear Meta.ordering so DISTINCT operates on source_id only (otherwise the
    # implicit ORDER BY recorded_at sneaks into the SELECT list and dedupes on
    # (source_id, recorded_at), defeating the point).
    source_ids = list(
        Observation.objects.filter(recorded_at__gte=lower, recorded_at__lte=upper)
        .order_by()
        .values_list("source_id", flat=True)
        .distinct()
    )

    sources_checked = 0
    gaps_detected = 0
    for source_id in source_ids:
        sources_checked += 1
        valid_obs_count = (
            Observation.objects.filter(
                source_id=source_id,
                recorded_at__gte=lower,
                recorded_at__lte=upper,
                location__isnull=False,
            )
            .by_exclusion_flags(filter_flag=0, include_empty_location=False)
            .count()
        )
        if valid_obs_count < 2:
            continue

        segment_count = ObservationSegment.objects.filter(
            start_observation__source_id=source_id,
            start_recorded_at__gte=lower,
            end_recorded_at__lte=upper,
        ).count()

        if segment_count >= valid_obs_count - 1:
            continue

        gaps_detected += 1
        logger.warning(
            "reconcile: gap detected domain=%s source=%s window=%dh valid_obs=%d segments=%d (rebuilding)",
            domain,
            source_id,
            hours,
            valid_obs_count,
            segment_count,
        )
        try:
            recompute_observation_segments_for_source_range(str(source_id), lower, upper)
        except Exception:
            logger.exception("reconcile_observation_segments_task: recompute failed for source %s", source_id)

    duration_ms = (time.monotonic() - started) * 1000.0
    stats.histogram("observation_segment.reconcile.sources_checked", sources_checked, tags=tags)
    stats.histogram("observation_segment.reconcile.gaps_detected", gaps_detected, tags=tags)
    stats.histogram("observation_segment.reconcile.duration_ms", duration_ms, tags=tags)
    if gaps_detected:
        stats.increment("observation_segment.reconcile.gap_detected", value=gaps_detected, tags=tags)
        logger.warning(
            "reconcile complete domain=%s sources_checked=%d gaps=%d duration_ms=%.0f window=%dh",
            domain,
            sources_checked,
            gaps_detected,
            duration_ms,
            hours,
        )
    else:
        logger.info(
            "reconcile complete domain=%s sources_checked=%d gaps=0 duration_ms=%.0f window=%dh",
            domain,
            sources_checked,
            duration_ms,
            hours,
        )


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def maintain_subjectstatus_all():
    for subject_id in Subject.objects.filter(is_active=True).values_list("id", flat=True):
        maintain_subjectstatus_for_subject.apply_async(
            args=(str(subject_id),),
            countdown=random.randint(0, MAX_MAINTAIN_SUBJECTSTATUS_DELAY_SECONDS),
        )


@celery.app.task(
    base=TenantQueueOnceTask,
    once={
        "graceful": True,
    },
)
def maintain_subjectstatus_for_subject(subject_id, notify=False, **kwargs):
    """
    Maintenance task to ensure the subjectstatus is up to date for a subject.
    """
    SubjectStatus.objects.maintain_subject_status(subject_id)

    if notify:
        pubsub.publish({"subject_id": str(subject_id)}, "das.subjectstatus.update")


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def maintain_observation_data():
    """Maintain observation data for all SourceProviders if they have the
    days_data_retain setting. For each matching SourceProvider a task maintain_observation_data_for_source_provider
    is queued.
    """
    for ssprovider in SourceProvider.objects.annotate(unique_id=F("id")):
        days_data_retain = ssprovider.additional.get("days_data_retain")
        if not days_data_retain:
            continue

        try:
            days_data_retain = int(days_data_retain)
        except ValueError:
            logger.warning(
                "Mis-configured field days_data_retain %s not an integer for source_provider: %s",
                days_data_retain,
                ssprovider.display_name,
            )
            continue

        maintain_observation_data_for_source_provider.apply_async(args=(ssprovider.unique_id, days_data_retain))


DAYS_BACK_TO_SEARCH_OBSERVATION_PARTITIONS = 365


@celery.app.task(
    base=TenantQueueOnceTask,
    bind=True,
    once={
        "graceful": True,
    },
)
def maintain_observation_data_for_source_provider(
    self,
    source_provider_id: str,
    days_data_retain: int,
    search_back_days: int = DAYS_BACK_TO_SEARCH_OBSERVATION_PARTITIONS,
    **kwargs,
):
    """
    Delete observation records older than days_data_retain for a source_provider.
    Only go back DAYS_BACK_TO_SEARCH_OBSERVATION_PARTITIONS days to not search all Observation table partitions
    """
    if search_back_days < days_data_retain:
        logger.warning(
            "search_back_days %s is less than days_data_retain %s for source_provider_id: %s",
            search_back_days,
            days_data_retain,
            source_provider_id,
        )
        return

    current_datetime = datetime.now(timezone.utc)
    minimum_date = current_datetime - timedelta(days=days_data_retain)
    minimum_observation_partition_lower_bound = current_datetime - timedelta(days=search_back_days)

    logger.info(f"Deleting observation records older than {minimum_date} for source_provider_id: {source_provider_id}")

    for source_id in Source.objects.filter(provider_id=source_provider_id).values_list("id", flat=True):
        # Observation records older than minimum date
        observation_queryset = Observation.objects.filter(
            source_id=source_id,
            recorded_at__lte=minimum_date,
            recorded_at__gte=minimum_observation_partition_lower_bound,
        )

        observation_queryset.delete()


def parse_xml_to_dict(xml):
    try:
        xml_todict = xmltodict.parse(xml)
    except Exception as exc:
        message = f"Error occurred when parsing gpx file: {str(exc)} "
        logger.exception(message)
        return message
    else:
        to_json = json.dumps(xml_todict)
        return json.loads(to_json)


def _collect_trkpts(seg):
    """Return a list of trackpoint dicts from a trkseg (segment) dict."""
    trkpt = seg.get("trkpt")
    if trkpt is None:
        return []
    if isinstance(trkpt, dict):
        return [trkpt]
    return list(trkpt)


def get_track_points(gpx):
    """Extract trackpoints from parsed GPX. Handles multiple trk/trkseg (xmltodict lists)."""
    try:
        root = gpx.get("gpx") or gpx
        trk = root.get("trk")
        if trk is None:
            return "No track points were found in the file."

        tracks = trk if isinstance(trk, list) else [trk]
        points = []
        for t in tracks:
            seg = t.get("trkseg")
            if seg is None:
                continue
            segments = seg if isinstance(seg, list) else [seg]
            for s in segments:
                points.extend(_collect_trkpts(s))

        if not points:
            return "No track points were found in the file."
        return points
    except Exception as exc:
        message = f"Error occurred when getting trackpoints from gpx file: {str(exc)}"
        logger.exception(message)
        return message


def get_array_recorded_time(src, array_recorded_at):
    """Returns an array of trackpoints datetime that does not exist in observation table"""
    arr_obs = Observation.objects.filter(source=src, recorded_at__in=array_recorded_at).values_list(
        "recorded_at", flat=True
    )
    arr_recorded_at = set(array_recorded_at).difference(set(arr_obs))
    return arr_recorded_at


def validate_observation(location, recorded_at, source_id, additional, obs_persist, obs_errors):
    observation = {
        "location": location,
        "recorded_at": recorded_at,
        "source": str(source_id),
        "additional": additional,
    }
    validator = ObservationSerializer(data=observation)
    if validator.is_valid():
        obs_persist.append(observation)
        logger.debug(f"Added new observation record {observation}")
    else:
        obs_errors.append(validator.errors)
        logger.error(f"Observation validation failed {validator.errors}")


def process_observation(observation_records, observation_errors):
    if observation_records:
        bulk_serializer = ObservationSerializer(data=observation_records, many=True)
        if bulk_serializer.is_valid():
            bulk_serializer.save()
            message = f"Successfully created {len(observation_records)} observations"
            logger.info(message)
            return True, message
        else:
            message = f"Failed to process bulk observation: {bulk_serializer.errors}"
            logger.error(message)
            return False, message
    elif observation_errors:
        message = f"Failed to process observation: {observation_errors}"
        logger.error(message)
        return False, message
    else:
        message = "Observations records already exists"
        return True, message


def process_trackpoints(source, source_id, trkpoints, file_name):
    error_msg = None

    try:
        list_gpx_datetime = [dateparse(trkp.get("time")) for trkp in trkpoints]
    except TypeError:
        error_msg = _("Points are missing timestamps in GPX file %s") % (file_name,)
    except Exception as exc:
        error_msg = _("Invalid timestamp, %s") % (exc,)

    if error_msg:
        return None, error_msg

    array_datetime = get_array_recorded_time(source, list_gpx_datetime)

    obs_records = []
    obs_errors = []
    for trkpt in trkpoints:
        recorded_at = dateparse(trkpt.get("time"))
        if recorded_at in array_datetime:
            lat = trkpt.get("@lat")
            lon = trkpt.get("@lon")
            location = {"latitude": float(lat), "longitude": float(lon)}
            additional = get_additional(trkpt)
            validate_observation(location, recorded_at, source_id, additional, obs_records, obs_errors)
            array_datetime.remove(recorded_at)
        else:
            logger.info(f"Ignored observation record of recorded_at: {recorded_at} and source: {source}")

    return obs_records, obs_errors


def get_additional(trkpoint):
    keys = ["@lat", "@lon", "time"]
    [trkpoint.pop(i) for i in keys]
    return trkpoint


def success_process_gpxtrack(gpx_id, message):
    # get length of observations from message
    count = "".join(filter(str.isdigit, message))
    points_imported = int(count) if count else "0 (All Duplicates)"

    return GPXTrackFile.objects.filter(id=gpx_id).update(processed_status="success", points_imported=points_imported)


def failed_process_gpxtrack(gpx_id, error_msg=None):
    return GPXTrackFile.objects.filter(id=gpx_id).update(
        processed_status="failure", status_description=error_msg, points_imported=0
    )


@celery.app.task(base=TenantQueueOnceTask, once={"graceful": True})
def process_gpxtrack_file(gpx_id, **kwargs):
    gpx_file, file_name = GPXTrackFile.objects.get_file(gpx_id)
    data = gpx_file.read()
    response = parse_xml_to_dict(data)
    if isinstance(response, str):
        failed_process_gpxtrack(gpx_id, response)
        return
    trkpoints = get_track_points(response)
    if isinstance(trkpoints, str):
        failed_process_gpxtrack(gpx_id, trkpoints)
        return

    source_id = GPXTrackFile.objects.get_source_id(gpx_id)
    source = Source.objects.get(id=source_id)
    obs_records, obs_errors = process_trackpoints(source, source_id, trkpoints, file_name)

    status, message = process_observation(observation_records=obs_records, observation_errors=obs_errors)
    if status:
        success_process_gpxtrack(gpx_id, message)
    else:
        if obs_records is None:
            failed_process_gpxtrack(gpx_id, obs_errors)
        else:
            failed_process_gpxtrack(gpx_id)


def _coerce(v):
    """Convert a CSV string value to int or float if it looks numeric, else return as-is."""
    if v is None:
        return v
    try:
        int_v = int(v)
        return int_v if str(int_v) == str(v).strip() else float(v)
    except (ValueError, TypeError):
        try:
            return float(v)
        except (ValueError, TypeError):
            return v


def _process_rows_for_source(source_id, rows, mappings, col_for):
    """
    Validate and bulk-create Observation records for a single source.
    Returns (ok, message) from process_observation.
    """
    recorded_ats = []
    for row in rows:
        raw = row.get(col_for.get("recorded_at", ""), "")
        try:
            recorded_ats.append(dateparse(raw))
        except Exception:
            pass

    existing_times = set(
        Observation.objects.filter(source_id=source_id, recorded_at__in=recorded_ats).values_list(
            "recorded_at", flat=True
        )
    )

    obs_records = []
    obs_errors = []

    for row in rows:
        try:
            recorded_at = dateparse(row[col_for["recorded_at"]])
            lat = float(row[col_for["latitude"]])
            lon = float(row[col_for["longitude"]])
        except (KeyError, TypeError, ValueError) as exc:
            obs_errors.append(str(exc))
            continue

        if recorded_at in existing_times:
            continue

        additional = {col: _coerce(row.get(col)) for col, target in mappings.items() if target == "additional"}

        validate_observation(
            {"latitude": lat, "longitude": lon},
            recorded_at,
            source_id,
            additional,
            obs_records,
            obs_errors,
        )
        existing_times.add(recorded_at)

    return process_observation(observation_records=obs_records, observation_errors=obs_errors)


def _delete_storage_file(storage_path):
    """Best-effort delete of an uploaded CSV after a successful import."""
    if not storage_path:
        return
    try:
        default_storage.delete(storage_path)
    except Exception:
        logger.warning("Failed to delete CSV from storage: %s", storage_path, exc_info=True)


@celery.app.task(base=TenantTask, bind=True)
def process_csv_observations(
    self,
    storage_path,
    mappings,
    header_row=1,
    data_start_row=2,
    source_id=None,
    subject_id=None,
    subject_name_col=False,
    **kwargs,
):
    """
    Read a stored CSV from default_storage, apply column mappings, and bulk-create
    Observation records. The file is deleted on success and left in storage on
    failure for debugging.

    storage_path: path returned by default_storage.save(...) at upload time.
    mappings: {csv_column: target_field}
    target_field: recorded_at | latitude | longitude | additional | subject_name

    Modes (mutually exclusive):
      source_id       — legacy: write all rows to an existing Source
      subject_id      — create a new Source for the given Subject, write all rows
      subject_name_col=True — group rows by subject_name column; find-or-create
                              Source+Subject+SubjectSource per unique name
    """
    logger.info(
        "process_csv_observations received: task_id=%s storage_path=%s source_id=%s subject_id=%s subject_name_col=%s",
        self.request.id,
        storage_path,
        source_id,
        subject_id,
        subject_name_col,
    )
    task_id = self.request.id
    try:
        if task_id:
            set_job_status(task_id, "STARTED")

        with default_storage.open(storage_path, "rb") as f:
            csv_content = f.read().decode("utf-8-sig")

        lines = csv_content.splitlines()
        header_row = max(1, int(header_row))
        data_start_row = max(1, int(data_start_row))
        if header_row > len(lines):
            message = "No header found at the specified row."
            if task_id:
                set_job_status(task_id, "FAILURE", error=message)
            return message

        header_line = lines[header_row - 1]
        data_lines = lines[data_start_row - 1 :] if data_start_row <= len(lines) else []
        rows = list(csv.DictReader(io.StringIO(header_line + "\n" + "\n".join(data_lines))))

        col_for = {target: col for col, target in mappings.items()}

        if subject_name_col:
            # Group rows by unique subject name and process each group separately
            rows_by_subject = defaultdict(list)
            subject_col = col_for.get("subject_name", "")
            for row in rows:
                name = row.get(subject_col, "").strip()
                if name:
                    rows_by_subject[name].append(row)

            messages = []
            for sname, srows in rows_by_subject.items():
                subject, _ = Subject.objects.get_or_create(name=sname)
                source, _ = Source.objects.get_or_create(
                    manufacturer_id=sname,
                    provider_id=SourceProvider.objects.get_or_create(
                        provider_key="file-upload",
                        defaults={"display_name": "File Upload"},
                    )[0].id,
                )
                SubjectSource.objects.get_or_create(
                    source=source,
                    subject=subject,
                    defaults={"assigned_range": DEFAULT_ASSIGNED_RANGE},
                )
                ok, msg = _process_rows_for_source(source.id, srows, mappings, col_for)
                messages.append(f"{sname}: {msg}")

            message = "; ".join(messages) if messages else "No valid subject names found in CSV."
            if task_id:
                set_job_status(task_id, "SUCCESS", result=message)
            _delete_storage_file(storage_path)
            return message

        elif subject_id:
            # Create a new Source tied to the selected Subject
            subject = Subject.objects.get(id=subject_id)
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S")
            provider, _ = SourceProvider.objects.get_or_create(
                provider_key="file-upload",
                defaults={"display_name": "CSV Import"},
            )
            source = Source.objects.create(
                manufacturer_id=f"{subject.name}_{ts}",
                provider=provider,
            )
            SubjectSource.objects.create(
                source=source,
                subject=subject,
                assigned_range=DEFAULT_ASSIGNED_RANGE,
            )
            ok, message = _process_rows_for_source(source.id, rows, mappings, col_for)

        else:
            # Legacy mode: write to existing source
            source = Source.objects.get(id=source_id)
            ok, message = _process_rows_for_source(source.id, rows, mappings, col_for)

        if ok:
            if task_id:
                set_job_status(task_id, "SUCCESS", result=message)
            _delete_storage_file(storage_path)
            return message
        else:
            if task_id:
                set_job_status(task_id, "FAILURE", error=message)
            raise ValidationError(message)

    except Exception as exc:
        if task_id:
            set_job_status(task_id, "FAILURE", error=str(exc))
        raise


@celery.app.task(base=TenantQueueOnceTask, once={"graceful": True}, bind=True, track_started=True, ignore_result=False)
def process_gpxdata_api(self, filename, source_id, **kwargs):
    with default_storage.open(filename, "r") as file:
        data = file.read()

        response = parse_xml_to_dict(data)
        if isinstance(response, str):
            raise ValidationError(response)

        trkpoints = get_track_points(response)
        if isinstance(trkpoints, str):
            raise ValidationError(trkpoints)

    source = Source.objects.get(id=source_id)

    file_name = filename.split("/")[-1]
    obs_records, obs_errors = process_trackpoints(source, source_id, trkpoints, file_name)

    status, message = process_observation(observation_records=obs_records, observation_errors=obs_errors)
    if status:
        return message
    else:
        raise ValidationError(message)


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def refresh_patrols_view():
    # FIXME By the time we consolidate all tenants in one DB we require rework on the DB view that refresh_view hit.
    patrols_view.refresh_view()


@celery.app.task(base=TenantQueueOnceTask, bind=True, once={"graceful": True}, max_retries=10)
def handle_outbox_message(self, message_id, user_email, **kwargs):
    try:
        _handle_outbox_message(message_id, user_email)
    except SendError as exc:
        logger.error("SendError in task handle_outbox_message %s", exc)
        self.retry(exc=exc, retry_backoff=True)


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def poll_news_gcs_bucket():
    """poll record topics from GCS bucket"""

    blob_name = "topic_feeds.json"
    bucket_name = "er_notifications"

    try:
        storage_client = storage.Client()
    except exceptions.GoogleAPIError:
        return

    try:
        bucket = storage_client.get_bucket(bucket_name)
    except exceptions.GoogleAPIError as exc:
        logger.info(f"Error occured when getting bucket {bucket_name} -> {exc}")
        return

    with tempfile.NamedTemporaryFile(delete=False) as f:
        blob = bucket.blob(blob_name)
        storage_client.download_blob_to_file(blob, f)
        f.flush()
        f.seek(0)

        announcement = json.loads(f.read())

    logger.debug(f"Announcements data from gcs {announcement}")

    for post in announcement["topic_list"]["topics"]:
        # skip any posts missing the 'cooked' property
        if "cooked" not in post:
            continue

        # ignore announcements if they are already in the DB:
        if Announcement.objects.filter(additional__id=post["id"]).exists():
            continue

        announcement_at = dateparse(post["created_at"])
        Announcement.objects.create(
            title=post["title"],
            description=post["cooked"],
            additional=dict(
                slug=post["slug"],
                id=post["id"],
                fancy_title=post["fancy_title"],
                created_at=post["created_at"],
                category_id=post["category_id"],
                last_poster_username=post["last_poster_username"],
            ),
            announcement_at=announcement_at,
            link=f"https://community.earthranger.com/t/{post['id']}",
        )


@celery.app.task(
    base=QueueOnce,
    default_retry_delay=60,
    max_retries=5,
    retry_backoff=30,
    retry_backoff_max=10 * 60,
)
def run_partition_table_check() -> None:
    """
    Run the partition table check on the observations_observation table.
    """
    table_name = "observations_observation"
    schema = "public"
    logger.info(f"Running partition table check for '{schema}.{table_name}'")
    utils_db_task_helpers.run_partition_table_check(schema=schema, table_name=table_name, logger=logger)


@celery.app.task(
    base=QueueOnce,
    default_retry_delay=60,
    max_retries=5,
    retry_backoff=30,
    retry_backoff_max=10 * 60,
)
def run_observation_segment_partition_table_check() -> None:
    """
    Run the partition table check on the observations_observationsegment table.
    """
    table_name = "observations_observationsegment"
    schema = "public"
    logger.info(f"Running partition table check for '{schema}.{table_name}'")
    utils_db_task_helpers.run_partition_table_check(schema=schema, table_name=table_name, logger=logger)

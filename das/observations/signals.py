from __future__ import annotations

import functools
import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from django_multitenant.utils import get_current_tenant

from django.apps import apps
from django.conf import settings as django_settings
from django.contrib.auth import models
from django.contrib.auth.management import _get_all_permissions
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.models import Q
from django.db.models.fields.json import KeyTransform
from django.db.models.signals import (
    post_delete,
    post_migrate,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver

from accounts.models import PermissionSet
from core.models import DASTenant
from das_server import pubsub
from observations.models import (
    Announcement,
    Message,
    Observation,
    ObservationSegment,
    Source,
    SourceProvider,
    Subject,
    SubjectGroup,
    SubjectSource,
    SubjectStatus,
)
from observations.servicesutils import SOURCE_PROVIDER_2WAY_MSG_KEY
from observations.tasks import (
    maintain_subjectstatus_for_subject,
    update_observation_segments_batch_task,
)
from utils.cache import bump_observation_segment_tile_version
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException

logger = logging.getLogger(__name__)

OBSERVATION_SEGMENT_OBSERVATION_SIGNALS_ENABLED: bool = getattr(
    django_settings, "OBSERVATION_SEGMENT_SIGNALS_ENABLED", True
)

# Post-save segment batches (creates and updates) use realtime_p3 (see celery task_routes).
OBSERVATION_SEGMENT_ASYNC_CREATE_QUEUE = "realtime_p3"
OBSERVATION_SEGMENT_ASYNC_UPDATE_QUEUE = "realtime_p3"


@receiver(post_save, sender=Observation)
def observation_post_save(sender, instance, created, **kwargs):
    # disable the handler during fixture loading
    if kwargs["raw"]:
        return
    last_week = datetime.now(tz=timezone.utc) - timedelta(days=7)

    # If the observation is new and was recorded in the last day, update the subjectstatus.
    # Otherwise, queue a task to update the subjectstatus.
    if created and instance.recorded_at > last_week:
        SubjectStatus.objects.update_from_observation(observation=instance, created=created)
    else:
        for subjectsource in SubjectSource.objects.get_for_source_at_time(instance.source, instance.recorded_at):
            transaction.on_commit(
                lambda: maintain_subjectstatus_for_subject.apply_async(args=[str(subjectsource.subject.id)])
            )


@receiver(post_delete, sender=Observation)
def observation_post_delete(sender, instance, **kwargs):
    for subjectsource in SubjectSource.objects.get_for_source_at_time(instance.source, instance.recorded_at):
        transaction.on_commit(
            lambda: maintain_subjectstatus_for_subject.apply_async(args=[str(subjectsource.subject.id)])
        )


@receiver(post_save, sender=SubjectStatus)
def subject_status_post_save(sender, instance, created, **kwargs):
    if kwargs["raw"]:
        return

    # Looking for name change.
    if instance.delay_hours == 0:
        latest_subject_name = instance.additional.get("subject_name", None)
        if latest_subject_name and latest_subject_name != instance.subject.name:
            logger.debug("Detected subject name change from %s to %s", instance.subject.name, latest_subject_name)
            instance.subject.name = latest_subject_name
            instance.subject.save()


@receiver(post_save, sender=Subject)
def ensure_subject_status_exists(sender, **kwargs):
    if kwargs.get("created", False):
        subject = kwargs.get("instance")
        SubjectStatus.objects.ensure_for_subject(subject)


@receiver(post_save, sender=SubjectSource)
def maintain_subjectstatus(sender, instance, created, **kwargs):
    # This function is triggered when source is updated for subject.
    transaction.on_commit(lambda: maintain_subjectstatus_for_subject.apply_async(args=[instance.subject_id]))


@receiver(pre_save, sender=SubjectSource)
def subjectsource_segment_pre_save(sender, instance, **kwargs):
    """Capture previous assigned_range and subject_id so post_save can recompute segments."""
    if instance.pk and not kwargs.get("raw", False):
        try:
            old = SubjectSource.objects.get(pk=instance.pk)
            instance._segment_prev_assigned_range = old.assigned_range
            instance._segment_prev_subject_id = old.subject_id
        except SubjectSource.DoesNotExist:
            pass


@receiver(post_save, sender=SubjectSource)
def subjectsource_segment_post_save(sender, instance, created, **kwargs):
    """When SubjectSource is created or changed, enqueue async recompute of segments for affected observations."""
    if kwargs.get("raw", False):
        return
    if created:
        lower, upper = instance.assigned_range.lower, instance.assigned_range.upper
    else:
        prev_range = getattr(instance, "_segment_prev_assigned_range", None)
        prev_subject_id = getattr(instance, "_segment_prev_subject_id", None)
        if prev_range is None and prev_subject_id is None:
            return
        lower, upper = _union_assigned_range_bounds(prev_range, instance.assigned_range)
        if lower is None:
            return
    source_id = str(instance.source_id)
    domain = instance.source.das_tenant.domain

    def _enqueue():
        from observations.tasks import recompute_observation_segments_task

        recompute_observation_segments_task.apply_async(
            kwargs={"source_id": source_id, "lower": lower, "upper": upper, "domain": domain}
        )

    transaction.on_commit(_enqueue)


@receiver(post_delete, sender=SubjectSource)
def subjectsource_segment_post_delete(sender, instance, **kwargs):
    """When SubjectSource is deleted, enqueue async recompute for observations that were in its assigned_range."""
    source_id = str(instance.source_id)
    lower = instance.assigned_range.lower
    upper = instance.assigned_range.upper
    domain = instance.source.das_tenant.domain

    def _enqueue():
        from observations.tasks import recompute_observation_segments_task

        recompute_observation_segments_task.apply_async(
            kwargs={"source_id": source_id, "lower": lower, "upper": upper, "domain": domain}
        )

    transaction.on_commit(_enqueue)


def create_proxy_permissions(**kwargs):
    """
    Creates permissions for proxy models which are not created automatically
    by "django.contrib.auth.management.create_permissions"
    see issue[bug]: https://code.djangoproject.com/ticket/11154, however, it has been fixed
    in Django release 2.2
    What this method does is create new permissions for all proxy models,
    using their own content type instead of the content type of the concrete model.
    Multi-Tenant: these are global permissions
    """
    for model in apps.get_models():
        opts = model._meta

        if not opts.proxy:
            continue
        # The content_type creation is needed for the tests
        proxy_content_type, __ = ContentType.objects.get_or_create(app_label=opts.app_label, model=opts.model_name)
        concrete_content_type = ContentType.objects.get_for_model(model, for_concrete_model=True)

        for code_tuple in _get_all_permissions(opts):
            codename = code_tuple[0]
            name = code_tuple[1]
            # Delete the automatically generated permission from Django
            Permission.objects.filter(codename=codename, content_type=concrete_content_type).delete()
            # Create the correct permission for the proxy model
            Permission.objects.get_or_create(
                codename=codename,
                content_type=proxy_content_type,
                defaults={
                    "name": name,
                },
            )


# TODO: do we still need this? I believe it has been addressed by now
post_migrate.connect(create_proxy_permissions)


def create_view_permissionset(permission_set_name):
    if not get_current_tenant():
        raise TenantNotFoundInLocalThreadException()

    permission_set, _ = PermissionSet.objects.get_or_create(name=permission_set_name)

    for codename in ["view_real_time", "view_subject", "subscribe_alerts", "view_subjectgroup"]:
        perms = models.Permission.objects.filter(codename=codename)
        for perm in perms:
            permission_set.permissions.add(perm)
    return permission_set


@receiver(post_save, sender=SubjectGroup)
def auto_create_view_perm(sender, instance, created, **kwargs):
    if created:
        permission_set_name = instance.auto_permissionset_name
        perm_set = create_view_permissionset(permission_set_name)
        permission_set = PermissionSet.objects.get(id=perm_set.id)

        # Add PermissionSet after commit
        transaction.on_commit(lambda: instance.permission_sets.add(permission_set))


@receiver(pre_delete, sender=SubjectGroup)
def delete_auto_created_view_permission_set(sender, instance, **kwargs):
    for permission_set in instance.permission_sets.all():
        search_list = {"View", "Subject", "Group"}
        if len(permission_set.subjectgroup_set.all()) == 1 and search_list.issubset(set(permission_set.name.split())):
            permission_set.delete()


@receiver(post_save, sender=SourceProvider)
def source_provider_post_save(sender, **kwargs):
    source_provider = (
        SourceProvider.objects.annotate(two_way_message=KeyTransform("two_way_messaging", "additional"))
        .exclude(Q(two_way_message__isnull=True) | Q(two_way_message=False))
        .exists()
    )
    cache.set(SOURCE_PROVIDER_2WAY_MSG_KEY, source_provider, None)


@receiver(post_save, sender=Message)
def message_post_save(sender, instance, created, **kwargs):
    logger.info("saved message {}, created={}".format(instance.pk, str(created)))
    message_action = "das.message.new" if created else "das.message.update"
    transaction.on_commit(lambda: pubsub.publish({"message_id": str(instance.pk)}, message_action))


@receiver(post_delete, sender=Message)
def message_post_delete(sender, instance, **kwargs):
    logger.info("delete message {}".format(instance.pk))
    transaction.on_commit(lambda: pubsub.publish({"message_id": str(instance.pk)}, "das.message.delete"))


@receiver(post_save, sender=Announcement)
def news_post_save(sender, instance, created, **kwargs):
    if created:
        logger.info("saved announcement {}, created={}".format(instance.pk, str(created)))
        action = "das.announcement.new"
        transaction.on_commit(lambda: pubsub.publish({"announcement_id": str(instance.pk)}, action))


# ============================================================================
# ObservationSegment Maintenance Signals
# ============================================================================


def get_subject_for_observation(observation):
    """
    Get the subject associated with an observation at the time it was recorded.
    Uses caching to avoid repeated queries for the same observation.

    Args:
        observation: Observation instance
    Returns:
        Subject instance or None if no subject is assigned
    """
    cache_key = f"obs_subject_{observation.id}"
    subject = cache.get(cache_key)

    if subject is None:
        # Find the subject assignment valid at the time of this observation
        try:
            subjectsource = (
                SubjectSource.objects.select_related("subject")
                .filter(source_id=observation.source_id, assigned_range__contains=observation.recorded_at)
                .first()
            )

            if subjectsource:
                subject = subjectsource.subject
                # Cache for 5 minutes (observations don't change subjects retroactively often)
                cache.set(cache_key, subject, 300)
        except Exception as e:
            logger.warning(f"Failed to get subject for observation {observation.id}: {e}")
            return None

    return subject


def _get_observations_for_source_in_range(source, lower, upper):
    """Return observation IDs for the given source with recorded_at in [lower, upper]."""
    return list(
        Observation.objects.filter(
            source=source,
            recorded_at__gte=lower,
            recorded_at__lte=upper,
        ).values_list("id", flat=True)
    )


# Columns needed for update_segments_for_observation (neighbors are loaded via separate queries).
RECOMPUTE_OBSERVATION_ONLY_FIELDS: tuple[str, ...] = (
    "id",
    "location",
    "recorded_at",
    "exclusion_flags",
    "das_tenant_id",
    "source_id",
)


def recompute_observation_segments(observation_ids, *, lower=None, upper=None):
    """Recompute ObservationSegments for the given observations.

    Safe to call with any number of IDs; callers (e.g. Celery task or backfill
    command) may batch.  Pass ``lower``/``upper`` when available so PostgreSQL
    can prune partitions on the ``recorded_at``-partitioned observation table.

    Loads rows with ``only()`` on the columns segment maintenance needs, avoiding
    large fields such as ``additional``.
    """
    if not observation_ids:
        return
    obs_ids = list(observation_ids)
    # Clear cached subject lookups so recompute picks up any SubjectSource changes.
    for obs_id in obs_ids:
        cache.delete(f"obs_subject_{obs_id}")
    qs = Observation.objects.filter(id__in=obs_ids).only(*RECOMPUTE_OBSERVATION_ONLY_FIELDS)
    if lower is not None and upper is not None:
        qs = qs.filter(recorded_at__gte=lower, recorded_at__lte=upper)
    for obs in qs.iterator():
        update_segments_for_observation(obs, created=False)


SEGMENT_RECOMPUTE_MAX_HISTORY_DAYS: int = 3 * 365


def _clamp_recompute_bounds(lower: datetime, upper: datetime) -> tuple[datetime, datetime]:
    """Clamp lower/upper to the segment partition retention window (3 years).

    SubjectSource rows often use DEFAULT_ASSIGNED_RANGE (datetime.min → datetime.max).
    Without clamping, a single SubjectSource edit would query the full observation
    history — potentially millions of rows on a busy source.
    """
    floor = datetime.now(tz=timezone.utc) - timedelta(days=SEGMENT_RECOMPUTE_MAX_HISTORY_DAYS)
    ceiling = datetime.now(tz=timezone.utc)
    clamped_lower = max(lower, floor) if lower.tzinfo else max(lower.replace(tzinfo=timezone.utc), floor)
    clamped_upper = min(upper, ceiling) if upper.tzinfo else min(upper.replace(tzinfo=timezone.utc), ceiling)
    if clamped_lower != lower or clamped_upper != upper:
        logger.info(
            "Clamped recompute range from [%s, %s] to [%s, %s] (partition retention cap)",
            lower,
            upper,
            clamped_lower,
            clamped_upper,
        )
    return clamped_lower, clamped_upper


def recompute_observation_segments_for_source_range(source_id, lower, upper, batch_size=1000):
    """Recompute segments for all observations of a source in [lower, upper].

    Processes in batches to avoid loading huge ID lists.  Common entry point
    used by the SubjectSource signal (via async task) and the backfill command.

    Bounds are clamped to the 3-year partition retention window so an unbounded
    SubjectSource ``assigned_range`` (datetime.min → datetime.max) does not scan
    the entire observation history.
    """
    lower, upper = _clamp_recompute_bounds(lower, upper)
    source = Source.objects.get(id=source_id)
    all_ids = _get_observations_for_source_in_range(source, lower, upper)
    for i in range(0, len(all_ids), batch_size):
        batch = all_ids[i : i + batch_size]
        recompute_observation_segments(batch, lower=lower, upper=upper)


def _union_assigned_range_bounds(assigned_range_a, assigned_range_b):
    """
    Return (lower, upper) covering both ranges for use in observation queries.
    Either argument may be None; if both None, returns (None, None).
    """
    if assigned_range_a is None and assigned_range_b is None:
        return None, None
    if assigned_range_a is None:
        return assigned_range_b.lower, assigned_range_b.upper
    if assigned_range_b is None:
        return assigned_range_a.lower, assigned_range_a.upper
    a_lower, b_lower = assigned_range_a.lower, assigned_range_b.lower
    a_upper, b_upper = assigned_range_a.upper, assigned_range_b.upper
    if a_lower is None or b_lower is None:
        lower = None
    else:
        lower = min(a_lower, b_lower)
    if a_upper is None or b_upper is None:
        upper = None
    else:
        upper = max(a_upper, b_upper)
    return lower, upper


def _create_bridge_segment(prev_obs, next_obs, subject):
    """
    Create a bridge segment between two observations.
    Caller relies on idempotent segment design; real errors propagate.
    """
    ObservationSegment.objects.create_segment(prev_obs, next_obs, subject)
    logger.debug("Created bridge segment %s -> %s", prev_obs.id, next_obs.id)


def _delete_bridge_segment(prev_obs, next_obs, tenant_id):
    """
    Delete the bridge segment between two observations.

    Args:
        prev_obs: Previous observation
        next_obs: Next observation
        tenant_id: Tenant ID for filtering
    """
    ObservationSegment.objects.filter(
        start_observation=prev_obs, end_observation=next_obs, das_tenant_id=tenant_id
    ).delete()


def _create_segment_to_neighbor(start_obs, end_obs, subject):
    """
    Create a segment between two observations.
    get_or_create_segment is idempotent (handles missing segment / IntegrityError);
    real errors propagate.
    """
    segment, created_flag = ObservationSegment.objects.get_or_create_segment(start_obs, end_obs, subject)
    if created_flag:
        return f"{start_obs.id} -> {end_obs.id}"
    return None


def _handle_observation_deletion(observation, subject, prev_obs, next_obs):
    """
    Handle segment updates when an observation is deleted.

    Args:
        observation: Observation being deleted
        subject: Subject instance
        prev_obs: Previous observation (or None)
        next_obs: Next observation (or None)
    """
    # Delete segments involving this observation
    observation._delete_observation_segments()

    # Bridge the gap if both neighbors exist
    if prev_obs and next_obs:
        _create_bridge_segment(prev_obs, next_obs, subject)


def _handle_observation_create_or_update(observation, subject, prev_obs, next_obs, created):
    """
    Handle segment updates when an observation is created or updated.

    Args:
        observation: Observation being created or updated
        subject: Subject instance
        prev_obs: Previous observation (or None)
        next_obs: Next observation (or None)
        created: Whether this is a new observation
    """
    # For updates: delete existing segments involving this observation
    if not created:
        observation._delete_observation_segments()

    # If inserting between two observations, delete the bridge segment
    if created and prev_obs and next_obs:
        _delete_bridge_segment(prev_obs, next_obs, observation.das_tenant_id)

    # Create new segments to neighbors
    segments_created = []

    if prev_obs:
        segment_desc = _create_segment_to_neighbor(prev_obs, observation, subject)
        if segment_desc:
            segments_created.append(segment_desc)

    if next_obs:
        segment_desc = _create_segment_to_neighbor(observation, next_obs, subject)
        if segment_desc:
            segments_created.append(segment_desc)

    if segments_created:
        logger.debug(f"Created segments: {', '.join(segments_created)}")


def update_segments_for_observation(observation, created=False, deleted=False):
    """
    Update segments affected by an observation change.

    This implements the O(1) segment update logic:
    - When observation is created: create segments to prev/next
    - When observation is updated: delete old segments, create new ones
    - When observation is deleted: delete affected segments, bridge the gap

    Args:
        observation: Observation instance
        created: Whether this is a new observation
        deleted: Whether this observation is being deleted
    """
    # Skip observations without location
    if not deleted and not observation.location:
        return

    # Get the subject this observation belongs to
    subject = get_subject_for_observation(observation)
    if not subject:
        logger.debug(f"No subject found for observation {observation.id}")
        return

    # Neighbours are scoped to the same source; subject is for attachment only.
    prev_obs, next_obs = observation.get_neighbor_observations()

    # Handle deletion or create/update
    if deleted:
        _handle_observation_deletion(observation, subject, prev_obs, next_obs)
    else:
        _handle_observation_create_or_update(observation, subject, prev_obs, next_obs, created)


def _resolve_tenant_domain(instance) -> str | None:
    """Resolve tenant domain without hitting the DB when possible.

    Prefers thread-local tenant context (free).  Falls back to the FK only when
    no thread-local is available (management commands, scripts).  Returns None
    when neither path works so the caller can skip enqueue gracefully.

    Returning None always silently drops segment maintenance for this save, so we
    only catch the specific lookup-failure exceptions and let everything else
    propagate to be visible in logs / error tracking.
    """
    try:
        tenant = get_current_tenant()
        if tenant is not None:
            domain = getattr(tenant, "domain", None)
            if domain:
                return domain
    except TenantNotFoundInLocalThreadException:
        pass

    try:
        return instance.das_tenant.domain
    except (DASTenant.DoesNotExist, AttributeError) as exc:
        logger.warning(
            "Could not resolve das_tenant for observation %s (%s); skipping segment enqueue",
            getattr(instance, "pk", "?"),
            exc.__class__.__name__,
        )
        return None


_segment_post_save_tl = threading.local()


def _get_segment_post_save_bucket(db_alias: str) -> dict:
    """Return the per-(thread, db_alias) buffer for coalescing segment post-save enqueues."""
    if not hasattr(_segment_post_save_tl, "buffers"):
        _segment_post_save_tl.buffers = {}
    if db_alias not in _segment_post_save_tl.buffers:
        _segment_post_save_tl.buffers[db_alias] = {"pending": {}, "flush_registered": False, "callback": None}
    return _segment_post_save_tl.buffers[db_alias]


def _flush_callback_still_registered(db_alias: str, callback) -> bool:
    """Return True if our flush callback is still in the connection's ``run_on_commit`` queue.

    Django prunes ``on_commit`` callbacks registered inside a savepoint when that
    savepoint is rolled back.  Without this check, a rolled-back savepoint would
    leave ``flush_registered=True`` while the actual callback is gone, so later
    saves on the same connection would skip re-registering and silently drop
    their batch enqueue.
    """
    if callback is None:
        return False
    conn = connections[db_alias]
    # ``run_on_commit`` entries are ``(savepoint_ids, func)`` on Django 3.2 and
    # ``(savepoint_ids, func, robust)`` on 4.x; index 1 is the function in both.
    for entry in getattr(conn, "run_on_commit", ()):
        if entry[1] is callback:
            return True
    return False


def _clear_segment_post_save_buffers() -> None:
    """Drop any buffered post_save state on this thread.

    A rolled-back transaction discards its ``on_commit`` callbacks but leaves the
    thread-local ``pending`` dict and ``flush_registered=True`` flag in place.  Without
    this cleanup, the next save on the same thread would not re-register a flush AND
    would enqueue stale IDs from the rolled-back transaction.  Wired to ``request_started``
    and Celery ``task_prerun`` so the buffer always starts empty on a new unit of work.
    """
    if hasattr(_segment_post_save_tl, "buffers"):
        del _segment_post_save_tl.buffers


def _flush_segment_post_save_buffer(db_alias: str) -> None:
    """Flush buffered observation segment work: chunk, split create/update queues, enqueue batch tasks."""
    buffers = getattr(_segment_post_save_tl, "buffers", None)
    if not buffers:
        return
    bucket = buffers.get(db_alias)
    if not bucket:
        return

    pending: dict[UUID, tuple[bool, str]] = dict(bucket["pending"])
    bucket["pending"].clear()
    bucket["flush_registered"] = False
    bucket["callback"] = None

    if not pending:
        return

    creates_by_domain: dict[str, list[UUID]] = defaultdict(list)
    updates_by_domain: dict[str, list[UUID]] = defaultdict(list)
    for obs_id, (created_flag, domain) in pending.items():
        if created_flag:
            creates_by_domain[domain].append(obs_id)
        else:
            updates_by_domain[domain].append(obs_id)

    chunk_size = int(getattr(django_settings, "OBSERVATION_SEGMENT_POST_SAVE_BATCH_SIZE", 200))

    for domain, ids in creates_by_domain.items():
        for i in range(0, len(ids), chunk_size):
            chunk_ids = ids[i : i + chunk_size]
            update_observation_segments_batch_task.apply_async(
                kwargs={
                    "observation_ids": [str(u) for u in chunk_ids],
                    "created": True,
                    "domain": domain,
                },
                queue=OBSERVATION_SEGMENT_ASYNC_CREATE_QUEUE,
            )

    for domain, ids in updates_by_domain.items():
        for i in range(0, len(ids), chunk_size):
            chunk_ids = ids[i : i + chunk_size]
            update_observation_segments_batch_task.apply_async(
                kwargs={
                    "observation_ids": [str(u) for u in chunk_ids],
                    "created": False,
                    "domain": domain,
                },
                queue=OBSERVATION_SEGMENT_ASYNC_UPDATE_QUEUE,
            )


@receiver(post_save, sender=Observation)
def observation_segment_post_save(sender, instance, created, **kwargs):
    """Enqueue async segment maintenance after an observation is saved.

    Buffers work per database connection and transaction: many saves in one
    ``atomic()`` produce one ``on_commit`` flush per DB alias (chunked by
    ``OBSERVATION_SEGMENT_POST_SAVE_BATCH_SIZE``). Both creates and updates enqueue
    to ``realtime_p3``.

    In tests that roll back transactions, ``on_commit`` does not run; call
    ``update_segments_for_observation()`` directly if segment state is needed.

    Idempotent by design: concurrent or duplicate tasks are harmless because the
    segment manager uses ``select_for_update`` + ``IntegrityError`` fallback.
    Failures surface in Celery (dead-letter / retry), not as HTTP 500s.
    """
    # Skip during fixture loading
    if kwargs.get("raw", False):
        return

    if not OBSERVATION_SEGMENT_OBSERVATION_SIGNALS_ENABLED:
        return

    # Skip if location is not set (can't create segments without geometry)
    if not instance.location:
        return

    # Resolve domain eagerly (before on_commit) so the callback cannot raise
    # TenantNotFoundInLocalThreadException after the DB transaction commits.
    domain = _resolve_tenant_domain(instance)
    if not domain:
        logger.warning("Cannot resolve tenant domain for observation %s; skipping segment enqueue", instance.pk)
        return

    db_alias = kwargs.get("using") or getattr(instance._state, "db", None) or DEFAULT_DB_ALIAS
    bucket = _get_segment_post_save_bucket(db_alias)
    bucket["pending"][instance.pk] = (created, domain)

    # Re-sync ``flush_registered`` against the connection's ``run_on_commit`` queue:
    # a savepoint rollback can prune a previously-registered callback while leaving
    # this flag True, which would otherwise cause subsequent saves to drop their
    # batch enqueue on outer commit.
    if bucket["flush_registered"] and not _flush_callback_still_registered(db_alias, bucket["callback"]):
        bucket["flush_registered"] = False
        bucket["callback"] = None

    if bucket["flush_registered"]:
        return
    callback = functools.partial(_flush_segment_post_save_buffer, db_alias)
    bucket["callback"] = callback
    bucket["flush_registered"] = True
    transaction.on_commit(callback, using=db_alias)


@receiver(pre_delete, sender=Observation)
def observation_segment_pre_delete(sender, instance, **kwargs):
    """Maintain ObservationSegments when an observation is deleted.

    Runs synchronously (not Celery): the row must exist until we read neighbors
    and delete/bridge segments.  After segments are fixed, a per-tenant tile
    version bump is scheduled on commit so cached tiles become stale.
    """
    if not OBSERVATION_SEGMENT_OBSERVATION_SIGNALS_ENABLED:
        return

    update_segments_for_observation(instance, deleted=True)

    tenant_id = str(instance.das_tenant_id)
    transaction.on_commit(lambda tid=tenant_id: bump_observation_segment_tile_version(tid))


# --- Thread-local buffer cleanup ----------------------------------------------------
# Pooled threads survive across requests (gunicorn sync) and across Celery tasks; a
# rolled-back transaction leaves the ``pending`` dict + ``flush_registered`` flag in place.
# Clear at the start of each new unit of work so no rolled-back state leaks forward.

from django.core.signals import request_started  # noqa: E402


@receiver(request_started)
def _clear_segment_buffers_on_request_started(sender, **kwargs) -> None:
    _clear_segment_post_save_buffers()


def _clear_segment_buffers_on_celery_task_prerun(sender=None, **kwargs) -> None:
    _clear_segment_post_save_buffers()


def _connect_celery_segment_buffer_cleanup() -> None:
    """Connect Celery's ``task_prerun`` so worker threads start each task with a clean buffer."""
    try:
        from celery.signals import task_prerun
    except ImportError:
        return
    task_prerun.connect(_clear_segment_buffers_on_celery_task_prerun, weak=False)


_connect_celery_segment_buffer_cleanup()

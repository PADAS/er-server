import logging
from datetime import datetime, timedelta, timezone

from django_multitenant.utils import get_current_tenant

from django.apps import apps
from django.contrib.auth import models
from django.contrib.auth.management import _get_all_permissions
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import transaction
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
from observations.tasks import maintain_subjectstatus_for_subject
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException

logger = logging.getLogger(__name__)


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
                .filter(source=observation.source, assigned_range__contains=observation.recorded_at)
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


def recompute_observation_segments(observation_ids):
    """
    Recompute ObservationSegments for the given observations (single interface for segment updates).

    Invalidates segment caches and calls update_segments_for_observation for each observation.
    Safe to call with any number of IDs; callers (e.g. Celery task or backfill command) may batch.
    """
    if not observation_ids:
        return
    obs_ids = list(observation_ids)
    # Collect subject IDs involved so we can invalidate their caches
    subject_ids = set()
    for obs in Observation.objects.filter(id__in=obs_ids):
        subject = get_subject_for_observation(obs)
        if subject:
            subject_ids.add(subject.id)
    _invalidate_segment_caches_for_observations_and_subjects(obs_ids, list(subject_ids))
    for obs in Observation.objects.filter(id__in=obs_ids):
        update_segments_for_observation(obs, created=False)


def recompute_observation_segments_for_source_range(source_id, lower, upper, batch_size=1000):
    """
    Recompute segments for all observations of the given source in the time range.

    Processes in batches to avoid loading huge ID lists. This is the common entry point
    used by the SubjectSource signal (via async task) and the backfill command.
    """
    source = Source.objects.get(id=source_id)
    all_ids = _get_observations_for_source_in_range(source, lower, upper)
    for i in range(0, len(all_ids), batch_size):
        batch = all_ids[i : i + batch_size]
        recompute_observation_segments(batch)


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
    lower = min(assigned_range_a.lower, assigned_range_b.lower)
    upper = max(assigned_range_a.upper, assigned_range_b.upper)
    return lower, upper


def _invalidate_segment_caches_for_observations_and_subjects(observation_ids, subject_ids):
    """Invalidate caches used by get_subject_for_observation."""
    for obs_id in observation_ids:
        cache.delete(f"obs_subject_{obs_id}")


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

    # Get neighboring observations
    prev_obs, next_obs = observation.get_neighbor_observations(subject)

    # Handle deletion or create/update
    if deleted:
        _handle_observation_deletion(observation, subject, prev_obs, next_obs)
    else:
        _handle_observation_create_or_update(observation, subject, prev_obs, next_obs, created)


@receiver(post_save, sender=Observation)
def observation_segment_post_save(sender, instance, created, **kwargs):
    """
    Signal handler to maintain ObservationSegments when observations are created or updated.
    This handler updates only the 2 affected segments (O(1) update).
    Uses transaction.on_commit(); in tests that roll back transactions, call
    update_segments_for_observation() directly if segment state is needed.

    Rollout-safe by design: "segment doesn't exist yet" is handled via idempotent
    operations (filter().first(), filter().delete(), manager IntegrityError handling)
    so we never raise for that case. Any exception that does propagate is a real
    error and will 500 the request so it gets fixed rather than hidden in logs.
    """
    # Skip during fixture loading
    if kwargs.get("raw", False):
        return

    # Skip if location is not set (can't create segments without geometry)
    if not instance.location:
        return

    # Schedule segment update after transaction commits. In test environments
    # that roll back transactions, on_commit hooks do not run; tests that need
    # segment updates should call update_segments_for_observation() directly.
    transaction.on_commit(lambda: update_segments_for_observation(instance, created=created))


@receiver(pre_delete, sender=Observation)
def observation_segment_pre_delete(sender, instance, **kwargs):
    """
    Signal handler to maintain ObservationSegments when observations are deleted.
    Removes affected segments and bridges the gap if possible.
    """
    # We need to process this before the observation is actually deleted
    # so we can still access its relationships
    update_segments_for_observation(instance, deleted=True)

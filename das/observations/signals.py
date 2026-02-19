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
from django.db.models.signals import post_delete, post_migrate, post_save, pre_delete
from django.dispatch import receiver

from accounts.models import PermissionSet
from das_server import pubsub
from observations.models import (
    Announcement,
    Message,
    Observation,
    ObservationSegment,
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


def get_neighbor_observations(observation, subject):
    """
    Get the previous and next observations for a subject relative to a given observation.

    Args:
        observation: Observation instance
        subject: Subject instance

    Returns:
        tuple: (prev_observation, next_observation) - either can be None
    """
    # Get all observations for this subject through all their sources, using cache
    cache_key = f"subject_sources_{subject.id}"
    subject_sources = cache.get(cache_key)
    if subject_sources is None:
        subject_sources = list(SubjectSource.objects.filter(subject=subject).values_list("source_id", flat=True))
        cache.set(cache_key, subject_sources, 300)  # Cache for 5 minutes

    # Find previous observation (most recent before this one)
    prev_obs = (
        Observation.objects.filter(
            source_id__in=subject_sources, recorded_at__lt=observation.recorded_at, location__isnull=False
        )
        .order_by("-recorded_at")
        .first()
    )

    # Find next observation (earliest after this one)
    next_obs = (
        Observation.objects.filter(
            source_id__in=subject_sources, recorded_at__gt=observation.recorded_at, location__isnull=False
        )
        .order_by("recorded_at")
        .first()
    )

    return prev_obs, next_obs


def _delete_observation_segments(observation):
    """
    Delete all segments involving the given observation.

    Args:
        observation: Observation instance
    """
    ObservationSegment.objects.filter(
        Q(start_observation=observation) | Q(end_observation=observation), das_tenant_id=observation.das_tenant_id
    ).delete()


def _create_bridge_segment(prev_obs, next_obs, subject):
    """
    Create a bridge segment between two observations.

    Args:
        prev_obs: Previous observation
        next_obs: Next observation
        subject: Subject instance
    """
    try:
        ObservationSegment.objects.create_segment(prev_obs, next_obs, subject)
        logger.debug(f"Created bridge segment {prev_obs.id} -> {next_obs.id}")
    except Exception as e:
        logger.error(f"Failed to create bridge segment: {e}")


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

    Args:
        start_obs: Starting observation
        end_obs: Ending observation
        subject: Subject instance

    Returns:
        str or None: Description of created segment, or None if not created
    """
    try:
        segment, created_flag = ObservationSegment.objects.get_or_create_segment(start_obs, end_obs, subject)
        if created_flag:
            return f"{start_obs.id} -> {end_obs.id}"
    except Exception as e:
        logger.error(f"Failed to create segment {start_obs.id} -> {end_obs.id}: {e}")
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
    _delete_observation_segments(observation)

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
        _delete_observation_segments(observation)

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
    prev_obs, next_obs = get_neighbor_observations(observation, subject)

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

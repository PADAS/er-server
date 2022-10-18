import datetime
import logging

from django_multitenant.utils import get_current_tenant

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify

from activity.models import (
    PC_DONE,
    PC_OPEN,
    Event,
    EventCategory,
    EventGeometry,
    EventPhoto,
    Patrol,
    PatrolFile,
    PatrolNote,
    PatrolSegment,
)
from activity.util import ensure_eventcategory_perms_exist
from das_server import celery, pubsub
from usercontent.tasks import imagefile_rendered
from utils.features import features
from utils.tenant import get_tenant_settings
from utils.tenant.exceptions import TenantNotFoundInLocalThreadException

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Event)
def event_post_save(sender, instance, created, **kwargs):
    logger.debug("saved event {}, created={}".format(instance.pk, str(created)))
    transaction.on_commit(
        lambda: pubsub.publish(
            {"event_id": str(instance.pk)},
            "das.event.new" if created else "das.event.update",
        )
    )

    if features.tms.is_on():
        transaction.on_commit(
            lambda: celery.app.send_task(
                "activity.tasks.evaluate_alert_rules",
                args=(instance.id, created),
                kwargs={"domain": get_tenant_settings().domain},
            )
        )
    else:
        transaction.on_commit(
            lambda: celery.app.send_task("activity.tasks.evaluate_alert_rules", args=(instance.id, created))
        )
    for segment in instance.patrol_segments.all():
        # Send patrol_update rt message
        verify_patrol_constituent_for_rt_messaging(segment)


@receiver(post_delete, sender=Event)
def event_post_delete(sender, instance, **kwargs):
    logger.debug("delete event {}".format(instance.pk))
    transaction.on_commit(lambda: pubsub.publish({"event_id": str(instance.pk)}, "das.event.delete"))


@receiver(post_delete, sender=EventGeometry)
def event_geometry_post_delete(sender, instance, **kwargs):
    logger.debug("delete event geometry {}".format(instance.pk))
    instance.event.dependent_table_updated()


@receiver(post_save, sender=EventPhoto)
def warm_EventPhoto_image(sender, instance, **kwargs):
    transaction.on_commit(lambda: celery.app.send_task("activity.tasks.warm_eventphotos", args=(str(instance.id),)))


@receiver(post_delete, sender=EventPhoto)
def delete_EventPhoto_products(sender, instance, **kwargs):
    logger.debug("delete sized images for EventPhoto.id: {}".format(instance.pk))
    instance.image.delete_all_created_images()


def send_event_thumbnail_update(sender, usercontent_id, **kwargs):
    for event in Event.objects.filter(file__usercontent_id=usercontent_id):
        pubsub.publish({"event_id": str(event.id)}, "das.event.update")


imagefile_rendered.connect(send_event_thumbnail_update)


# Patrol signals
@receiver(post_save, sender=Patrol)
def patrol_post_save(sender, instance, created, **kwargs):
    logger.debug("saved patrol {}, created={}".format(instance.pk, str(created)))
    patrol_action = "das.patrol.new" if created else "das.patrol.update"
    patrol_id = instance.id
    transaction.on_commit(lambda: pubsub.publish({"patrol_id": str(patrol_id)}, patrol_action))
    transaction.on_commit(lambda: check_and_update_patrol_open_state(patrol_id=patrol_id))


@receiver(post_delete, sender=Patrol)
def patrol_post_delete(sender, instance, **kwargs):
    logger.debug("deleted patrol {}".format(instance.pk))
    patrol_action = "das.patrol.delete"
    transaction.on_commit(lambda: pubsub.publish({"patrol_id": str(instance.pk)}, patrol_action))


@receiver(m2m_changed, sender=Event.patrol_segments.through)
def event_linked_to_patrol_segment(sender, instance, action, reverse, model, pk_set, **kwargs):
    def publish_patrol_event_actions(patrol_ids, event_ids):
        logger.debug(f"linked event {event_ids} and patrol {patrol_ids}")
        patrol_action = "das.patrol.update"
        event_action = "das.event.update"
        for id in patrol_ids:
            pubsub.publish({"patrol_id": str(id)}, patrol_action)
        for id in event_ids:
            pubsub.publish({"event_id": str(id)}, event_action)

    listen_for_actions = ("post_add", "post_remove")
    if action in listen_for_actions:
        patrol_ids = (
            (instance.patrol.pk,)
            if isinstance(instance, PatrolSegment)
            else [p.pk for p in Patrol.objects.filter(patrol_segment__id__in=pk_set)]
        )
        event_ids = (instance.pk,) if isinstance(instance, Event) else pk_set
        transaction.on_commit(lambda: publish_patrol_event_actions(patrol_ids, event_ids))


def verify_patrol_constituent_for_rt_messaging(instance):
    if instance.patrol:
        patrol_action = "das.patrol.update"
        transaction.on_commit(lambda: pubsub.publish({"patrol_id": str(instance.patrol.pk)}, patrol_action))


@receiver(post_save, sender=PatrolSegment)
@receiver(post_save, sender=PatrolNote)
@receiver(post_save, sender=PatrolFile)
def patrol_item_post_save(sender, instance, created, **kwargs):
    logger.debug(f"saved {sender._meta.verbose_name} {instance.pk}, created={str(created)}")
    set_eta(instance)
    verify_patrol_constituent_for_rt_messaging(instance)


@receiver(post_delete, sender=PatrolSegment)
@receiver(post_delete, sender=PatrolNote)
@receiver(post_delete, sender=PatrolFile)
def patrol_item_post_delete(sender, instance, **kwargs):
    logger.debug(f"deleted {sender._meta.verbose_name} {instance.pk}")
    verify_patrol_constituent_for_rt_messaging(instance)


def set_eta(instance):
    if isinstance(instance, PatrolSegment) and instance.time_range:
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        upper_bound = instance.time_range.upper
        if upper_bound and upper_bound > now:
            celery.app.send_task(
                "activity.tasks.maintain_patrol_state",
                eta=upper_bound,
                kwargs={"domain": get_tenant_settings().domain},
            )


def check_and_update_patrol_open_state(patrol_id):
    try:
        patrol = Patrol.objects.prefetch_related("patrol_segments").get(id=patrol_id)
        for o in patrol.patrol_segments.all():
            if o.time_range and all([o.time_range.upper is None, patrol.state == PC_DONE]):
                patrol.state = PC_OPEN
                patrol.save()
    except Patrol.DoesNotExist:
        pass


# EventCategory signals
@receiver(post_save, sender=EventCategory)
def ensure_perms_exist(sender, **kwargs):
    if not get_current_tenant():
        raise TenantNotFoundInLocalThreadException()

    if kwargs.get("created", False):
        tenant_settings = get_tenant_settings()
        ensure_eventcategory_perms_exist(kwargs["instance"], tenant_settings.id)


@receiver(pre_save, sender=EventCategory)
def slugify_category_value_field(sender, instance, **kwargs):
    if instance._state.adding:
        instance.value = slugify(instance.value)


@receiver(post_save, sender=EventCategory)
@receiver(post_delete, sender=EventCategory)
def invalidate_active_categories_cache(sender, **kwargs):
    cache.delete(EventCategory.CATEGORIES_CACHE_KEY)

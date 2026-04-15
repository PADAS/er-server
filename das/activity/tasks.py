import logging
from datetime import datetime, timedelta

import pytz
from versatileimagefield.image_warmer import VersatileImageFieldWarmer

import django.contrib.auth
from django.db.models import DateTimeField, ExpressionWrapper, F, Q

from activity.alerting.message import (
    get_revised_event_details_fields,
    get_revised_event_fields,
    send_event_alert,
)
from activity.alerting.rate_limit import (
    allow_send_event_alert,
    reset_alert_metrics,
    reset_alerts_counter,
)
from activity.alerting.rendering import resolve_event_revisions
from activity.alerting.service import evaluate_event
from activity.materialized_view import re_create_view, refresh_materialized_view
from activity.models import (
    PC_DONE,
    PC_OPEN,
    SC_RESOLVED,
    AlertRule,
    Event,
    EventPhoto,
    Patrol,
    RefreshRecreateEventDetailView,
)
from activity.util import get_er_user
from das_server import celery
from utils.features import features
from utils.schema_utils import SchemaValidationError
from utils.tenant import get_tenant_settings
from utils.tenant.celery import OverAllTenantTask, TenantQueueOnceTask

logger = logging.getLogger(__name__)

User = django.contrib.auth.get_user_model()


@celery.app.task(bind=True)
def warm_eventphotos(self, event_photo_id):
    try:
        logger.info("Warming images for event_photo_id=%s", event_photo_id)
        instance = EventPhoto.objects.get(id=event_photo_id)
        warmer = VersatileImageFieldWarmer(
            instance_or_queryset=instance, rendition_key_set="event_photo", image_attr="image"
        )
        num_created, failed_to_create = warmer.warm()
        logger.info("Warmed images for event_photo_id=%s", event_photo_id)
    except Exception:
        logger.exception("Failed when warming images for event_photo_id {}".format(event_photo_id))


@celery.app.task(
    base=TenantQueueOnceTask,
    once={
        "graceful": True,
    },
)
def evaluate_alert_rules(event_id, created, **kwargs) -> None:
    try:
        logger.info("Evaluating event %s for alerting.", event_id)
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist as dex:
            logger.warning("Event %s does not exist. Error: %s", event_id, dex)
            return

        try:
            action_list = evaluate_event(event)
        except SchemaValidationError as svex:
            logger.warning("Error in evaluate_event with %s, ex:%s", event_id, svex)
            return

        # Resolve distinct list of active NotificationMethod objects for the given set of alert rule IDs.
        # TODO: revisit ordering by alert-rule to preserve precedence
        alert_rule_ids = [action["alert_rule_id"] for action in action_list]

        already_queued_nids = set()  # accumulator for Notification Methods.
        alert_rules_qs = (
            AlertRule.objects.filter(id__in=alert_rule_ids, owner__is_active=True)
            .select_related("owner")
            .order_by("ordernum", "title")
        )
        for alert_rule in alert_rules_qs:
            # Verify conditions to only send alerts when the set conditions are met
            evaluate_conditions_for_sending_alerts(event, alert_rule, already_queued_nids, created)

    except Exception:
        logger.exception("Failed when evaluating alert rules for event {}".format(event_id))


def execute_evaluate_alert_rules(*args, **kwargs):
    evaluate_alert_rules(*args, **kwargs)


def evaluate_conditions_for_sending_alerts(event, alert_rule, queued_nids, created):
    event_revision, details_revision = resolve_event_revisions(event)

    # Calculate updated fields
    updated_event_fields = get_revised_event_fields(event_revision)
    updated_event_details_fields = get_revised_event_details_fields(details_revision)

    combined_updated_fields = updated_event_fields
    combined_updated_fields.update(updated_event_details_fields)

    if created or not alert_rule.conditions:
        # Sending all alerts, if new report created or report has no conditions set
        evaluate_notifications(alert_rule, queued_nids, event.id)

    for alert_condition in alert_rule.conditions.get("all", {}):
        condition_name = alert_condition["name"]

        # Check if allowed condition values are updated
        if condition_name in combined_updated_fields:
            evaluate_notifications(alert_rule, queued_nids, event.id)


def evaluate_notifications(alert_rule, already_queued_nids, event_id):
    for notification_method in alert_rule.notification_methods.filter(is_active=True):
        if notification_method.id not in already_queued_nids and allow_send_event_alert(notification_method.owner):
            kwargs = {
                "alert_rule_id": str(alert_rule.id),
                "event_id": str(event_id),
                "notification_method_id": str(notification_method.id),
            }
            if features.tms.is_on():
                kwargs["domain"] = get_tenant_settings().domain

            send_alert_to_notificationmethod.apply_async(args=(), kwargs=kwargs)
        already_queued_nids.add(notification_method.id)


@celery.app.task(
    base=TenantQueueOnceTask,
    once={
        "graceful": True,
    },
)
def send_alert_to_notificationmethod(alert_rule_id=None, event_id=None, notification_method_id=None, **kwargs):
    if any((x is None for x in (alert_rule_id, notification_method_id, event_id))):
        raise ValueError("Coding error.  I need keyword arguments.")

    logger.info(f"Sending alert of event {event_id} to notification id {notification_method_id}")
    send_event_alert(alert_rule_id=alert_rule_id, event_id=event_id, notification_method_id=notification_method_id)


class EventDetailViewException(Exception):
    pass


@celery.app.task(base=TenantQueueOnceTask, bind=True, ignore_result=False, track_started=True)
def recreate_event_details_view(self, **kwargs):
    try:
        result = re_create_view()
        logger.info("Recreate data for event_details_view")
    except Exception as exc:
        logger.exception("Failed to recreate event_details_view.")
        raise EventDetailViewException(exc)
    else:
        return result


@celery.app.task(base=TenantQueueOnceTask, bind=True, ignore_result=False, track_started=True)
def refresh_event_details_view(self, activity, **kwargs):
    try:
        logger.info("Refresh data for event_details_view")
        result = refresh_materialized_view()
    except Exception as e:
        logger.exception("Failed to refresh event_details_view.")
        if activity == "Celery":
            return activity, f"{RefreshRecreateEventDetailView.FAILED}-{str(e)}"
        else:
            raise EventDetailViewException(e)
    else:
        success_state = (
            RefreshRecreateEventDetailView.SUCCESS_WARNING if result else RefreshRecreateEventDetailView.SUCCESS
        )
        invalid_eventtypes = result if result else "-"
        if activity == "Celery":
            return activity, success_state, invalid_eventtypes
        else:
            return result


@celery.app.task(base=TenantQueueOnceTask, once={"graceful": True})
def maintain_patrol_state(**kwargs):
    now = datetime.now(tz=pytz.utc)
    done_patrols = Patrol.objects.filter(
        Q(patrol_segment__time_range__endswith__lte=now) & Q(state=PC_OPEN) & Q(patrol_segment__scheduled_end=None)
    )

    # Transition patrol state from open to done.
    for instance in done_patrols:
        instance.state = PC_DONE
        instance.save()


def execute_maintain_patrol_state(*args, **kwargs):
    maintain_patrol_state(**kwargs)


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def periodically_maintain_patrol_state():
    now = datetime.now(tz=pytz.utc)
    done_patrols = Patrol.objects.filter(
        Q(patrol_segment__time_range__endswith__lte=now) & Q(state=PC_OPEN) & Q(patrol_segment__scheduled_end=None)
    )

    for patrol in done_patrols:
        patrol.state = PC_DONE
        patrol.save()


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def automatically_update_event_state():
    now = datetime.now(tz=pytz.utc)
    expr = ExpressionWrapper(
        F("created_at") + timedelta(hours=1) * F("event_type__resolve_time"), output_field=DateTimeField()
    )

    # only auto-resolve event when the resolve time has reached or surpassed.
    events = (
        Event.objects.annotate(resolve_dt=expr)
        .filter(resolve_dt__lte=now, event_type__auto_resolve=True)
        .exclude(state=SC_RESOLVED)
    )
    er_system_user = get_er_user()
    for e in events:
        e.state = SC_RESOLVED
        setattr(e, "revision_user", er_system_user)
        e.save()


def execute_automatically_update_event_state(*args, **kwargs):
    automatically_update_event_state(*args, **kwargs)


@celery.app.task(base=OverAllTenantTask, once={"graceful": True})
def reset_alert_counter_for_all_users():
    for user in User.objects.all().by_is_active():
        reset_alerts_counter(user)
    reset_alert_metrics()

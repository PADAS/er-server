import pytz
import time
import logging

from datetime import datetime, timedelta
from celery_once import QueueOnce
from versatileimagefield.image_warmer import VersatileImageFieldWarmer

from activity.alerting.businessrules import resolve_event_revisions, \
    infer_event_state
from activity.alerting.message import send_event_alert, \
    get_revised_event_fields, get_revised_event_details_fields
from activity.alerting.service import evaluate_event
from activity.models import EventPhoto, Event, AlertRule, RefreshRecreateEventDetailView
from das_server import celery
from activity.materialized_view import refresh_materialized_view, re_create_view, check_db_view_exists

logger = logging.getLogger(__name__)


@celery.app.task(bind=True)
def warm_eventphotos(self, event_photo_id):

    try:
        logger.info('Warming images for event_photo_id=%s', event_photo_id)
        instance = EventPhoto.objects.get(id=event_photo_id)
        warmer = VersatileImageFieldWarmer(
            instance_or_queryset=instance,
            rendition_key_set='event_photo',
            image_attr='image'
        )
        num_created, failed_to_create = warmer.warm()
        logger.info('Warmed images for event_photo_id=%s', event_photo_id)
    except Exception as e:
        logger.exception(
            'Failed when warming images for event_photo_id {}'.format(event_photo_id))


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def evaluate_alert_rules(event_id, created):

    try:
        logger.info('Evaluating Event %s for alerting.', event_id)
        event = Event.objects.get(id=event_id)
        action_list = evaluate_event(event)

        # For a single event we've gotten the list of alert rules that match.
        # Now we can iterate over them to accumulate the notification methods
        # that should be targeted.

        # Resolve distinct list of active NotificationMethod objects for the given set of alert rule IDs.
        # TODO: revisit ordering by alert-rule to preserve precedence
        alert_rule_ids = [action['alert_rule_id'] for action in action_list]

        already_queued_nids = set()  # accumulator for Notification Methods.
        for alert_rule in AlertRule.objects.filter(id__in=alert_rule_ids).order_by('ordernum', 'title'):

            # Verify conditions to only send alerts when the set conditions are met
            evaluate_conditions_for_sending_alerts(event, alert_rule, already_queued_nids, created)

    except Exception as e:
        logger.exception(
            'Failed when evaluating alert rules for event {}'.format(event_id))


def evaluate_conditions_for_sending_alerts(event, alert_rule, queued_nids, created):
    event_revision, details_revision = resolve_event_revisions(event)

    # Calculate updated fields
    updated_event_fields = get_revised_event_fields(event_revision)
    updated_event_details_fields = get_revised_event_details_fields(
        details_revision)

    combined_updated_fields = updated_event_fields
    combined_updated_fields.update(updated_event_details_fields)

    for alert_condition in alert_rule.conditions.get('all', {}):
        condition_name = alert_condition['name']

        # new event, no updated fields, or revisions
        if created:
            evaluate_notifications(alert_rule, queued_nids, event.id)

        # Check if allowed condition values are updated
        if condition_name in combined_updated_fields:
            evaluate_notifications(alert_rule, queued_nids, event.id)


def evaluate_notifications(alert_rule, already_queued_nids, event_id):
    for notification_method in alert_rule.notification_methods.filter(is_active=True):
        if notification_method.id not in already_queued_nids:
            kwargs = {
                'alert_rule_id': str(alert_rule.id),
                'event_id': str(event_id),
                'notification_method_id': str(notification_method.id)
            }

            send_alert_to_notificationmethod.apply_async(
                args=(), kwargs=kwargs)
        already_queued_nids.add(notification_method.id)


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def send_alert_to_notificationmethod(alert_rule_id=None, event_id=None, notification_method_id=None):

    if any((x is None for x in (alert_rule_id, notification_method_id, event_id))):
        raise ValueError('Coding error.  I need keyword arguments.')

    logger.info(
        f"Sending alert of event {event_id} to notification id {notification_method_id}")
    send_event_alert(alert_rule_id=alert_rule_id, event_id=event_id,
                     notification_method_id=notification_method_id)


@celery.app.task(bind=True, ignore_result=False, track_started=True)
def recreate_event_details_view(self):
    # recreate materialized view for: "event_details_view".

    re_create_view()
    logger.info(f'Recreate data for event_details_view')


@celery.app.task(bind=True, ignore_result=False, track_started=True)
def refresh_event_details_view(self, activity):
    # refresh materialized view for: "event_details_view".
    try:
        logger.info(f'Refresh data for event_details_view')
        refresh_materialized_view()
        return activity, 'SUCCESS'
    except Exception as e:
        logger.exception('Failed to refresh event_details_view.')
        return activity, 'FAILURE'


@celery.app.task(bine=True, ignore_result=False, track_started=True,
                 base=QueueOnce, once={'graceful': True})
def refresh_event_details_view_task(self, activity):
    # run the scheduler if and only-if view exist.

    # Remove records older than 15-days (keep the last five for posterity).
    minimum_date = datetime.now(tz=pytz.utc) - timedelta(days=15)
    last_five_ids = [
        rec.id for rec in RefreshRecreateEventDetailView.objects.order_by('-refresh_at')[:5]]
    RefreshRecreateEventDetailView.objects.filter(
        refresh_at__lte=minimum_date).exclude(id__in=last_five_ids).delete()

    if check_db_view_exists():
        (refresh_event_details_view.s(activity=activity) |
         update_status_of_event_details_view_refresh.s()).delay()


@celery.app.task(bind=True)
def update_status_of_event_details_view_refresh(self, activity_and_status):
    logger.info('updating status of event details view refresh: %s',
                activity_and_status)
    activity, status = activity_and_status
    RefreshRecreateEventDetailView.objects.refresh(
        activity=activity, status=status)

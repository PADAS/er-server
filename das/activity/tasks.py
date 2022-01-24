import logging
from datetime import datetime, timedelta

import pytz
from activity.alerting.businessrules import resolve_event_revisions
from activity.alerting.message import (get_revised_event_details_fields,
                                       get_revised_event_fields,
                                       send_event_alert)
from activity.alerting.service import evaluate_event
from activity.materialized_view import (check_db_view_exists, re_create_view,
                                        refresh_materialized_view)
from activity.models import (PC_DONE, PC_OPEN, SC_RESOLVED, AlertRule, Event,
                             EventPhoto, Patrol,
                             RefreshRecreateEventDetailView)
from activity.util import get_er_user
from celery_once import QueueOnce
from das_server import celery
from django.db.models import DateTimeField, ExpressionWrapper, F, Q
from versatileimagefield.image_warmer import VersatileImageFieldWarmer

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
    except Exception:
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
            evaluate_conditions_for_sending_alerts(
                event, alert_rule, already_queued_nids, created)

    except Exception:
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

    if created or not alert_rule.conditions:
        # Sending all alerts, if new report created or report has no conditions set
        evaluate_notifications(alert_rule, queued_nids, event.id)

    for alert_condition in alert_rule.conditions.get('all', {}):
        condition_name = alert_condition['name']

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


class EventDetailViewException(Exception):
    pass


@celery.app.task(base=QueueOnce, bind=True, ignore_result=False, track_started=True)
def recreate_event_details_view(self):
    # recreate materialized view for: "event_details_view".
    try:
        result = re_create_view()
        logger.info(f'Recreate data for event_details_view')
    except Exception as exc:
        logger.exception('Failed to recreate event_details_view.')
        raise EventDetailViewException(exc)
    else:
        return result


@celery.app.task(base=QueueOnce, bind=True, ignore_result=False, track_started=True)
def refresh_event_details_view(self, activity):
    # refresh materialized view for: "event_details_view".
    try:
        logger.info(f'Refresh data for event_details_view')
        result = refresh_materialized_view()
    except Exception as e:
        logger.exception('Failed to refresh event_details_view.')
        if activity == 'Celery':
            return activity, f'{RefreshRecreateEventDetailView.FAILED}-{str(e)}'
        else:
            raise EventDetailViewException(e)
    else:
        success_state = RefreshRecreateEventDetailView.SUCCESS_WARNING if result else RefreshRecreateEventDetailView.SUCCESS
        invalid_eventtypes = result if result else '-'
        if activity == 'Celery':
            return activity, success_state, invalid_eventtypes
        else:
            return result


@celery.app.task()
def refresh_event_details_view_task(activity):
    # run the scheduler if and only-if view exist.

    # Remove records older than 15-days (keep the last five for posterity).
    minimum_date = datetime.now(tz=pytz.utc) - timedelta(days=15)
    last_five_ids = [
        rec.id for rec in RefreshRecreateEventDetailView.objects.order_by('-started_at')[:5]]
    RefreshRecreateEventDetailView.objects.filter(
        started_at__lte=minimum_date).exclude(id__in=last_five_ids).delete()

    if check_db_view_exists():
        (refresh_event_details_view.s(activity=activity) |
         update_status_of_event_details_view_refresh.s()).apply_async()


@celery.app.task(bind=True)
def update_status_of_event_details_view_refresh(self, activity_and_status):
    logger.info('updating status of event details view refresh: %s',
                activity_and_status)
    activity, status, error_details = activity_and_status

    RefreshRecreateEventDetailView.objects.create(performed_by=activity,
                                                  task_mode='Refresh',
                                                  maintenance_status=status,
                                                  started_at=datetime.now(
                                                      tz=pytz.utc),
                                                  ended_at=datetime.now(
                                                      tz=pytz.utc),
                                                  error_details=error_details
                                                  )


@celery.app.task(base=QueueOnce, once={'graceful': True})
def maintain_patrol_state():
    now = datetime.now(tz=pytz.utc)
    done_patrols = Patrol.objects.filter(Q(patrol_segment__time_range__endswith__lte=now) & Q(
        state=PC_OPEN) & Q(patrol_segment__scheduled_end=None))

    # Transition patrol state from open to done.
    for instance in done_patrols:
        instance.state = PC_DONE
        instance.save()


@celery.app.task(base=QueueOnce, once={'graceful': True})
def periodically_maintain_patrol_state():
    now = datetime.now(tz=pytz.utc)
    done_patrols = Patrol.objects.filter(Q(patrol_segment__time_range__endswith__lte=now) & Q(
        state=PC_OPEN) & Q(patrol_segment__scheduled_end=None))

    for patrol in done_patrols:
        patrol.state = PC_DONE
        patrol.save()


@celery.app.task
def automatically_update_event_state():
    now = datetime.now(tz=pytz.utc)
    expr = ExpressionWrapper(F('created_at') + timedelta(hours=1) * F('event_type__resolve_time'),
                             output_field=DateTimeField())

    # only auto-resolve event when the resolve time has reached or surpassed.
    events = Event.objects.annotate(resolve_dt=expr).filter(resolve_dt__lte=now,
                                                            event_type__auto_resolve=True).exclude(state=SC_RESOLVED)
    er_system_user = get_er_user()
    for e in events:
        e.state = SC_RESOLVED
        setattr(e, 'revision_user', er_system_user)
        e.save()

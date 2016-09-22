
import logging

from accounts.models import User, PermissionSet
from activity.models import Event
from activity.views import EventView
from das_server import celery, mailer
from django.conf import settings
from rt_api.rest_api_interface.dummy_request import DummyRequest

logger = logging.getLogger(__name__)

def get_alert_list_by_priorities(priorities):
    alert_users = set()
    for priority in priorities:
        user_group = None
        if priority == Event.PRI_URGENT and settings.NOTIFY_HIGH_PRIORITY_EVENT is not None:
            user_group = PermissionSet.objects.get(name=settings.NOTIFY_HIGH_PRIORITY_EVENT)
        elif priority == Event.PRI_IMPORTANT and settings.NOTIFY_MEDIUM_PRIORITY_EVENT is not None:
            user_group = PermissionSet.objects.get(name=settings.NOTIFY_MEDIUM_PRIORITY_EVENT)
        elif settings.NOTIFY_LOW_PRIORITY_EVENT is not None:
            user_group = PermissionSet.objects.get(name=settings.NOTIFY_LOW_PRIORITY_EVENT)

        if user_group is not None:
            alert_users |= set(user_group.user_set.all())

    return alert_users


@celery.app.task()
def send_user_event_notification(username, event_id, revision_id = None):
    # First load the user and the event
    user = User.objects.get(username=username)

    # Do a fake API request to make sure the user has
    # permission to view this event
    request = DummyRequest('/event/', 'GET', user=user)
    result = EventView.as_view()(request, id=event_id)
    if result.status_code != 200 or not result.data:
        return

    event = Event.objects.get(pk=event_id)

    if revision_id == None:
        if user.is_email_alert:
            mailer.send_new_event_mail(event, user)

        if user.is_sms_alert:
            mailer.send_new_event_sms(event, user)
    else:
        revision = event.revision.all_user().get(id=revision_id)
        if user.is_email_alert:
            mailer.send_update_event_mail(event, revision, user)

        if user.is_sms_alert:
            mailer.send_update_event_sms(event, revision, user)


@celery.app.task()
def notify_new_event(event_id):
    logger.info('event mailer event_id: {}'.format(event_id))
    event = Event.objects.get(pk=event_id)

    # Get all priorities this alert has ever had
    priorities = []
    revisions = list(iter(event.revision.all_user().order_by('sequence')))
    for revision in revisions:
        if 'priority' in revision.data:
            priorities.append(revision.data['priority'])

    # Get alert user list based on priority history
    user_list = get_alert_list_by_priorities(priorities)

    # Alert each user according to their contact preferences
    for user in user_list:
        celery.app.send_task('das_server.tasks.send_user_event_notification',
            args=(user.username, event_id))


@celery.app.task()
def notify_update_event(event_id):
    logger.info('event mailer event_id: {}'.format(event_id))
    event = Event.objects.get(pk=event_id)
    latest_revision = event.revision.all_user().order_by('sequence').last()

    # Get all priorities this alert has ever had
    priorities = []
    revisions = list(iter(event.revision.all_user().order_by('sequence')))
    for revision in revisions:
        if 'priority' in revision.data:
            priorities.append(revision.data['priority'])

    # Get alert user list based on priority history
    userlist = get_alert_list_by_priorities(priorities)

    # Alert each user according to their contact preferences
    for user in userlist:
        celery.app.send_task('das_server.tasks.send_user_event_notification',
            args=(user.username, event_id, str(latest_revision.id)))



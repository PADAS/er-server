
import logging

from accounts.models import User
from activity.models import Event
from activity.views import EventView
from activity.alerts import get_alert_users
from das_server import celery, mailer

from rt_api.rest_api_interface.dummy_request import DummyRequest

logger = logging.getLogger(__name__)


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
            mailer.send_event_mail(event, user, None, user.email_user)

        if user.is_sms_alert:
            mailer.send_new_event_sms(event, user)
    else:
        revision = event.revision.all_user().get(id=revision_id)
        if user.is_email_alert:
            mailer.send_event_mail(event, user, revision, user.email_user)

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
    user_list = get_alert_users(priorities)

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
    userlist = get_alert_users(priorities)

    # Alert each user according to their contact preferences
    for user in userlist:
        celery.app.send_task('das_server.tasks.send_user_event_notification',
            args=(user.username, event_id, str(latest_revision.id)))



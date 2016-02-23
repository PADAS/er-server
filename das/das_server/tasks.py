import logging

from activity.models import Event
from das_server import celery, mailer

logger = logging.getLogger(__name__)

@celery.app.task()
def event_mailer(event_id):
    logger.info('event mailer event_id: {}'.format(event_id))
    event = Event.objects.get(pk=event_id)

    for subject in event.subjects:
        for user in subject.get_users_to_notify():
            mailer.send_event_mail(event, user)

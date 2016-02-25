import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from activity.models import Event


logger = logging.getLogger(__name__)


def send_event_mail(event, user):


    if event.priority < Event.PRI_IMPORTANT:
        logger.debug("Event wasn't high enough priority to mail out")
        return

    subjects = event.subjects

    if subjects:
        summary = '({})'.format(', '.join([s.name for s in subjects]))
    else:
        summary = ''

    try:
        priority_str = [x[1] for x in  Event.PRIORITY_CHOICES if x[0] == event.priority][0]
    except IndexError:
        priority_str = ''

    subject = 'DAS Event: [{}] {}'.format(priority_str, summary)
    parameters = {
        'event': 'Id: {}'.format(event.pk),
        'time': 'Time: {}'.format(event.time.isoformat()),
        'summary': summary,
        'name': event.name,
        'location': event.location and 'Location: {}'.format(event.location) or 'n/a',
        'content': ''
    }

    body = render_to_string('templates/mailer_new_event.txt', parameters)
    logger.info('emailing {} from {}'.format(user.email, settings.FROM_EMAIL))

    send_mail(subject, body, settings.FROM_EMAIL, [user.email])

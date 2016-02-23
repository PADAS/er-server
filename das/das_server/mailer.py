import logging

from django.conf import settings
from django.template.loader import render_to_string

from activity.models import Event


logger = logging.getLogger(__name__)


def send_event_mail(event, user):

    from boto import ses

    subjects = event.subjects
    conn = ses.connect_to_region(settings.AWS_SES_REGION)

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
    to = [user.email]
    logger.info('emailing {}'.format(user.email))
    return conn.send_email(settings.FROM_EMAIL, subject, body, to)

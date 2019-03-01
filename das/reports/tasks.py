import logging
from das_server import celery
from reports.observationlagnotification import get_lagging_providers, send_lag_delay_alert
from reports.subjectsilentnotification import get_silent_sources, send_silent_source_alert
from django.conf import settings
from datetime import datetime, timedelta
import json


import redis

logger = logging.getLogger(__name__)

from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _
from django.utils.dateparse import parse_datetime

from reports.subjectsourcereport import generate_user_reports
from reports.distribution import send_report, get_users_for_permission, \
    SOURCE_REPORT_PERMISSION_CODENAME



@celery.app.task(bind=True)
def subjectsource_report(self, usernames=None):

    # Limit recipients to those identified by usernames argument.
    recipients = get_users_for_permission(
        SOURCE_REPORT_PERMISSION_CODENAME, usernames=usernames)

    recipients = list(recipients)
    if len(recipients) < 1:
        logger.info(
            'No recipients for Subject Source Report, so not generating report data.')
        return

    for user, report_context in generate_user_reports(recipients):

        logger.info('Generating Subject Source Report for username: %s, email: %s',
                    user.username, user.email)

        email_body = render_to_string(
            'subjectsourcereport.html', report_context)

        report_timestamp = report_context.get(
            'report_date').strftime('%b %d, %Y %H:%M (utc)')

        message_subject = _('DAS Source Report - {}').format(report_timestamp)
        send_report(subject=message_subject,
                    to_email=user.email, text_content=_(
                        'DAS Source report (attached as HTML).'),
                    html_content=email_body)


@celery.app.task(bind=True)
def alert_lag_delay(self):
    lagging_providers = get_lagging_providers()

    for lagging_provider in lagging_providers:
        send_lag_delay_alert(*lagging_provider)


@celery.app.task(bind=True)
def alert_subject_silent(self):
    redis_client = redis.from_url(
        settings.CELERY_BROKER_URL)
    # TODO put this key in a better place and maybe configure 3 hour throttle
    alerted_ttl_key = 'alert_silent_source_alerted_ttl'
    alerted_ttl_dict = redis_client.get(alerted_ttl_key)
    if alerted_ttl_dict is None:
        alerted_ttl_dict = {}
    else:
        alerted_ttl_dict = json.loads(alerted_ttl_dict.decode('utf-8'))
    silent_subjects = get_silent_sources()

    for silent_subject in silent_subjects:
        alerted_ttl = alerted_ttl_dict.get(str(silent_subject[0]['source'].id), None)
        if alerted_ttl is None or parse_datetime(alerted_ttl) < datetime.utcnow():
            send_silent_source_alert(*silent_subject)
            alerted_ttl_dict[str(silent_subject[0]['source'].id)] = (datetime.utcnow() + timedelta(hours=3)).isoformat()
    #TODO on some interval (perhaps stored in the alert_ttl_dict itself), iterate and clean out old items
    redis_client.set(alerted_ttl_key, json.dumps(alerted_ttl_dict).encode('utf-8'))





import logging
import datetime
import pytz

from django.utils.dateparse import parse_duration
from reports.distribution import send_report, get_users_for_permission, SILENT_SOURCE_NOTIFY_PERMISSION_CODENAME
from observations.models import Observation, Subject
from django.db.models import F, Subquery, OuterRef, Max
from django.conf import settings

logger = logging.getLogger(__name__)

def get_silent_sources():

    silent_sources = []
    # we only want sources with "silence_notification_threshold" in its additional json
    # then order by observation recorded and take first source giving us the latest observation for each source
    source_observations = Observation.objects\
        .filter(source__additional__silence_notification_threshold__isnull=False)\
        .order_by('source_id', '-recorded_at')\
        .distinct('source_id')

    for obs in source_observations:
        # build data object to pass to threshold check
        silent_source_check_data = {
            'source_last_obs': obs,
            'source': obs.source
        }
        # get config for this provider
        silent_source_alert_config = get_silent_source_alert_config(obs.source)
        # now we have config lets check if it exceeded threshold
        if check_source_silent(silent_source_check_data, silent_source_alert_config):
            source_subject = Subject.objects.filter(subjectsource__source_id=obs.source_id, subjectsource__assigned_range__contains=obs.recorded_at).first()
            #TODO do we need subject here?  It is nice to get the name for human readability, but it does add DB lookups
            silent_source_check_data['subject_name'] = source_subject.name
            logger.warning('Subject {0} has exceeded silent threshold of {1}, its last known observation is {2}'
                           .format(silent_source_check_data.get('subject_name'),
                                   silent_source_alert_config.get('silence_notification_threshold'),
                                   silent_source_check_data.get('source_last_obs').recorded_at))

            silent_sources.append((silent_source_check_data, silent_source_alert_config))

    return silent_sources


# return the config for this provider's lag alert report
def get_silent_source_alert_config(source):
    # hard coded for now, but could come from file, etc.
    threshold = source.additional.get('silence_notification_threshold', None)
    configured_lag_threshold = {
        'silence_notification_threshold': threshold,
        'site_name': settings.UI_SITE_NAME,
        'site_url': settings.UI_SITE_URL
    }

    return configured_lag_threshold


# check and return bool if the lag time provided in data exceeds configured threshold
def check_source_silent(silent_source_check_data, silent_source_alert_config):
    threshold = silent_source_alert_config.get('silence_notification_threshold', None)

    if any( [threshold is None, len(threshold) == 0]):
        return False  # TODO how did we get here? source should have only returned if threshold was configured

    # configured value is a string, lets parse to timedelta
    threshold = parse_duration(threshold)
    if silent_source_check_data.get('source_last_obs').recorded_at < datetime.datetime.now(pytz.utc) - threshold:
        return True
    return False


# given check data and config send a lag alert as specified in DAS-3533
def send_silent_source_alert(silent_source_check_data, silent_source_alert_config, usernames=None):
    # Limit recipients to those identified by usernames argument.
    recipients = get_users_for_permission(
        SILENT_SOURCE_NOTIFY_PERMISSION_CODENAME, usernames=usernames)

    recipients = list(recipients)
    if len(recipients) < 1:
        logger.info(
            'No recipients for Silent Source notification, so not generating report data.')
        return

    email_body, message_subject = generate_silent_source_notification_email(silent_source_check_data, silent_source_alert_config)
    recipient_emails = [recipient.email for recipient in recipients]
    logger.info('Sending Silent Source Notification for {0}'.format(recipient_emails))
    send_report(subject=message_subject,
                to_email=recipient_emails, text_content=email_body)


def generate_silent_source_notification_email(silent_source_check_data, silent_source_alert_config):
    site_name = silent_source_alert_config.get('site_name')
    message_subject = 'EarthRanger WARNING ({0}): Subject {1} hasn\'t reported!' \
        .format(site_name, silent_source_check_data.get('subject_name'))
    email_body = """EarthRanger WARNING: Subject {subject_name} hasn't reported since configured threshold.

Site name: {site_name}
Site URL: {site_url}
Subject Name: {subject_name}
Configured threshold: {threshold}
Last Reported Time: {last_obs_time}
Last Reported Location: {last_obs_location}

    """.format(site_name=site_name,
               site_url=silent_source_alert_config.get('site_url'),
               threshold=silent_source_alert_config.get('lag_notification_threshold'),
               subject_name=silent_source_check_data.get('subject_name'),
               last_obs_time=silent_source_check_data.get('source_last_obs').recorded_at,
               last_obs_location=silent_source_check_data.get('source_last_obs').location)
    return email_body, message_subject

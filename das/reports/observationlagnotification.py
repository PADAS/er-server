import logging
import datetime
import pytz

logger = logging.getLogger(__name__)

from django.utils.dateparse import parse_duration

from reports.distribution import send_report, get_users_for_permission, OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME

from observations.models import Observation
from django.db.models import Avg, F, Count

def get_lagging_providers():
    lagging_providers = []
    configured_report_duration = "00:30:00"
    period_end = datetime.datetime.now(pytz.utc)
    period_start = period_end - parse_duration(configured_report_duration)
    # grouped by source provider lets find the average lag time in the last duration along with number of entries
    providers = Observation.objects \
        .filter(created_at__gt=period_start) \
        .values(provider_key=F('source__provider__provider_key'),
                provider_display_name=F('source__provider__display_name')) \
        .annotate(avg_lag=Avg(F('created_at') - F('recorded_at')), data_points=Count('created_at')).order_by()
    for provider in providers:
        # build data object to pass to threshold check
        provider_lag_check_data = {
            'provider_name': provider.get('provider_display_name'),
            'avg_lag': provider.get('avg_lag'),
            'num_data_points': provider.get('data_points'),
            'period_start': period_start,
            'period_end': period_end,
        }
        # get config for this provider
        provider_lag_config = get_provider_lag_alert_config(provider_lag_check_data.get('provider_name'))
        # now we have config lets check if it exceeded threshold
        if check_source_provider_lag_exceeded(provider_lag_check_data, provider_lag_config):
            lagging_providers.append((provider_lag_check_data, provider_lag_config))

    return lagging_providers


# return the config for this provider's lag alert report
def get_provider_lag_alert_config(provider_name):
    # hard coded for now, but could come from file, etc.
    configured_lag_threshold = {
        'default': {'lag_delay_threshold': '00:00:00.01'},
        'site_name': 'this site',
        'site_url': 'this site url'
    }

    config = {}
    if provider_name in configured_lag_threshold:
        config = configured_lag_threshold.get(provider_name)
    elif 'default' in configured_lag_threshold:
        config = configured_lag_threshold.get('default')

    # we have pulled to the root any config specific for this provider,
    # now lets update to get any other root items needed later
    config.update(configured_lag_threshold)
    return config


# check and return bool if the lag time provided in data exceeds configured threshold
def check_source_provider_lag_exceeded(provider_lag_check_data, provider_lag_config):
    threshold = provider_lag_config.get('lag_delay_threshold', None)

    if threshold is None:
        return False  # TODO we don't have a configuration for this source and no default specified

    # configured value is a string, lets parse to timedelta
    threshold = parse_duration(threshold)
    if provider_lag_check_data.get('avg_lag') > threshold:
        return True
    return False


# given check data and config send a lag alert as specified in DAS-3365
def send_lag_delay_alert(provider_lag_check_data, provider_lag_config, usernames=None):
    # Limit recipients to those identified by usernames argument.
    recipients = get_users_for_permission(
        OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME, usernames=usernames)

    recipients = list(recipients)
    if len(recipients) < 1:
        logger.info(
            'No recipients for Observation lag notification, so not generating report data.')
        return

    email_body, message_subject = generate_lag_notification_email(provider_lag_check_data, provider_lag_config)
    for recipient in recipients:
        logger.info('Sending Observation Lag Notification for {0}'.format(recipient.email))
        send_report(subject=message_subject,
                    to_email=recipient.email, text_content=email_body)


def generate_lag_notification_email(provider_lag_check_data, provider_lag_config):
    site_name = provider_lag_config.get('site_name')
    message_subject = 'EarthRanger WARNING ({0}): Average delay in data from source provider {1}' \
        .format(site_name, provider_lag_check_data.get('provider_name'))
    email_body = """EarthRanger WARNING: Average delay in data from source provider exceeds configured threshold.

Site name: {site_name}
Site URL: {site_url}
Source provider: {provider_name}
Configured delay threshold: {threshold}
Start of period: {period_start}
End of period: {period_end}
Number of data points: {data_points}
Average delay: {avg_lag}
    """.format(site_name=site_name,
               site_url=provider_lag_config.get('site_url'),
               threshold=provider_lag_config.get('lag_delay_threshold'),
               provider_name=provider_lag_check_data.get('provider_name'),
               period_start=provider_lag_check_data.get('period_start'),
               period_end=provider_lag_check_data.get('period_end'),
               data_points=provider_lag_check_data.get('num_data_points'),
               avg_lag=provider_lag_check_data.get('avg_lag'))
    return email_body, message_subject

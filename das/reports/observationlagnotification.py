import logging
import datetime
import pytz

from django.utils.dateparse import parse_duration
from reports.distribution import send_report, get_users_for_permission, OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME
from observations.models import Observation, SourceProvider
from django.db.models import Avg, F, Count
from django.conf import settings

logger = logging.getLogger(__name__)


def get_lagging_providers():
    lagging_providers = []
    # TODO do we want to be able to configure this value?
    configured_report_duration = "00:30:00"
    period_end = datetime.datetime.now(pytz.utc)
    period_start = period_end - parse_duration(configured_report_duration)
    # grouped by source provider lets find the average lag time in the last duration along with number of entries
    providers = Observation.objects \
        .filter(created_at__gt=period_start) \
        .values(provider_key=F('source__provider__provider_key'),
                provider_display_name=F('source__provider__display_name')) \
        .annotate(avg_lag=Avg(F('created_at') - F('recorded_at')), data_points=Count('created_at')).order_by()
    # the blank order_by above clears the default order_by for Observation model which removes unwanted group by
    for provider in providers:
        # build data object to pass to threshold check
        provider_lag_check_data = {
            'provider_key': provider.get('provider_key'),
            'provider_name': provider.get('provider_display_name'),
            'avg_lag': provider.get('avg_lag'),
            'num_data_points': provider.get('data_points'),
            'period_start': period_start,
            'period_end': period_end,
        }
        # get config for this provider
        provider_lag_config = get_provider_lag_alert_config(
            provider_lag_check_data.get('provider_key'))
        # now we have config lets check if it exceeded threshold
        if check_source_provider_lag_exceeded(provider_lag_check_data, provider_lag_config):
            lagging_providers.append(
                (provider_lag_check_data, provider_lag_config))

    return lagging_providers


# return the config for this provider's lag alert report
def get_provider_lag_alert_config(provider_key):
    # hard coded for now, but could come from file, etc.
    provider = SourceProvider.objects.get(provider_key=provider_key)
    threshold = provider.additional.get('lag_notification_threshold', None)
    configured_lag_threshold = {
        'lag_notification_threshold': threshold,
        'site_name': settings.UI_SITE_NAME,
        'site_url': settings.UI_SITE_URL
    }

    return configured_lag_threshold


# check and return bool if the lag time provided in data exceeds configured threshold
def check_source_provider_lag_exceeded(provider_lag_check_data, provider_lag_config):
    threshold = provider_lag_config.get('lag_notification_threshold', None)

    if not isinstance(threshold, str):
        return False

    # configured value is a string, lets parse to timedelta
    threshold = parse_duration(threshold)
    if provider_lag_check_data.get('avg_lag') > threshold:
        logger.warning('Provider {0} has exceeded lag threshold of {1}, its avg lag in the last interval {2}'
                       .format(provider_lag_check_data.get('provider_name'),
                               threshold, provider_lag_check_data.get('avg_lag')))
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

    email_body, message_subject = generate_lag_notification_email(
        provider_lag_check_data, provider_lag_config)
    recipient_emails = [recipient.email for recipient in recipients]
    logger.info(
        'Sending Observation Lag Notification for {0}'.format(recipient_emails))
    send_report(subject=message_subject,
                to_email=recipient_emails, text_content=email_body)


def generate_lag_notification_email(provider_lag_check_data, provider_lag_config):
    site_name = provider_lag_config.get('site_name')
    message_subject = f"""EarthRanger WARNING ({site_name}): Lag in data from source provider {provider_lag_check_data.get('provider_name')}"""
    email_body = """EarthRanger WARNING: Average lag in data from source provider exceeds configured threshold.
    The lag is the avg time between when the observation was recorded and when it was created in ER over the time period below.

Site name: {site_name}
Site URL: {site_url}
Source provider: {provider_name}
Configured lag threshold: {threshold}
Start of period: {period_start}
End of period: {period_end}
Number of data points: {data_points}
Average lag: {avg_lag}
    """.format(site_name=site_name,
               site_url=provider_lag_config.get('site_url'),
               threshold=provider_lag_config.get('lag_notification_threshold'),
               provider_name=provider_lag_check_data.get('provider_name'),
               period_start=provider_lag_check_data.get('period_start'),
               period_end=provider_lag_check_data.get('period_end'),
               data_points=provider_lag_check_data.get('num_data_points'),
               avg_lag=provider_lag_check_data.get('avg_lag'))
    return email_body, message_subject

import datetime
import logging

import pytz
from celery_once import QueueOnce

from django.conf import settings
from django.db.models import Avg, Count, F
from django.utils.dateparse import parse_duration

from activity.models import EventType
from das_server import celery
from observations.models import Observation, Source, SourceProvider
from reports.distribution import (OBSERVATION_LAG_NOTIFY_PERMISSION_CODENAME,
                                  get_users_for_permission, send_report)
from reports.models import SourceEvent, SourceProviderEvent
from reports.serializers import EventSerializer

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


@celery.app.task(base=QueueOnce, once={'graceful': True})
def check_sources_threshold():
    source_providers = SourceProvider.objects.filter(
        source__subjectsource__assigned_range__contains=datetime.datetime.now(
            pytz.utc)
    ).distinct()
    now = datetime.datetime.now(pytz.utc)

    for source_provider in source_providers:
        sources = (
            Source.objects.filter(provider=source_provider)
            .annotate(last_observation=F("last_observation_source__observation"))
            .annotate(last_observation_recorded_at=F("last_observation_source__recorded_at"))
            .order_by("last_observation_recorded_at")
        )
        if evaluate_source_provider_compliance(source_provider, sources, now):
            continue

        for source in sources.filter(last_observation__isnull=False, last_observation_recorded_at__isnull=False):
            evaluate_source_compliance(source, source_provider, now)


def evaluate_source_provider_compliance(source_provider, latest_observations, now):
    silence_notification_threshold = source_provider.additional.get(
        "silence_notification_threshold"
    )
    source_report = SourcesReport()
    if silence_notification_threshold and all_sources_have_observations(
        source_provider, latest_observations
    ):
        provider_threshold = parse_duration(silence_notification_threshold)
        threshold = now - provider_threshold

        if not all_observations_reach_threshold(
            latest_observations, threshold
        ) and check_can_write_new_provider_event(
            source_provider, now, provider_threshold
        ):
            logger.info(
                f"Creating source provider report, due to all sources reach the provider({source_provider.display_name}) threshold."
            )
            source_report.create_silent_source_provider_report(
                source_provider,
                now,
                latest_observation_record_at=latest_observations.first().last_observation_recorded_at,
            )
            return True
    return False


def all_sources_have_observations(source_provider, latest_observations):
    return source_provider.sources.count() == latest_observations.filter(last_observation__isnull=False).count()


def all_observations_reach_threshold(latest_observation, datetime_threshold):
    return latest_observation.filter(last_observation_recorded_at__gt=datetime_threshold).count()


def check_can_write_new_provider_event(source_provider, now, threshold):
    if source_provider.events_reached_threshold.all():
        lag = (
            now
            - source_provider.events_reached_threshold.latest("created_at").created_at
        )
        return lag > threshold
    return True


def evaluate_source_compliance(source, source_provider, now):
    provider_default_threshold = source_provider.additional.get(
        "default_silent_notification_threshold"
    )
    if provider_default_threshold:
        provider_default_threshold = provider_default_threshold + ":00"
    source_report = SourcesReport()

    if is_threshold_reached(provider_default_threshold, now, source):
        if can_write_new_source_event(
            source, now, provider_default_threshold
        ):
            logger.info(
                f"Creating source report, due to default provider threshold was reached by source {source_provider.display_name}"
            )
            source_report.create_silent_source_report(
                source, now, provider_default_threshold, default_reached=True)
    else:
        source_threshold = source.additional.get(
            "silence_notification_threshold"
        )
        if is_threshold_reached(
            source_threshold, now, source
        ) and can_write_new_source_event(source, now, source_threshold):
            logger.info(
                f"Creating source report, due to source threshold was reached by source {source.model_name}"
            )
            source_report.create_silent_source_report(
                source, now, source_threshold, default_reached=False)


def is_threshold_reached(threshold, now, source):
    if threshold:
        threshold = now - parse_duration(threshold)
        return source.last_observation_recorded_at < threshold
    return False


def can_write_new_source_event(source, now, threshold):
    if source.events_reached_threshold.all():
        lag = now - \
            source.events_reached_threshold.latest("created_at").created_at
        return lag > parse_duration(threshold)
    return True


class SourcesReport:
    def create_silent_source_report(self, source, now, threshold, default_reached) -> None:
        last_observations = source.observation_set.order_by("recorded_at")
        self._save_silent_source_report(
            title=self._get_report_title(source, default_reached),
            report_time=now.strftime("%Y-%m-%d %H:%M:%S"),
            subject_name=self._get_subject_name(source),
            source_provider=source.provider.display_name,
            device_id=source.manufacturer_id,
            silence_threshold=threshold[:-3],
            last_device_reported_at=last_observations.last().recorded_at.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            subject=self._get_source_subject(source),
            source=source,
            location={
                "latitude": last_observations.last().location.y,
                "longitude": last_observations.last().location.x,
            },
        )

    def create_silent_source_provider_report(
        self, source_provider, now, latest_observation_record_at
    ) -> None:
        self._save_silent_source_provider_report(
            title=f"{source_provider.display_name} integration disrupted",
            report_time=now.strftime("%Y-%m-%d %H:%M:%S"),
            silence_threshold=source_provider.additional.get(
                "silence_notification_threshold"
            )[:-3],
            last_device_reported_at=latest_observation_record_at.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            source_provider=source_provider
        )

    def _save_silent_source_report(
        self,
        title: str,
        report_time: str,
        subject_name: str,
        source_provider: str,
        device_id: str,
        silence_threshold: str,
        last_device_reported_at: str,
        subject,
        source,
        location=None,
    ) -> None:
        data = {
            "title": title,
            "event_type": EventType.objects.get(value="silence_source_rep").id,
            "location": location,
            "events": [
                {
                    "data": {
                        "event_details": {
                            "report_time": report_time,
                            "location": location,
                            "device_id": device_id,
                            "name_assigned_subject": subject_name,
                            "source_provider": source_provider,
                            "silence_threshold": silence_threshold,
                            "latest_position_recorded_at": last_device_reported_at,
                        }
                    }
                }
            ],
        }
        serializer = EventSerializer(data=data)
        if serializer.is_valid():
            event = serializer.save()
            if subject:
                event.related_subjects.add(subject)
            SourceEvent.objects.create(source=source, event=event)
        else:
            logger.info(
                f"Impossible create a source report {serializer.errors}")

    def _save_silent_source_provider_report(
        self, title, report_time, silence_threshold, last_device_reported_at, source_provider
    ) -> None:
        data = {
            "title": title,
            "event_type": EventType.objects.get(value="silence_source_provider_rep").id,
            "events": [
                {
                    "data": {
                        "event_details": {
                            "report_time": report_time,
                            "silence_threshold": silence_threshold,
                            "last_device_reported_at": last_device_reported_at,
                        }
                    }
                }
            ],
        }
        serializer = EventSerializer(data=data)
        if serializer.is_valid():
            event = serializer.save()
            SourceProviderEvent.objects.create(
                source_provider=source_provider, event=event)
        else:
            logger.info(
                f"Impossible create a source provider report {serializer.errors}"
            )

    def _get_report_title(self, source, default_reached=False) -> str:
        extra_title = "has gone silent" if default_reached else "is silent"
        if source.subjectsource_set.last() and source.subjectsource_set.last().subject:
            return f"{source.subjectsource_set.last().subject.name} {extra_title}"
        if default_reached:
            return f"{source.id} {extra_title}"
        return f"{source.manufacturer_id} {extra_title}"

    def _get_subject_name(self, source) -> str:
        if source.subjectsource_set.last() and source.subjectsource_set.last().subject:
            return source.subjectsource_set.last().subject.name
        return "(none)"

    def _get_source_subject(self, source):
        if source.subjectsource_set.last() and source.subjectsource_set.last().subject:
            return source.subjectsource_set.last().subject
        return None

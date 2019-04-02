import logging
from datetime import datetime, timedelta
import pytz

from typing import NamedTuple

import redis

from django.utils.dateparse import parse_duration
from reports.distribution import send_report, get_users_for_permission, SILENT_SOURCE_NOTIFY_PERMISSION_CODENAME
from observations.models import Observation, Subject, Source, SubjectSource
from django.db.models import F, Subquery, OuterRef, Max, Q
from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.conf import settings

from django.template.loader import render_to_string
from django.utils.translation import ugettext_lazy as _

logger = logging.getLogger(__name__)


class SourceNoiseData(NamedTuple):
    source: Source
    manufacturer_id: str
    provider_name: str
    assigned_subject_name: str
    threshold_duration: timedelta
    last_recorded_at: datetime = None
    last_location_x: float = None
    last_location_y: float = None


SILENT_SOURCE_ALERT_QUIET_PERIOD = 60*60 # seconds


def calculate_silent_source_report(usernames=None):

    # Limit recipients to those identified by usernames argument.
    recipients = get_users_for_permission(
        SILENT_SOURCE_NOTIFY_PERMISSION_CODENAME, usernames=usernames)

    recipients = list(recipients)
    logger.debug('Silent Source Report recipients: %s', recipients)
    if len(recipients) < 1:
        logger.info(
            'No recipients for Silent Source Notification, so not generating report data.')
        return

    redis_client = redis.from_url(settings.CELERY_BROKER_URL)

    silent_sources = get_silent_sources()

    report_list = []
    for silent_source in silent_sources:

        source_id = silent_source.source.id
        source_alert_marker = f'source_silent_alert_{source_id}'

        # Disregard if we've already alerted for this source (within a threshold).
        if redis_client.exists(source_alert_marker):
            continue
        redis_client.setex(source_alert_marker, 1, SILENT_SOURCE_ALERT_QUIET_PERIOD)

        report_list.append(silent_source)

    if len(report_list) < 1:
        logger.info('No new silent sources found, so not sending any report.')
        return

    report_context = {
        'report_date': datetime.now(tz=pytz.utc),
        'sources': report_list,
        'site_name': settings.UI_SITE_NAME,
        'site_url': settings.UI_SITE_URL
    }

    email_body = render_to_string('silentsourcereport.html', report_context)
    report_timestamp = report_context.get('report_date').strftime('%b %d, %Y %H:%M (utc)')
    message_subject = _('Silent Source Report - {}').format(report_timestamp)

    for user in recipients:
        send_report(subject=message_subject,
                    to_email=user.email,
                    text_content=_('Silent Source Report (attached as HTML).'),
                    html_content=email_body)


def get_silent_sources():

    silent_sources = []

    # Find Sources that are subject to a silence threshold
    eligible_sources = Source.objects.filter(subjectsource__assigned_range__contains=datetime.now(tz=pytz.utc)) \
        .annotate(
        source_threshold=KeyTextTransform('silence_notification_threshold', 'additional'),
        provider_threshold=KeyTextTransform('silence_notification_threshold', 'provider__additional')) \
        .exclude(Q(source_threshold__isnull=True) & Q(provider_threshold__isnull=True))

    logger.debug('Eligible Sources: %s', eligible_sources)
    # For each Source, figure out whether it has an Observation with it's allowed threshold.
    for src in eligible_sources:
        if src.source_threshold:
            duration = parse_duration(src.source_threshold)
        else:
            duration = parse_duration(src.provider_threshold)
        earliest_acceptable_time = datetime.now(tz=pytz.utc) - duration

        latest_observation = Observation.objects.filter(source=src).order_by('-recorded_at').first()

        if latest_observation and latest_observation.recorded_at >= earliest_acceptable_time:
            continue

        relevant_datetime = latest_observation.recorded_at if latest_observation else datetime.now(tz=pytz.utc)

        associated_assignments = SubjectSource.objects.filter(source=src, assigned_range__contains=relevant_datetime)\
            .annotate(subject_name=F('subject__name')) \
            .order_by('-assigned_range')

        if len(associated_assignments) > 1:
            logger.debug('Source %s is associated with multiple Subjects', src)

        relevant_assignment = associated_assignments.first()

        subject_name = relevant_assignment.subject_name if relevant_assignment else '<No Subject>'

        source_noise_data = SourceNoiseData(source=src,
                                            manufacturer_id=src.manufacturer_id,
                                            provider_name=src.provider.display_name,
                                            assigned_subject_name=subject_name,
                                            last_recorded_at=latest_observation.recorded_at if latest_observation else None,
                                            last_location_x=latest_observation.location.x if latest_observation else None,
                                            last_location_y=latest_observation.location.y if latest_observation else None,
                                            threshold_duration=duration)
        silent_sources .append(source_noise_data)

    return silent_sources



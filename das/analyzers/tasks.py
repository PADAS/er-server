import logging

from django.contrib.gis.geos import Point
from django.db import transaction

from analyzers.models.analyzer import NOMINAL, WARNING, CRITICAL
from activity.models import Event, EventAttachment
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.utils import get_or_create_analyzers_for_subject, latest_event_for
from das_server import celery
from observations.models import Subject, SubjectSource
from observations.track import Track

logger = logging.getLogger(__name__)

analyzer_level_to_event_priority = {
    NOMINAL: Event.PRI_REFERENCE,
    WARNING: Event.PRI_IMPORTANT,
    CRITICAL: Event.PRI_URGENT
}

@celery.app.task()
def handle_subject(subject_id):
    logger.info('handling subject ' + str(subject_id))

    subject = Subject.objects.get(id=subject_id)
    track = Track.from_observations(subject.observations())

    if not track:
        logger.warning('Subject {} ({}) has no observations'.format(subject.name, subject_id))
        return

    for analyzer in get_or_create_analyzers_for_subject(subject):
        latest_event = latest_event_for(subject, analyzer)

        try:
            analyzer_result = analyzer.analyze(track)
            if not latest_event and analyzer_result.level == NOMINAL:
                continue

            if analyzer_result and \
                ((not latest_event) or (analyzer_result.level != latest_event.attributes.get('level'))):

                analyzer_result.subject_id = subject_id
                location = Point(analyzer_result.location.x, analyzer_result.location.y)

                with transaction.atomic():
                    event = Event(
                        event_type=analyzer.event_type,
                        provenance=Event.ANALYZER,
                        attributes=analyzer_result.to_dict(),
                        location=location,
                        priority=analyzer_level_to_event_priority[analyzer_result.level],
                        name=analyzer_result.title,
                        description='{}'.format(subject.name)
                    )

                    event.save()
                    event_attachment = EventAttachment(event=event, target=subject, reason=EventAttachment.TARGET)
                    event_attachment.save()

        except InsufficientDataAnalyzerException:
            logger.warning('insufficient observations exist to support analyzer {}'.format(analyzer))

@celery.app.task()
def handle_source(source_id):
    logger.info('handling source ' + str(source_id))

    # get the most recent Subject for this Source
    subject_source = SubjectSource\
                        .objects\
                        .filter(source=source_id)\
                        .order_by('assigned_range')\
                        .reverse()\
                        .first()

    handle_subject(str(subject_source.subject_id))

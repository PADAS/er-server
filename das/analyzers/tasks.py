import logging

from django.db import transaction

from activity.models import Event, EventAttachment
from analyzers.all import all_analyzers
from analyzers.models.analyzer import NOMINAL
from analyzers.models.subject_analyzer import SubjectAnalyzer
from das_server import celery
from observations.models import Subject, SubjectSource
from observations.track import Track

logger = logging.getLogger(__name__)


@celery.app.task()
def handle_subject(subject_id):
    logger.info('handling subject ' + str(subject_id))

    subject = Subject.objects.get(id=subject_id)
    track = Track.from_observations(subject.observations())

    if not track:
        logger.info('Subject {} ({}) has no observations'.format(subject.name, subject_id))

    # get all analyzers, using Subject-specific analyzers where applicable
    analyzers = [sa.analyzer for sa in SubjectAnalyzer.objects.filter(subject=subject)]
    analyzer_classes = [x.__class__ for x in analyzers]
    for a in all_analyzers:
        if a.__class__ not in analyzer_classes:
            analyzers.append(a)

    for analyzer in analyzers:
        analyzer_result = analyzer.analyze(track)
        if analyzer_result.level > NOMINAL:
            analyzer_result.subject_id = subject_id

            with transaction.atomic():
                event = Event(
                    provenance=Event.ANALYZER,
                    attributes=analyzer_result.to_dict(),
                    location=analyzer_result.location,
                    name='{}'.format(analyzer.__class__.__name__)
                )

                event.save()
                event_attachment = EventAttachment(event=event, target=subject, reason=EventAttachment.TARGET)
                event_attachment.save()

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

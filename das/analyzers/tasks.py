import logging

from analyzers.models.analyzer import NOMINAL, WARNING, CRITICAL
from activity.models import Event
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.utils import get_or_create_analyzers_for_subject, latest_event_for
from das_server import celery
from observations.models import Subject, SubjectSource
from observations.track import Track

logger = logging.getLogger(__name__)


@celery.app.task()
def handle_subject(subject_id):
    logger.info('handling subject ' + str(subject_id))

    subject = Subject.objects.get(id=subject_id)
    track = Track.from_observations(subject.observations(last_days=3))

    if not track:
        logger.warning('Subject {} ({}) has no observations'.format(subject.name, subject_id))
        return

    for analyzer in get_or_create_analyzers_for_subject(subject):
        latest_event = latest_event_for(analyzer)

        try:
            analyzer_result = analyzer.analyze(track)
            if (not latest_event and analyzer_result.level == NOMINAL) or \
               ((not analyzer.is_two_state) and analyzer_result.level < WARNING) or \
               (not analyzer_result) or \
               (latest_event and analyzer.is_two_state and analyzer_result.level == latest_event.attributes.get('level')):

                continue

            # conditions met to create a new Event

            analyzer_result.subject = subject
            _ = analyzer_result.create_event()

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

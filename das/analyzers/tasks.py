import logging

from django.conf import settings

from analyzers.models.analyzer import NOMINAL, WARNING, CRITICAL
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.utils import get_or_create_analyzers_for_subject, latest_event_for
from das_server import celery
from observations.models import Subject, SubjectSource
from observations.track import Track
from analyzers.models import ObservationAnnotator

logger = logging.getLogger(__name__)


@celery.app.task()
def handle_subject(subject_id):


    # Call annotator first
    annotate_observations_for_subject(subject_id)

    logger.info('handling subject %s' % str(subject_id))

    subject = Subject.objects.get(id=subject_id)

    if hasattr(settings, 'ANALYZER_SUBJECT_TYPES'):
        if subject.subject_type not in settings.ANALYZER_SUBJECT_TYPES:
            logger.debug(
                'Subject named %s with sub-type %s ignored for analysis', subject.name, subject.subject_type)
            return


    track = Track.from_observations(subject.observations(last_hours=3*24))

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
def annotate_observations_for_subject(subject_id):

    logger.debug('Annotating observations for subject: %s', str(subject_id))

    try:
        sub = Subject.objects.get(id=subject_id)
        annotator = ObservationAnnotator.get_for_subject(sub)
        annotator.annotate()
    except Subject.DoesNotExist:
        logger.warning('Unable to run annotation for subject ID: %s, because it does not exist.', subject_id)
        return




@celery.app.task()
def handle_source(source_id):
    logger.info('handling source %s', str(source_id))

    # get the most recent Subject for this Source
    subject_source = SubjectSource\
                        .objects\
                        .filter(source=source_id)\
                        .order_by('assigned_range')\
                        .reverse()\
                        .first()

    if subject_source:
        handle_subject(str(subject_source.subject_id))
    else:
        logger.warning('Asked to handle source %s, but could not find SubjectSource record.', str(source_id))

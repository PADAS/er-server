import logging

from django.conf import settings

from analyzers.models.analyzer import OK, WARNING, CRITICAL
from analyzers.exceptions import InsufficientDataAnalyzerException
from analyzers.utils import get_or_create_analyzers_for_subject, latest_event_for
from das_server import celery
from observations.models import Subject, SubjectSource
from observations.track import Track
from analyzers.models import ObservationAnnotator
from analyzers.models import *


logger = logging.getLogger(__name__)

def should_save(analyzer_result, last_result=None):
    if last_result is None:
        return True
    if analyzer_result.level in (CRITICAL, WARNING):
        return True
    if last_result.level in (CRITICAL, WARNING):
        return True

@celery.app.task()
def handle_subject(subject_id):

    logger.info('handling subject %s' % str(subject_id))

    # Call annotator first
    annotate_observations_for_subject(subject_id)

    subject = Subject.objects.get(id=subject_id)

    for analyzer in get_or_create_analyzers_for_subject(subject):

        try:
            last_result = analyzer.SubjectAnalyzerResult.objects.filter(subject=subject, subject_analyzer=analyzer). \
                latest('created_at')
        except analyzer.SubjectAnalyzerResult.DoesNotExist:
            last_result = None

        try:
            analyzer_result, analyzer_event = analyzer.analyze(subject, last_result)
            print(analyzer_result)

            if analyzer_event is not None:
                #ToDo: Should signal the event
                pass

            # if should_save(analyzer_result, last_result=latest_result):
            #     analyzer_result.save()
            #     event_to_file = analyzer_result.build_event(last_result)

            # if (not latest_event and analyzer_result.level == OK) or \
            #    ((not analyzer.is_two_state) and analyzer_result.level < WARNING) or \
            #    (not analyzer_result) or \
            #    (latest_event and analyzer.is_two_state and analyzer_result.level == latest_event.attributes.get('level')):
            #     continue
            #
            # # conditions met to create a new Event
            #
            # analyzer_result.subject = subject
            # _ = analyzer_result.create_event()

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

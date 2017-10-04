import logging

from django.conf import settings

from analyzers.exceptions import InsufficientDataAnalyzerException
from das_server import celery
from observations.models import Subject, SubjectSource
from analyzers.models import ObservationAnnotator
from analyzers.finder import get_subject_analyzers

logger = logging.getLogger(__name__)


@celery.app.task()
def handle_subject(subject_id):

    logger.info('handling subject %s', str(subject_id))

    # Call annotator first
    annotate_observations_for_subject(subject_id)

    # Queue analyzer tasks.
    analyze_subject.apply_async(args=[str(subject_id), ])


@celery.app.task(bind=True)
def analyze_subject(self, subject_id):

    subject = Subject.objects.get(id=subject_id)

    logger.info('Running analyzers for subject: %s', subject)
    for analyzer in get_subject_analyzers(subject):

        try:
            analyzer_results = analyzer.analyze()
            for result in analyzer_results:
                logger.debug('Analyzer Result: %s', result[0])

        except InsufficientDataAnalyzerException:
            logger.warning(
                'insufficient observations exist to support analyzer {}'.format(analyzer))


@celery.app.task()
def annotate_observations_for_subject(subject_id):

    logger.debug('Annotating observations for subject: %s', str(subject_id))

    try:
        sub = Subject.objects.get(id=subject_id)
        annotator = ObservationAnnotator.get_for_subject(sub)
        if annotator:
            annotator.annotate()

    except Subject.DoesNotExist:
        logger.warning(
            'Unable to run annotation for subject ID: %s, because it does not exist.', subject_id)
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
        logger.warning(
            'Asked to handle source %s, but could not find SubjectSource record.', str(source_id))


# @celery.app.task()
# def build_subject_speed_profile(subject_id):
#
#     logger.debug('Building speed profile for subject: %s', str(subject_id))
#
#     try:
#         sub = Subject.objects.get(id=subject_id)
#
#     except Subject.DoesNotExist:
#         logger.warning('Unable to run speed profiler for subject ID: %s, because it does not exist.', subject_id)
#         return

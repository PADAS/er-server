import logging

from celery_once import QueueOnce

from analyzers.exceptions import InsufficientDataAnalyzerException
from das_server import celery
from observations.models import Subject, SubjectSource
from analyzers.models import ObservationAnnotator
from analyzers.finder import get_subject_analyzers

logger = logging.getLogger(__name__)


def get_active_subject(subject_id):
    # Check existence of active subject object with provided subject_id
    try:
        if Subject.objects.get(id=subject_id, is_active=True):
            return True
    except Subject.DoesNotExist as e:
        logger.error('No active Subject found with id=%s', subject_id)
        return False


@celery.app.task(base=QueueOnce, once={'graceful': True, 'timeout': 3 * 60})
def handle_subject(subject_id):
    """
    Subject-centric task to run when new observations are recorded.

    Using QueueOnce as a base-class to squash a succession of tasks for the same subject_id.
    """
    subject_id = str(subject_id)
    logger.info('Handling subject %s', subject_id)

    # Call annotator first
    annotate_observations_for_subject(subject_id)

    # Queue analyzer tasks.
    analyze_subject.apply_async(args=(subject_id,))


@celery.app.task()
def handle_source(source_id):
    logger.info('Handling source %s', str(source_id))

    subjects = Subject.objects.get_current_subjects_from_source_id(
        source_id=source_id, values=('id', 'name'))

    for subject in subjects:
        subject_id = subject['id']

        # Execute in one minute, which will allow squashing a succession of observations for a single subject.
        # See 'handle_subject' and it's use of QueueOnce to do the squashing.
        if get_active_subject(subject_id):
            handle_subject.apply_async(args=(subject_id,), countdown=60)


@celery.app.task(base=QueueOnce)
def analyze_subject(subject_id):
    subject = None
    logger.info('Analyze subject for id=%s', subject_id)
    try:
        subject = Subject.objects.get(id=subject_id, is_active=True)
    except Subject.DoesNotExist:
        logger.warning(
            'No active Subject found by ID in analyze_subject. id=%s', subject_id)

    if subject:
        logger.info('Running analyzers for subject: %s', subject)
        for analyzer in get_subject_analyzers(subject):

            try:
                analyzer_results = analyzer.analyze()
                for result in analyzer_results:
                    logger.debug('Analyzer Result: %s', result[0])

            except InsufficientDataAnalyzerException:
                logger.warning(
                    'insufficient observations exist to support analyzer {}'.format(analyzer))
            except Exception:
                logger.exception(
                    'Programming error in analyzer. analyzer=%s', analyzer)


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
def handle_observation(observation_id):

    logger.debug('Handling observation: %s', observation_id)

    subjects = Subject.objects.get_subjects_from_observation_id(
        observation_id, values=('id', 'name'))

    if not subjects:
        logger.debug(
            'Handling observation %s, but it has no associated subject.', observation_id)

    for subject in subjects:
        subject_id = subject['id']

        # Execute in one minute, which will allow squashing a succession of observations for a single subject.
        # See 'handle_subject' and it's use of QueueOnce to do the squashing.
        if get_active_subject(subject_id):
            handle_subject.apply_async(args=(subject_id,), countdown=60)

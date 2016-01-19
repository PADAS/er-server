import logging

from analyzers.all import all_analyzers
from analyzers.models.analyzer import NOMINAL
from analyzers.models.subject_analyzer import SubjectAnalyzer
from das_server import celery
from das_server import pubsub
from observations.models import Subject
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
            pubsub.publish(analyzer_result, 'das.analyzer.warning')

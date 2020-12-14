import logging

from das_server import celery
from observations.models import SubjectSource, Source
from sensors.subject_name_change import get_subject_model

logger = logging.getLogger(__name__)


@celery.app.task()
def handle_subject_and_source(subject_info, source_created, source_id, provider_key, user_id, observation):
    source = Source.objects.get(id=source_id)
    subject_model = get_subject_model(
        subject_info, source_created, source, provider_key, user_id, observation)
    SubjectSource.objects.get_or_create(source=source, subject=subject_model)

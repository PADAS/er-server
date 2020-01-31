import logging
import json
from datetime import datetime, timedelta
import pytz

from celery_once import QueueOnce
from das_server import celery, pubsub
from observations import servicesutils
from observations.models import Subject, SubjectStatus, Observation, SourceProvider, Source
from django.db.models import F


logger = logging.getLogger(__name__)


@celery.app.task()
def store_and_forward_service_status(provider_key=None, data=None):

    data = data or {}
    servicesutils.store_service_status(provider_key=provider_key, data=data)


@celery.app.task(base=QueueOnce, once={'graceful': True})
def maintain_subjectstatus_all():
    for subject in Subject.objects.filter(is_active=True).values('id'):
        maintain_subjectstatus_for_subject.apply_async(
            args=(str(subject['id']),))


@celery.app.task(base=QueueOnce, once={'graceful': True, })
def maintain_subjectstatus_for_subject(subject_id):

    SubjectStatus.objects.maintain_subject_status(subject_id)


@celery.app.task
def maintain_observation_data():
    for ssprovider in SourceProvider.objects.annotate(unique_id=F('id')):
        days_data_retain = ssprovider.additional.get('days_data_retain')
        if not days_data_retain:
            continue
        try:
            days_data_retain = int(days_data_retain)
        except ValueError:
            logger.warning(
                f'Mis-configured field days_data_retain {days_data_retain} not an integer for source_provider: {ssprovider.display_name}'
            )
            continue

        minimum_date = pytz.utc.localize(
            datetime.utcnow()) - timedelta(days=days_data_retain)

        # Observation records older than minimum date
        observation_queryset = Observation.objects.filter(
            source__provider__id=ssprovider.unique_id, recorded_at__lte=minimum_date)

        if observation_queryset.exists():
            observation_queryset.delete()

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


def query_source_provider():
    for ssprovider in SourceProvider.objects.annotate(unique_id=F('id')):
        try:
            if ssprovider.additional['days_data_retain'] != None:
                yield ssprovider
        except KeyError:
            pass

@celery.app.task
def maintain_observation_data():
    source_provider = query_source_provider()

    for o in source_provider:
        minimum_date = pytz.utc.localize(datetime.utcnow()) - timedelta(days=o.additional['days_data_retain'])

        # Observation records older than minimum date
        observation_queryset = Observation.objects.filter(
            source__provider__id=o.unique_id, recorded_at__lte=minimum_date)
        observation_queryset.delete()

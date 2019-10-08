import logging
import json

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
    for ssprovider in SourceProvider.objects.annotate(
            name=F('display_name'),
            info=F('additional')).values('name', 'info'):
        try:
            if ssprovider["info"]["days_data_retain"] != None:
                yield ssprovider
        except KeyError:
            pass


def query_observation(source_provider, source):
    for o in Observation.objects.filter(
            source__provider__display_name=source_provider['name'],
            source__id=source['id']):
        yield o


@celery.app.task
def maintain_observation_data():
    source_provider = query_source_provider()
    source = Source.objects.values('id')

    for o in source_provider:
        for i in source:
            observation_record = list(
                query_observation(source_provider=o, source=i))
            if len(observation_record) >= 2:
                for n in range(1, len(observation_record)):
                    difference_time = observation_record[
                        0].recorded_at - observation_record[-n].recorded_at
                    if difference_time.days == o['info']['days_data_retain']:
                        observation_record[-n].delete()

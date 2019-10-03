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

@celery.app.task
def maintain_observation_data():

    source_provider = SourceProvider.objects.annotate(
        name=F('display_name'), info=F('additional')).values('name', 'info')

    source = Source.objects.values('id')
    for o in source_provider:
        for i in source:
            for x in Observation.objects.filter(source__provider__display_name=o['name'], source__id=i['id']):
                difference_time = x.recorded_at - Observation.objects.last().recorded_at
                if difference_time.days == o['info']['maximum_number_of_days']:
                    # TODO: delete observed data
                    pass



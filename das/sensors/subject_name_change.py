import logging
from datetime import datetime

import pytz
from accounts.models import User
from django.contrib.postgres.fields import DateTimeRangeField
from django.db.models import ExpressionWrapper, F, Func, Q
from observations.models import (SourceGroup, SourceProvider, Subject,
                                 SubjectSource)
from psycopg2.extras import DateTimeTZRange
from tracking.models.er_track import (UPDATE_NAME, USE_EXISTING,
                                      TrackConfiguration)

logger = logging.getLogger(__name__)


def handle_new_device(track_config, user_subjects, observation, source):
    source.groups.set((SourceGroup.objects.get_default(),))
    config = track_config.new_device_config
    if config == USE_EXISTING:
        excluded_subtypes = [
            k.value for k in track_config.new_subject_excluded_subject_types.all()]
        return get_existing_matching_subject(user_subjects, observation, excluded_subtypes, source)


def handle_device_name_change(track_config, user_subjects, observation, subject_id, source):
    config = track_config.name_change_config
    subject_name = observation.get('subject_name')

    if config == USE_EXISTING:
        excluded_subtypes = [
            k.value for k in track_config.name_change_excluded_subject_types.all()]
        return get_existing_matching_subject(user_subjects, observation, excluded_subtypes, source)

    elif config == UPDATE_NAME:
        if subject_id:
            try:
                subject_model = Subject.objects.get(id=subject_id)
            except Subject.DoesNotExist:
                pass
            else:
                if subject_model.name != subject_name:
                    subject_model.name = subject_name
                    subject_model.save()
                    return subject_model


def get_existing_matching_subject(user_subjects, observation, excluded_subtypes, source):
    subject_name = observation.get('subject_name')
    record_time = observation.get('recorded_at')
    qs_person = user_subjects.filter(
        name=subject_name,
        subject_subtype__subject_type__value__iexact='person')
    if qs_person:
        matching_subject = qs_person.first()
        update_source_assignment(matching_subject, source, record_time)
        return matching_subject
    else:
        qs_other = user_subjects.filter(name=subject_name).exclude(
            Q(subject_subtype__subject_type__value__in=excluded_subtypes)) if user_subjects else []

        if len(qs_other) == 1:
            matching_subject = qs_other.first()
            update_source_assignment(matching_subject, source, record_time)
            return matching_subject


def update_source_assignment(matching_subject, source, record_time):
    # Terminate pre existing subject source assignment
    count_terminated_assignments = SubjectSource.objects.filter(subject=matching_subject, assigned_range__contains=record_time) \
        .exclude(source=source) \
        .annotate(lower_boundary=Func(F('assigned_range'), function='LOWER')) \
        .update(assigned_range=ExpressionWrapper(Func(F('lower_boundary'), record_time, function='tstzrange'), output_field=DateTimeRangeField()))

    logger.info('Terminated %d existing assignments.',
                count_terminated_assignments)

    SubjectSource.objects.create(
        source=source, subject=matching_subject,
        assigned_range=DateTimeTZRange(
            lower=record_time, upper=pytz.utc.localize(datetime.max))
    )


def get_track_config(provider_key):
    provider = SourceProvider.objects.filter(provider_key=provider_key).first()

    configs = TrackConfiguration.objects.filter(
        Q(source_provider=provider) | Q(is_default=True)).order_by('is_default')
    track_config = configs.first()

    if not track_config:
        track_config = create_default_config(provider)
    return track_config


def create_default_config():
    default_config = TrackConfiguration.objects.create(is_default=True)
    return default_config


def get_subject_model(subject_info, source_created, source, provider_key, user_id, observation):
    user = User.objects.get(id=user_id)
    user_subjects = Subject.objects.all().by_user_subjects(user)
    subject_id = subject_info.get('id')

    track_config = get_track_config(provider_key)

    if source_created:
        subject_model = handle_new_device(
            track_config, user_subjects, observation, source)
    else:
        subject_model = handle_device_name_change(
            track_config, user_subjects, observation, subject_id, source)
    if not subject_model:
        if Subject.objects.filter(id=subject_id):
            subject_info.pop('id')
        subject_model = Subject.objects.create_subject(**subject_info)
    return subject_model

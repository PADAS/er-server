import logging
from datetime import datetime

import dateutil.parser
import pytz
from accounts.models import User
from django.contrib.postgres.fields import DateTimeRangeField
from django.db.models import ExpressionWrapper, F, Func, Q
from observations.models import (SourceGroup, SourceProvider, Subject,
                                 SubjectSource, Source)
from psycopg2.extras import DateTimeTZRange
from tracking.models.er_track import (UPDATE_NAME, USE_EXISTING, CREATE_NEW,
                                      SourceProviderConfiguration)

logger = logging.getLogger(__name__)


def update_source_assignment(subject, source, recorded_at, terminate_existing_assignments=True):
    '''
    Create an assignment between the given subject and source. This function will also terminate any
    existing assignments for either the Subject or the Source.

    :param subject: A Subject
    :param source: A Source
    :param recorded_at: The timestamp used for starting the assignment.
    :return: a SubjectSource object
    '''
    # Coerce record_time to datetime object.
    recorded_at = recorded_at if isinstance(
        recorded_at, (datetime,)) else dateutil.parser.parse(recorded_at)

    logger.debug('Reassigning subject: %s and source: %s using recorded_at %s',
                 subject, source, recorded_at)

    if terminate_existing_assignments:
        # Terminate pre existing subject source assignment
        count_terminated_assignments = SubjectSource.objects.filter(Q(source=source) | Q(subject=subject),
                                                                    assigned_range__contains=recorded_at) \
            .annotate(lower_boundary=Func(F('assigned_range'), function='LOWER')) \
            .update(assigned_range=ExpressionWrapper(Func(F('lower_boundary'), recorded_at, function='tstzrange'),
                                                     output_field=DateTimeRangeField()))

        logger.info('Terminated %d existing assignments.',
                    count_terminated_assignments)

    return SubjectSource.objects.create(
        source=source, subject=subject,
        assigned_range=DateTimeTZRange(
            lower=recorded_at, upper=pytz.utc.localize(datetime.max))
    )


def mutate_ertrack_subject_assignment(*, source: Source = None, subject_name: str = None,
                                      subject_subtype_id: str = None,
                                      recorded_at: datetime = None, user: User = None, is_new_source: bool):
    '''
    Really special handling for ERTrack observations.

    This function uses the incoming Observation and a SourceProviderConfiguration object to apply rules
    for updating or reassigning the Observation's Source and/or Subject.

    :param source: The Source for the posted Observation
    :param subject_name: The Subject_name given in the posted Observation
    :param subject_subtype_id: chosen subtype for a new Subject
    :param recorded_at: Timestamp for the Observation, used to identify existing assignment(s)
    :param user: User which determines the pool of Subjects for changing assignments.
    :param is_new_source: Indicate whether the Source is just now created.
    :return:
    '''

    er_track_configuration = get_track_config(source.provider)
    subject_queryset = Subject.objects.by_user_subjects(user)

    # Identify excluded subject types.
    if is_new_source:
        excluded_subject_types = er_track_configuration.new_subject_excluded_subject_types.all()
        subject_mutate_setting = er_track_configuration.new_device_config
        match_case = er_track_configuration.new_device_match_case
    else:
        excluded_subject_types = er_track_configuration.name_change_excluded_subject_types.all()
        subject_mutate_setting = er_track_configuration.name_change_config
        match_case = er_track_configuration.name_change_match_case

    name_filter = Q(name=subject_name) if match_case else Q(
        name__iexact=subject_name)

    # Short-circuit if the assignment is already in place.
    if Subject.objects.filter(name_filter, subjectsource__source=source, subjectsource__assigned_range__contains=recorded_at).exists():
        logger.info('Found everything already in place. Doing nothing.')
        return

    logger.debug("Is new source? %s", is_new_source)
    logger.debug('Excluding types: %s, mutating by %s',
                 excluded_subject_types, subject_mutate_setting)

    # ...and update the queryset if necessary.
    if excluded_subject_types:
        logger.debug('Updating query for excludes')
        subject_queryset = subject_queryset.exclude(
            subject_subtype__subject_type__in=excluded_subject_types)

    # Use existing match
    if subject_mutate_setting == USE_EXISTING:

        try:
            # Special Case, if subject-type is "person" we want to find the first.
            existing_match = subject_queryset.filter(name_filter,
                                                     subject_subtype__subject_type__value__iexact='person').first()

            # Otherwise get unique matching subject from other subtypes
            if not existing_match:
                existing_match = subject_queryset.exclude(
                    subject_subtype__subject_type__value__iexact='person').get(name_filter)

        except Subject.MultipleObjectsReturned:
            # More than one subject returned, skip and create new subject later
            logger.warning(
                'Multiple Subjects found with name %s', subject_name)
        except Subject.DoesNotExist:
            # More than one subject returned, skip and create new subject later
            pass

        if existing_match:
            logger.debug('Found match by name: %s', existing_match)
            update_source_assignment(existing_match, source, recorded_at)
        else:
            logger.debug(
                'No match found by name %s. Fall back to CREATE_NEW.', subject_name)
            subject_mutate_setting = CREATE_NEW

    if subject_mutate_setting == UPDATE_NAME:
        # Update name for all requester-visible Subjects presently assigned to this Source.
        cnt = subject_queryset.filter(subjectsource__source=source,
                                      subjectsource__assigned_range__contains=recorded_at).update(name=subject_name)

        logger.debug('Changed name of %d subject(s) to %s', cnt, subject_name)
        if cnt == 0:
            logger.debug(
                'No assignment found for source %s when trying to rename to %s. Fall back to CREATE_NEW.', source, subject_name)
            subject_mutate_setting = CREATE_NEW

    # Create new.
    if subject_mutate_setting == CREATE_NEW:
        logger.debug('CREAT_NEW for subject name: %s, source: %s, recorded_at: %s',
                     subject_name, source, recorded_at)
        created_subject = Subject.objects.create_subject(
            name=subject_name, subject_subtype_id=subject_subtype_id)
        update_source_assignment(created_subject, source, recorded_at)


def get_track_config(provider: SourceProvider):

    track_config = SourceProviderConfiguration.objects.filter(
        Q(source_provider=provider) | Q(is_default=True)).order_by('is_default').first()

    if not track_config:
        track_config, _ = SourceProviderConfiguration.objects.get_or_create(
            is_default=True)
    return track_config

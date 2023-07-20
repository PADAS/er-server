import logging
from datetime import datetime

import dateutil.parser
import pytz
from psycopg2.extras import DateTimeTZRange

from django.contrib.postgres.fields import DateTimeRangeField
from django.db.models import ExpressionWrapper, F, Func, Q

from accounts.models import User
from observations.models import Source, SourceProvider, Subject, SubjectSource
from tracking.models.er_track import (
    CREATE_NEW,
    UPDATE_NAME,
    USE_EXISTING,
    SourceProviderConfiguration,
)
from utils.drf import BadRequestAPIException, ForbiddenAPIException

logger = logging.getLogger(__name__)


def update_source_assignment(subject, source, recorded_at, terminate_existing_assignments=True):
    """
    Create an assignment between the given subject and source. This function will also terminate any
    existing assignments for either the Subject or the Source.

    :param subject: A Subject
    :param source: A Source
    :param recorded_at: The timestamp used for starting the assignment.
    :return: a SubjectSource object
    """
    # Coerce record_time to datetime object.
    recorded_at = recorded_at if isinstance(recorded_at, (datetime,)) else dateutil.parser.parse(recorded_at)

    logger.debug("Reassigning subject: %s and source: %s using recorded_at %s", subject, source, recorded_at)

    if terminate_existing_assignments:
        # Terminate pre existing subject source assignment
        count_terminated_assignments = (
            SubjectSource.objects.filter(Q(source=source) | Q(subject=subject), assigned_range__contains=recorded_at)
            .annotate(lower_boundary=Func(F("assigned_range"), function="LOWER"))
            .update(
                assigned_range=ExpressionWrapper(
                    Func(F("lower_boundary"), recorded_at, function="tstzrange"), output_field=DateTimeRangeField()
                )
            )
        )

        logger.info("Terminated %d existing assignments.", count_terminated_assignments)

    return SubjectSource.objects.create(
        source=source,
        subject=subject,
        assigned_range=DateTimeTZRange(lower=recorded_at, upper=pytz.utc.localize(datetime.max)),
    )


def get_track_config(provider: SourceProvider):
    track_config = (
        SourceProviderConfiguration.objects.filter(Q(source_provider=provider) | Q(is_default=True))
        .order_by("is_default")
        .first()
    )

    if not track_config:
        track_config, _ = SourceProviderConfiguration.objects.get_or_create(is_default=True)
    return track_config


class HandlerERTrack:
    def __init__(
        self,
        source: Source,
        user: User,
        is_new_source: bool,
        subject_name: str,
        recorded_at,
        subject_subtype_id: str = None,
        observation={},
    ):
        self.source = source
        self.user = user
        self.is_new_source = is_new_source
        self.subject_name = subject_name
        self.recorded_at = recorded_at
        self.subject_subtype_id = subject_subtype_id
        self.observation = observation
        self.er_track_configuration = get_track_config(source.provider)
        self.subjects = Subject.objects.by_user_subjects(user)
        self.filters = self.get_subject_filter(subject_name)
        self.user_id = self.observation.get("user_id")
        self.subject_id = self.observation.get("subject_id")
        self.user_linked_subject = None
        if self.user_id:
            self.user_linked_subject = Subject.objects.by_linked_user_id(user_id=self.user_id)

    def handle(self):
        excluded_subject_types = self.get_excluded_subject_types()
        subject_mutate_setting = self.get_subject_mutate_settings()

        if (
            self.has_source_assignment(source=self.source, recorded_at=self.recorded_at)
            and not self.get_allowed_observations_fields()
        ):
            logger.info("Found everything already in place. Doing nothing.")
            return

        if self.subject_id and not self.subjects.filter(id=self.subject_id).exists():
            raise ForbiddenAPIException("Caller can't see this subject")

        linked_subject = self.get_linked_subject(user_id=self.user_id)
        if linked_subject:
            if not self.has_source_assignment(source=self.source, recorded_at=self.recorded_at, subject=linked_subject):
                logger.info("Updating source assignment using linked subject.")
                update_source_assignment(subject=linked_subject, source=self.source, recorded_at=self.recorded_at)
            self.set_subject_name(user_id=self.user_id, subject=linked_subject)
            return

        elif self.user_linked_subject:
            raise ForbiddenAPIException("Caller can't see this user linked subject")

        elif self.subject_id:
            subject = Subject.objects.get(id=self.subject_id)
            self.process_subject(subject=subject)
            return

        assert not self.subject_id

        if excluded_subject_types:
            self.subjects = self.exclude_subject_types(excluded_subject_types)

        if subject_mutate_setting == USE_EXISTING:
            existing_subject = self.get_existing_subject()
            if existing_subject:
                if (
                    self.user_linked_subject
                    and existing_subject.linked_user
                    and existing_subject.id != self.user_linked_subject.id
                ):
                    raise BadRequestAPIException("Specificed user is linked to a different subject")

                if not self.user_linked_subject and not existing_subject.linked_user:
                    self.process_subject(subject=existing_subject)
                else:
                    update_source_assignment(existing_subject, self.source, self.recorded_at)
                logger.debug("Found match by name: %s", existing_subject)
            else:
                if self.get_existing_subject(Subject.objects.all()):
                    logger.info("subject exists, but can't be seen by user")
                    raise ForbiddenAPIException("Caller can't see this subject")

                logger.debug(
                    "No match found by name %s. Fall back to CREATE_NEW.",
                    self.subject_name,
                )
                # TODO: we could be here because the user posting subject data does not have rights to this subject
                # then we will end up creating a new subject for each observation, cause they will not be granted
                # rights to see the subject just created.
                subject_mutate_setting = CREATE_NEW

        if subject_mutate_setting == UPDATE_NAME:
            subjects_updated = self.update_subjects_name()
            logger.debug(
                "Changed name of %d subject(s) to %s",
                subjects_updated,
                self.subject_name,
            )
            if not subjects_updated:
                logger.debug(
                    "No assignment found for source %s when trying to rename to %s. Fall back to CREATE_NEW.",
                    self.source,
                    self.subject_name,
                )
                subject_mutate_setting = CREATE_NEW

        if subject_mutate_setting == CREATE_NEW:
            logger.debug(
                "CREAT_NEW for subject name: %s, source: %s, recorded_at: %s",
                self.subject_name,
                self.source,
                self.recorded_at,
            )
            created_subject = Subject.objects.create_subject(
                name=self.subject_name, subject_subtype_id=self.subject_subtype_id
            )

            if self.user_id and not self.user_linked_subject:
                self.link_subject_to_user(user_id=self.user_id, subject=created_subject)
                self.set_subject_name(user_id=self.user_id, subject=created_subject)

            if not self.has_source_assignment(
                source=self.source, recorded_at=self.recorded_at, subject=created_subject
            ):
                update_source_assignment(created_subject, self.source, self.recorded_at)

    def get_excluded_subject_types(self):
        if self.is_new_source:
            return self.er_track_configuration.new_subject_excluded_subject_types.all()
        return self.er_track_configuration.name_change_excluded_subject_types.all()

    def get_subject_mutate_settings(self) -> str:
        if self.is_new_source:
            return self.er_track_configuration.new_device_config
        return self.er_track_configuration.name_change_config

    def get_match_case(self) -> bool:
        if self.is_new_source:
            return self.er_track_configuration.new_device_match_case
        return self.er_track_configuration.name_change_match_case

    def get_subject_filter(self, subject_name: str):
        if self.get_match_case():
            return Q(name=subject_name)
        return Q(name__iexact=subject_name)

    def has_source_assignment(self, source: Source, recorded_at, subject=None) -> bool:
        if subject:
            return Subject.objects.filter(
                subjectsource__subject=subject,
                subjectsource__source=source,
                subjectsource__assigned_range__contains=recorded_at,
            ).exists()
        return Subject.objects.filter(
            self.filters,
            subjectsource__source=source,
            subjectsource__assigned_range__contains=recorded_at,
        ).exists()

    def exclude_subject_types(self, excluded_subject_types):
        return self.subjects.exclude(subject_subtype__subject_type__in=excluded_subject_types)

    def exclude_subject_type_person(self, subjects):
        try:
            return subjects.exclude(subject_subtype__subject_type__value__iexact="person").get(self.filters)
        except Subject.MultipleObjectsReturned:
            logger.warning("Multiple Subjects found with name %s", self.subject_name)
        except Subject.DoesNotExist:
            pass

    def get_first_subject_type_person(self, subjects):
        return subjects.filter(self.filters, subject_subtype__subject_type__value__iexact="person").first()

    def update_subjects_name(self):
        return self.subjects.filter(
            subjectsource__source=self.source,
            subjectsource__assigned_range__contains=self.recorded_at,
        ).update(name=self.subject_name)

    def get_linked_subject(self, user_id: str):
        return self.subjects.by_linked_user_id(user_id=user_id)

    def is_user_linked_to_a_subject(self) -> bool:
        return self.user_id and self.get_linked_subject(user_id=self.user_id)

    def is_not_subject_linked_to_user(self, subject=None) -> bool:
        subject_id = subject.id if subject else self.subject_id
        if subject_id and self.user_id:
            subject_user = User.objects.by_linked_subject_id(subject_id)
            return subject_user.id != self.user_id if subject_user else True
        return True

    def set_subject_name(self, user_id: str, subject):
        user = self.get_user(user_id=user_id)
        logger.info(f"Renaming subject {subject.id}.")
        subject.name = user.get_full_name() or user.username
        subject.save()

    def link_subject_to_user(self, subject, user_id: str):
        user = self.get_user(user_id=user_id)
        logger.info("Linking subject %s to user %s." % (subject.name, user.username))
        subject.linked_user = user
        subject.save()

    def get_user(self, user_id):
        return User.objects.get(id=user_id)

    def get_allowed_observations_fields(self):
        allowed_fields = {"user_id", "subject_id"}
        observation_fields = list(self.observation.keys())
        return allowed_fields.intersection(observation_fields)

    def get_existing_subject(self, subjects=None):
        subjects = subjects if subjects else self.subjects
        subject_person = self.get_first_subject_type_person(subjects)
        if not subject_person:
            return self.exclude_subject_type_person(subjects)
        return subject_person

    def process_subject(self, subject):
        if self.user_id:
            self.link_subject_to_user(user_id=self.user_id, subject=subject)
            self.set_subject_name(user_id=self.user_id, subject=subject)
        if not self.has_source_assignment(source=self.source, recorded_at=self.recorded_at, subject=subject):
            logger.info("Updating source assignment using linked subject.")
            update_source_assignment(subject, self.source, self.recorded_at)

import datetime
from dataclasses import dataclass
from typing import Dict, List
from uuid import UUID

import pytz

from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Q

from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Observation, Subject, SubjectGroup
from observations.utils import VIEW_SUBJECTGROUP_PERMS, get_cyclic_subjectgroup
from utils.drf import CycleDetectedException, ForbiddenAPIException
from utils.etags import get_hash_from_queryset
from utils.json import parse_bool
from utils.tenant.thread import get_tenant_settings


def get_track_days():
    show_track_days = get_tenant_settings().env_settings.show_track_days
    return datetime.timedelta(days=int(show_track_days))


def default_since():
    """default value for since
    last days is the default
    """
    return datetime.datetime.now(pytz.utc) - get_track_days()


def get_subjects_with_observations_in_daterange(start_date=None, end_date=None):
    observations_qs = Observation.objects.all()

    if start_date and end_date:
        observations_qs = observations_qs.filter(Q(recorded_at__range=(start_date, end_date)))
    elif start_date:
        observations_qs = observations_qs.filter(Q(recorded_at__gte=start_date))
    elif end_date:
        observations_qs = observations_qs.filter(Q(recorded_at__lte=end_date))

    subject_id_values = (
        observations_qs.distinct("source__subjectsource__subject")
        .order_by("source__subjectsource__subject_id")
        .values("source__subjectsource__subject_id")
    )

    subject_ids = [
        str(i["source__subjectsource__subject_id"]) for i in subject_id_values if i["source__subjectsource__subject_id"]
    ]

    return Subject.objects.filter(id__in=subject_ids)


def get_subject_group_etag_fields():
    subject_group_fields = [field.name for field in SubjectGroup._meta.concrete_fields]
    children_fields = [f"children__{field}" for field in subject_group_fields]
    subject_fields = [f"subjects__{field.name}" for field in Subject._meta.concrete_fields]
    return subject_group_fields + children_fields + subject_fields


class SubjectGroupGetQuerySet(TwoWaySubjectSourceMixin):
    def get_queryset(self, request):
        if not request.user.has_any_perms(VIEW_SUBJECTGROUP_PERMS):
            raise ForbiddenAPIException

        qparams = request.GET

        if parse_bool(qparams.get("flat")):
            queryset = SubjectGroup.objects.prefetch_related("children").all()
        else:
            queryset = SubjectGroup.objects.get_non_cyclic_subjectgroups()

        if qparams.get("group_name"):
            queryset = queryset.by_name_search(qparams.get("group_name"))

        queryset = queryset.order_by("name")
        self._get_two_way_sources(queryset)
        return queryset

    def get_all_queryset(self):
        if get_cyclic_subjectgroup(check_any_cycle=True):
            raise CycleDetectedException("Cyclic SubjectGroup found")

        return SubjectGroup.objects.prefetch_related("children").annotate(subject_ids=ArrayAgg("subjects__id"))


@dataclass
class TypedGroup:
    id: str
    name: str
    subgroups: List
    subjects: List


def build_groups_hierarchy_with_all_subjects(
    all_groups_query, user, include_inactive, mou_date, include_subgroups
) -> List[TypedGroup]:
    def _fetch_all_subjects_map(user, mou_date, distinct_subject_ids) -> Dict[UUID, Subject]:
        queryset = Subject.objects.by_ids_user_and_mou_expiry_date(
            id_list=distinct_subject_ids, user=user, active=not include_inactive, mou_expiry_date=mou_date
        )

        return {subject.id: subject for subject in queryset}

    def _build_all_subjects_ids_set(all_groups_query) -> set:
        subject_ids_set = set()

        for subject_group in all_groups_query:
            if None not in subject_group.get("subject_ids"):
                subject_ids_set.update(subject_group.get("subject_ids"))

        return subject_ids_set

    def _build_groups_lookup(all_groups_flat_query, all_subjects_map) -> Dict[UUID, TypedGroup]:
        return {
            group.get("id"): TypedGroup(
                id=group.get("id"),
                name=group.get("name"),
                subgroups=[],
                subjects=[all_subjects_map.get(subject_id) for subject_id in group.get("subject_ids") if subject_id],
            )
            for group in all_groups_flat_query
        }

    def _rebuild_groups_hierarchy(groups_lookup, all_groups_flat_query) -> List[TypedGroup]:
        group_is_child = set()

        for group in all_groups_flat_query:
            parent_id = group.get("id")
            child_id = group.get("children")
            if child_id and child_id in groups_lookup:
                groups_lookup[parent_id].subgroups.append(groups_lookup[child_id])
                group_is_child.add(child_id)

        return [group for group in groups_lookup.values() if group.id not in group_is_child]

    all_groups_flat_query = all_groups_query.values("id", "name", "subject_ids", "children", "is_visible")
    all_subject_ids = _build_all_subjects_ids_set(all_groups_flat_query)

    all_subjects_map = _fetch_all_subjects_map(user, mou_date, all_subject_ids)
    groups_lookup = _build_groups_lookup(all_groups_flat_query, all_subjects_map)

    if not include_subgroups:
        return [group for group in groups_lookup.values()], all_subject_ids

    return _rebuild_groups_hierarchy(groups_lookup, all_groups_flat_query), all_subject_ids


def subject_group_etag(request, *args, **kwargs):
    fields = get_subject_group_etag_fields()
    queryset = SubjectGroup.objects.get_non_cyclic_subjectgroups(single_sg=True)
    TwoWaySubjectSourceMixin()._get_two_way_sources(queryset)
    queryset = queryset.values(*fields).filter(pk=kwargs["id"])
    return get_hash_from_queryset(queryset=queryset, request=request)


def all_group_subjects_etag(request, *args, **kwargs):
    fields = get_subject_group_etag_fields()
    queryset = SubjectGroupGetQuerySet().get_all_queryset()
    queryset = queryset.values(*fields)
    return get_hash_from_queryset(queryset=queryset, request=request)

import datetime

import pytz

from django.db.models import Q

from observations.mixins import TwoWaySubjectSourceMixin
from observations.models import Observation, Subject, SubjectGroup
from observations.utils import VIEW_SUBJECTGROUP_PERMS
from utils.drf import ForbiddenAPIException
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


def subject_groups_etag(request, *args, **kwargs):
    queryset = SubjectGroupGetQuerySet().get_queryset(request)
    queryset = queryset.prefetch_related("children", "subjects").values(*get_subject_group_etag_fields())
    return get_hash_from_queryset(queryset, request)


def subject_group_etag(request, *args, **kwargs):
    fields = get_subject_group_etag_fields()
    queryset = SubjectGroup.objects.get_non_cyclic_subjectgroups(single_sg=True)
    TwoWaySubjectSourceMixin()._get_two_way_sources(queryset)
    queryset = queryset.values(*fields).filter(pk=kwargs["id"])
    return get_hash_from_queryset(queryset=queryset, request=request)

from utils.gis import check_valid_lat_lon, calculate_bbox
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, Polygon
from geopy import Point
from psycopg2.extras import DateTimeTZRange
from django.db.models import Q

from observations.models import LatestObservationSource, SubjectSource, Subject

STATIONARY_SUBJECT_VALUE = "stationary-object"
NAUTICAL_MILE_RADIUS = 5


def check_valid_state_string(state_str):
    """
    Check valid state string.
    Check if the state string is valid.
    valid values are "deployed" or "hauled".

    :param state_str:
    :return: bool, str
    """
    if not state_str:
        return False, None

    state_str = state_str.lower()
    if state_str not in ["deployed", "hauled"]:
        raise ValueError("Invalid value for state: '%s'" % state_str)
    return True, state_str == "deployed"


def check_to_include_inactive_buoys(request, full_queryset):
    """
        Check to include inactive/hauled buoys in the query set.
        Filter the query set based on is_active status.

        :param request:
        :param full_queryset:
        :return: queryset of Subjects.
        """
    # return only active subjects
    queryset = full_queryset.filter(subject__is_active=True)

    # return all subjects if parameter is passed and set to true
    include_inactive = request.GET.get("state", "deployed").lower() == "hauled"
    if include_inactive:
        queryset = full_queryset
    return queryset


def filter_by_bbox(queryset, latitude, longitude, nautical_miles=NAUTICAL_MILE_RADIUS, include_stationary_subjects=False, updated_since=None):
        """
        Filter by bbox.
        Conditionally include subjects that have the latest positions within the bbox.

        :param queryset:
        :param latitude:
        :param longitude:
        :param nautical_miles:
        :param include_stationary_subjects:
        :param updated_since:
        :return: queryset of Subjects.
        """
        geom = Polygon.from_bbox(calculate_bbox(latitude, longitude, nautical_miles))
        sources = LatestObservationSource.objects.filter(observation__location__within=geom)

        sources = sources.exclude(
            source__subjectsource__subject__subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE
        )

        date_range = None
        if updated_since:
            gt = updated_since
            sources = sources.filter(recorded_at__gte=gt)
            date_range = DateTimeTZRange(lower=updated_since)

        sources = sources.values("source").annotate(models.Count("source")).values("source")

        if date_range:
            subject_sources = SubjectSource.objects.filter(
                source__in=sources,
                assigned_range__overlap=date_range,
            )
        else:
            subject_sources = SubjectSource.objects.filter(
                source__in=sources,
            )

        subjects = subject_sources.values("subject")

        if include_stationary_subjects:
            stationary_subjects = Subject.objects.filter(
                subjectstatus__delay_hours=0,
                is_active=True,
                subjectsource__location__within=geom,
                subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE,
            )
            return queryset.values("subject").filter(Q(pk__in=subjects) | Q(pk__in=stationary_subjects))
        else:
            return queryset.filter(subject__in=subjects)
        
from django.contrib.gis.db import models
from django.contrib.gis.geos import Point, Polygon
from geopy import Point
from geopy.distance import distance
from psycopg2.extras import DateTimeTZRange
from django.db.models import Q

from observations.models import Observation, SubjectSource, Subject

STATIONARY_SUBJECT_VALUE = "stationary-object"
NAUTICAL_MILE_RADIUS = 5


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
    try:
        if include_inactive:
            queryset = full_queryset
    except Exception:
        pass
    return queryset

def calculate_bbox(latitude, longitude, nautical_miles):
    """
        Calculate the bbox.
        Calculate the bounding box given the position and radius.

        :param latitude:
        :param longitude:
        :param nautical_miles:
        :return: array representing bbox [west. south, east, north].
        """
    # Create a Point at the original location
    original_point = Point(latitude, longitude)

    # Calculate the points at the corners of the bounding box
    north = distance(nautical=nautical_miles).destination(original_point, 0).latitude
    south = distance(nautical=nautical_miles).destination(original_point, 180).latitude
    east = distance(nautical=nautical_miles).destination(original_point, 90).longitude
    west = distance(nautical=nautical_miles).destination(original_point, 270).longitude

    # Return the bounding box
    return [west, south, east, north]

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
        sources = queryset.values("source").filter(location__within=geom)
        # queryset = queryset.filter(location__within=geom)
        # queryset = queryset.exclude(subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE)
        # sources = Observation.objects.filter(location__within=geom)
        sources = sources.exclude(
            source__subjectsource__subject__subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE
        )
        for source in sources:
            print(source)

        date_range = None
        if updated_since:
            gt = updated_since
            # queryset = queryset.filter(recorded_at__gte=gt)
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
            for subject_source in subject_sources:
                print(subject_source)

        subjects = subject_sources.values("subject")
        for subject in subjects:
            print(subject)

        if include_stationary_subjects:
            stationary_subjects = Subject.objects.filter(
                subjectstatus__delay_hours=0,
                # is_active=True,
                subjectsource__location__within=geom,
                subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE,
            )
            return queryset.values("subject").filter(Q(pk__in=subjects) | Q(pk__in=stationary_subjects))
        else:
            return queryset.values("subject").filter(pk__in=subjects)
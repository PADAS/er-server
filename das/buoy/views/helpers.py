from __future__ import annotations

from django.contrib.gis.geos import Polygon
from django.db.models import QuerySet

from observations.models import Subject, SubjectSource
from utils.gis import calculate_bbox

STATIONARY_SUBJECT_VALUE = "stationary-object"
NAUTICAL_MILE_RADIUS = 5


def filter_by_bbox(
    queryset: QuerySet[Subject],
    latitude: float,
    longitude: float,
    nautical_miles: int = NAUTICAL_MILE_RADIUS,
) -> QuerySet[Subject]:
    """Filter Subjects whose devices have locations within a bounding box.

    Uses SubjectSource.location (kept current by BuoyService) so the query
    avoids joining into the partitioned Observations table entirely.
    """
    geom = Polygon.from_bbox(calculate_bbox(latitude, longitude, nautical_miles))

    # Note: (0,0) sentinel points are not excluded here because the serializer
    # already handles empty-location filtering via the include_empty_location flag.
    subject_id_subquery = (
        SubjectSource.objects.filter(location__within=geom)
        .exclude(subject__subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE)
        .values("subject_id")
        .distinct()
    )

    return queryset.filter(id__in=subject_id_subquery)

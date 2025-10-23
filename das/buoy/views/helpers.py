from psycopg2.extras import DateTimeTZRange

from django.contrib.gis.geos import Polygon

from observations.models import LatestObservationSource, Subject, SubjectSource
from utils.gis import calculate_bbox

STATIONARY_SUBJECT_VALUE = "stationary-object"
NAUTICAL_MILE_RADIUS = 5


def filter_by_bbox(
    queryset,
    latitude,
    longitude,
    nautical_miles=NAUTICAL_MILE_RADIUS,
    include_stationary_subjects=False,
    updated_since=None,
):
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

    sources_qs = LatestObservationSource.objects.filter(observation__location__within=geom).exclude(
        source__subjectsource__subject__subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE
    )

    if updated_since:
        sources_qs = sources_qs.filter(recorded_at__gte=updated_since)

    source_ids = list(sources_qs.values_list("source_id", flat=True))

    if not source_ids:
        return queryset.none()

    subject_sources_qs = SubjectSource.objects.filter(source_id__in=source_ids)

    if updated_since:
        date_range = DateTimeTZRange(lower=updated_since)
        subject_sources_qs = subject_sources_qs.filter(assigned_range__overlap=date_range)

    subject_ids = list(subject_sources_qs.values_list("subject_id", flat=True))

    if include_stationary_subjects:
        stationary_subject_ids = list(
            Subject.objects.filter(
                subjectstatus__delay_hours=0,
                is_active=True,
                subjectsource__location__within=geom,
                subject_subtype__subject_type__value=STATIONARY_SUBJECT_VALUE,
            ).values_list("id", flat=True)
        )
        subject_ids.extend(stationary_subject_ids)

    return queryset.filter(subject_id__in=subject_ids)

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.contrib.gis.geos import Point
from django.db.models import F, Q, QuerySet

from observations.models import Observation

EMPTY_POINT = Point(0, 0)


def _get_observations_queryset(
    filter_fields: Optional[Dict[str, Any]] = None,
    filter_q_fields: Optional[Dict[str, Any]] = None,
    exclude_fields: Optional[Dict[str, Any]] = None,
) -> QuerySet[Observation]:
    """
    Retrieve a queryset of observations based on the provided filters.

    Args:
        filter_fields (Optional[Dict[str, Any]]): A dictionary of fields and their values to filter the queryset.
        filter_q_fields (Optional[Dict[str, Any]]):
            A dictionary of fields and their values to filter the queryset using Q objects.
        exclude_fields (Optional[Dict[str, Any]]): A dictionary of fields and their values to exclude from the queryset.

    Returns:
        QuerySet[Observation]: The resulting queryset of observations.

    """
    qs = Observation.objects.all()

    if filter_fields:
        qs = qs.filter(**filter_fields)
    if filter_q_fields:
        qs = qs.filter(Q(**filter_q_fields))
    if exclude_fields:
        qs = qs.exclude(**exclude_fields)
    return qs


def _get_observation_instance(id: UUID) -> Observation:
    try:
        return Observation.objects.get(id=id)
    except Observation.DoesNotExist:
        return None


def get_observation_location_and_recorded_at_by_subject_source_id(
    subject_source_id: UUID,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> List[Optional[Dict[str, Any]]]:
    """
    Retrieves the observation location and recorded_at timestamp for a given subject source ID.

    Args:
        subject_source_id (UUID): The ID of the subject source.
        since (Optional[datetime], optional): The starting timestamp for filtering observations. Defaults to None.
        until (Optional[datetime], optional): The ending timestamp for filtering observations. Defaults to None.

    Returns:
        List[Optional[Dict[str, Any]]]:
        A list of dictionaries containing the location and recorded_at timestamp of each observation.
    """
    filter_q = None

    if since and until:
        filter_q = {"recorded_at__range": [since, until]}

    qs = _get_observations_queryset(
        filter_fields={
            "source__subjectsource": subject_source_id,
            "source__subjectsource__assigned_range__contains": F("recorded_at"),
        },
        filter_q_fields=filter_q,
        exclude_fields={"location": EMPTY_POINT},
    )
    data = qs.values("location", "recorded_at")

    return list(data)

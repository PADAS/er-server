from typing import Any, Dict, Optional
from uuid import UUID

from django.contrib.gis.geos import Point
from django.db.models import F, Q, QuerySet

from observations.dataclasses import ObservationData
from observations.models import Observation
from observations.repositories.interfaces import RepositoryInterface

EMPTY_POINT = Point(0, 0)


class ObservationDatabaseManagerMixin:
    def by_since(self, qs: QuerySet, recorded_since):
        return qs.filter(recorded_at__gte=recorded_since)

    def by_until(self, qs: QuerySet, recorded_until):
        return qs.filter(Q(recorded_at__lte=recorded_until))

    def by_since_until(self, qs: QuerySet, recorded_since, recorded_until):
        if recorded_since and recorded_until:
            qs = qs.filter(Q(recorded_at__range=[recorded_since, recorded_until]))
        elif recorded_since:
            qs = qs.by_since(recorded_since)
        elif recorded_until:
            qs = self.by_until(qs, recorded_until)
        return qs

    def by_exclusion_flags(self, qs: QuerySet, filter_flag=None, include_empty_location: bool = False):
        """Works with more than one filter flag, for example 3 which is manual and automatic exclusion.

        Args:
            filter_flag (optional): the exclusion filter flag, think bits. 0 is a valid value. Defaults to None.
            include_empty_location (bool, optional): don't filter out locations that are 0,0. Defaults to False.

        Returns:
            queryset: a further filtered queryset
        """
        if filter_flag is not None:
            if filter_flag > 0:
                qs = qs.annotate(exclusion_filter=F("exclusion_flags").bitand(filter_flag)).filter(
                    exclusion_filter__gt=0
                )
            else:
                qs = qs.filter(exclusion_flags=filter_flag)
            if not include_empty_location:
                qs = qs.exclude(Q(location=EMPTY_POINT))
        return qs

    def get_subjectsource_observations(
        self,
        subject_source_id: UUID,
        since=None,
        until=None,
        limit=None,
        values=None,
        filter_flag=0,
        order_by=None,
    ):
        qs = self.qs.filter(
            source__subjectsource=subject_source_id, source__subjectsource__assigned_range__contains=F("recorded_at")
        )
        qs = self.by_since_until(qs, since, until)
        qs = self.by_exclusion_flags(qs, filter_flag)

        if order_by:
            qs = qs.order_by(order_by)

        if limit and limit > 0:
            qs = qs[:limit]

        if values:
            qs = qs.values(*values)

        return qs

    def _get_observation_by_id(self, id: UUID) -> Observation:
        try:
            return Observation.objects.get(pk=id)
        except Observation.DoesNotExist:
            return None
        except Observation.MultipleObjectsReturned:
            return None


class ObservationRepository(RepositoryInterface, ObservationDatabaseManagerMixin):
    qs: QuerySet = Observation.objects.all()

    def get_all(self):
        return self._get_observations()

    def get_by_id(self) -> Optional[Observation]:
        return self._get_observation_by_id()

    def build_dataclass(self, observation_data: Dict[str, Any]) -> ObservationData:
        if not isinstance(observation_data["location"], Point):
            location = Point(observation_data["location"])
        else:
            location = observation_data["location"]
        observation_data["location"] = location
        return ObservationData(**observation_data)


def get_observation_location_and_recorded_at_by_subject_source_id(
    subject_source_id: UUID,
    since=None,
    until=None,
    limit=None,
    values=None,
    filter_flag=0,
    order_by=None,
):
    observation_repository = ObservationRepository()
    qs = observation_repository.get_subjectsource_observations(
        subject_source_id=subject_source_id,
        since=since,
        until=until,
        limit=limit,
        values=values,
        filter_flag=filter_flag,
        order_by=order_by,
    )
    qs = qs.exclude(location=EMPTY_POINT)
    qs = qs.values("location", "recorded_at")

    data = []
    for observation_data in qs:
        data.append(observation_repository.build_dataclass(observation_data=observation_data))
    return data

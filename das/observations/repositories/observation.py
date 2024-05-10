from typing import Any, Dict, Optional
from uuid import UUID

from django.contrib.gis.geos import Point
from django.db.models import Q, QuerySet

from observations.models import Observation

EMPTY_POINT = Point(0, 0)


class ReadDjangoObservationRepository:
    model: Observation = Observation

    @classmethod
    def get(
        cls,
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
            exclude_fields (Optional[Dict[str, Any]]):
                A dictionary of fields and their values to exclude from the queryset.

        Returns:
            QuerySet[Observation]: The resulting queryset of observations.

        """
        qs = cls.model.objects.all()

        if filter_fields:
            qs = qs.filter(**filter_fields)
        if filter_q_fields:
            qs = qs.filter(Q(**filter_q_fields))
        if exclude_fields:
            qs = qs.exclude(**exclude_fields)
        return qs

    @classmethod
    def get_by_id(cls, id: UUID) -> Observation:
        """
        Retrieve an Observation instance by its ID.

        Args:
            id (UUID): The ID of the Observation instance to retrieve.

        Returns:
            Observation: The retrieved Observation instance, or None if it doesn't exist.
        """
        try:
            return cls.model.objects.get(id=id)
        except cls.model.DoesNotExist:
            return None


class ReadEROSObservationRepository:
    pass


class ReadAllSourcesObservationRepository:
    pass


class WriteDjangoObservationRepository:
    pass


class WriteEROSObservationRepository:
    pass


class WriteAllSourcesObservationRepository:
    pass

from typing import Any, Dict, List, Optional
from uuid import UUID

from django.contrib.gis.geos import Point
from django.db.models import F, Q
from django.forms.models import model_to_dict

from observations.models import Observation, SubjectSource
from observations.services.repositories.interfaces import ReadObservationSourceBase

EMPTY_POINT = Point(0, 0)


class ReadDjangoObservationSource(ReadObservationSourceBase):
    def get_object_dict_by_id(self, id: UUID, fields: Optional[List[str]]) -> Dict[str, Any]:
        instance = Observation.objects.get(id=id)
        return model_to_dict(instance, fields=fields) if fields else model_to_dict(instance)

    def get_objects_dict_by_subject_id_and_source_id(
        self,
        subject_id: UUID,
        source_id: UUID,
    ) -> List[Dict[str, Any]]:
        try:
            subject_source = SubjectSource.objects.get(subject_id=subject_id, source_id=source_id)
        except SubjectSource.DoesNotExist:
            return Observation.objects.none()

        since = subject_source.safe_assigned_range.lower
        until = subject_source.safe_assigned_range.upper

        qs = (
            Observation.objects.filter(
                source__subjectsource=subject_source.id,
                source__subjectsource__assigned_range__contains=F("recorded_at"),
                recorded_at__range=[since, until],
            )
            .exclude(Q(location=EMPTY_POINT))
            .values("location", "recorded_at")
        )
        return [model_to_dict(instance) for instance in qs]

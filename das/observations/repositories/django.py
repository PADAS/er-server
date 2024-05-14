from typing import Any, Dict, Optional
from uuid import UUID

from django.contrib.gis.geos import Point
from django.db.models import F, Q, QuerySet
from django.forms.models import model_to_dict

from observations.models import Observation, SubjectSource

EMPTY_POINT = Point(0, 0)


class ReadDjangoObservationMixin:
    def _get_instance_by_id(self, id: UUID, fields: Optional[str] = None) -> QuerySet[Observation]:
        try:
            instance = Observation.objects.get(id=id)
            if not fields:
                return self._model_instance_to_dict(model_instance=instance)
            return instance.values(*fields)
        except Observation.DoesNotExist:
            return None

    def _get_queryset_observations_by_subject_id_and_source_id(
        self,
        subject_id: UUID,
        source_id: UUID,
    ) -> QuerySet[Observation]:
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
        return qs

    def _model_instance_to_dict(self, model_instance: Observation) -> Dict[str, Any]:
        return model_to_dict(
            model_instance,
            fields=[field.name for field in model_instance._meta.fields],
        )

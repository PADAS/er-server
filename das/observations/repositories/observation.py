from typing import Any, Dict, List, Optional
from uuid import UUID

from observations.dataclasess import ObservationData
from observations.repositories.django import ReadDjangoObservationMixin
from observations.repositories.interfaces import ReadObservationRepositoryInterface


class ReadDjangoObservationRepository(ReadObservationRepositoryInterface, ReadDjangoObservationMixin):

    def get_by_id(self, id: UUID, fields: Optional[str] = None) -> ObservationData:
        data = self._get_instance_by_id(id=id, fields=fields)
        if not data:
            return None
        return self.build_dataclass(observation_data=data)

    def get_observations_by_subject_id_and_source_id(
        self,
        subject_id: UUID,
        source_id: UUID,
    ) -> List[ObservationData]:
        observations_dicts = self._get_queryset_observations_by_subject_id_and_source_id(subject_id, source_id)
        if not observations_dicts:
            return []
        return [self.build_dataclass(observation_data) for observation_data in observations_dicts]

    def build_dataclass(self, observation_data: Dict[str, Any]) -> ObservationData:
        return ObservationData(**observation_data)


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

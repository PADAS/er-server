from typing import List, Optional
from uuid import UUID

from observations.domain import ObservationData
from observations.services.repositories.django import ReadDjangoObservationMixin
from observations.services.repositories.interfaces import ReadObservationRepositoryBase


class ReadDjangoObservationRepository(ReadObservationRepositoryBase, ReadDjangoObservationMixin):

    def get_by_id(self, id: UUID, fields: Optional[str] = None) -> ObservationData:
        observation_dict = self._get_instance_by_id(id=id, fields=fields)
        if not observation_dict:
            return None
        return ObservationData.build(data=observation_dict)

    def get_observations_by_subject_id_and_source_id(
        self,
        subject_id: UUID,
        source_id: UUID,
    ) -> List[ObservationData]:
        observations_dicts = self._get_queryset_observations_by_subject_id_and_source_id(subject_id, source_id)

        return ObservationData.build_in_bulk(data=observations_dicts)


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

from typing import List, Optional
from uuid import UUID

from observations.domain import ObservationData
from observations.models import Observation
from observations.services.exceptions import ObservationDoesNotExist
from observations.services.repositories.django import ReadDjangoObservationSource
from observations.services.repositories.interfaces import ReadObservationRepositoryBase

OBSERVATION_SOURCE = "database"  # Temporal Feature Flag
SOURCES = {"database": ReadDjangoObservationSource}


class ReadObservationRepository(ReadObservationRepositoryBase):

    def __init__(self, data_source: str) -> None:
        self.source = SOURCES[data_source]()  # ToDo. Add EROS Source

    def get_by_id(self, id: UUID, fields: Optional[str] = None) -> ObservationData:
        try:
            observation_dict = self.source.get_object_dict_by_id(id=id, fields=fields)
        except Observation.DoesNotExist:  # ToDo. catch EROS exceptions
            raise ObservationDoesNotExist()
        return ObservationData.build(data=observation_dict)

    def get_observations_by_subject_id_and_source_id(
        self,
        subject_id: UUID,
        source_id: UUID,
    ) -> List[ObservationData]:
        observations_dicts = self.source.get_objects_dict_by_subject_id_and_source_id(subject_id, source_id)

        return ObservationData.build_in_bulk(data=observations_dicts)


class WriteDjangoObservationRepository:
    pass


class WriteEROSObservationRepository:
    pass


class WriteAllSourcesObservationRepository:
    pass

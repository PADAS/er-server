from typing import Any, Dict
from uuid import UUID

from observations.services.repositories import ReadObservationRepository

OBSERVATION_SOURCE = "database"  # Temporal Feature Flag


def get_observation_by_id(id: UUID):
    repository = ReadObservationRepository(data_source="database")

    return repository.get_by_id(id=id)


def get_observation_coordinates_and_times_by_subject_id_and_source_id(
    subject_id: UUID, source_id: UUID
) -> Dict[str, Any]:
    coordinates = []
    times = []

    repository = ReadObservationRepository(data_source="database")
    observations_data = repository.get_observations_by_subject_id_and_source_id(
        subject_id=subject_id, source_id=source_id
    )

    for observation in observations_data:
        coordinates.append(observation.location.coords)
        times.append(observation.recorded_at)

    return {"coordinates": coordinates, "times": times}

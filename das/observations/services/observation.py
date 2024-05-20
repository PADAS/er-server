from uuid import UUID

from observations.repositories import ReadDjangoObservationRepository

OBSERVATION_SOURCE = "database"  # Temporal Feature Flag
REPOSITORIES = {"database": ReadDjangoObservationRepository}


def get_observation_by_id(id: UUID):
    repository = REPOSITORIES[OBSERVATION_SOURCE]

    return repository.get_by_id(id=id)


def get_observation_coordinates_and_times_by_subject_id_and_source_id(subject_id: UUID, source_id: UUID):
    coordinates = []
    times = []
    empty_data = {"coordinates": coordinates, "times": times}

    repository = REPOSITORIES[OBSERVATION_SOURCE]
    observations_data = repository.get_observations_by_subject_id_and_source_id(
        subject_id=subject_id, source_id=source_id
    )

    if not observations_data:
        return empty_data

    for observation in observations_data:
        coordinates.append(observation.location.coords)
        times.append(observation.recorded_at)

    return {"coordinates": coordinates, "times": times}

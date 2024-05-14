from uuid import UUID

from observations.repositories import ReadDjangoObservationRepository

SOURCE = 1  # Temporal Feature Flag logic. 1 Django, 2 EROS, 3 Both


def get_observation_by_id(id: UUID):
    if SOURCE == 1:
        repository = ReadDjangoObservationRepository()

    return repository.get_by_id(id=id)


def get_observation_coordinates_and_times_by_subject_id_and_source_id(subject_id: UUID, source_id: UUID):
    coordinates = []
    times = []
    empty_data = {"coordinates": coordinates, "times": times}

    if SOURCE == 1:
        repository = ReadDjangoObservationRepository()

    observations_data = repository.get_observations_by_subject_id_and_source_id(
        subject_id=subject_id, source_id=source_id
    )

    if not observations_data:
        return empty_data

    for observation in observations_data:
        coordinates.append(observation.location.coords)
        times.append(observation.recorded_at)

    return {"coordinates": coordinates, "times": times}

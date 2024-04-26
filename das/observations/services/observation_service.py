from uuid import UUID

from observations.models import SubjectSource
from observations.repositories import (
    get_observation_location_and_recorded_at_by_subject_source_id,
)


def get_observation_coordinates_and_times_by_subject_id_and_source_id(subject_id: UUID, source_id: UUID):
    subject_source = SubjectSource.objects.get(subject_id=subject_id, source_id=source_id)
    lower = subject_source.safe_assigned_range.lower
    upper = subject_source.safe_assigned_range.upper
    coordinates = []
    times = []

    observations_data = get_observation_location_and_recorded_at_by_subject_source_id(
        subject_source_id=subject_source.id,
        since=lower,
        until=upper,
    )

    if not observations_data:
        return {"coordinates": None, "times": None}

    for observation in observations_data:
        coordinates.append(observation.location.coords)
        times.append(observation.recorded_at)

    return {"coordinates": coordinates, "times": times}

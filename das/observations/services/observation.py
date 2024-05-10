from uuid import UUID

from django.contrib.gis.geos import Point
from django.db.models import F

from observations.models import SubjectSource
from observations.repositories import ReadDjangoObservationRepository

EMPTY_POINT = Point(0, 0)

SOURCE = 1  # Teporal Feature Flag logic. 1 Django, 2 EROS, 3 Both


def get_observation_coordinates_and_times_by_subject_id_and_source_id(subject_id: UUID, source_id: UUID):
    coordinates = []
    times = []
    empty_data = {"coordinates": coordinates, "times": times}

    try:
        subject_source = SubjectSource.objects.get(subject_id=subject_id, source_id=source_id)
    except SubjectSource.DoesNotExist:
        return empty_data

    since = subject_source.safe_assigned_range.lower
    until = subject_source.safe_assigned_range.upper

    if SOURCE == 1:
        repository = ReadDjangoObservationRepository()
        qs = repository.get(
            filter_fields={
                "source__subjectsource": subject_source.id,
                "source__subjectsource__assigned_range__contains": F("recorded_at"),
            },
            filter_q_fields={"recorded_at__range": [since, until]},
            exclude_fields={"location": EMPTY_POINT},
        )

        data = qs.values("location", "recorded_at")
        observations_data = list(data)

    if not observations_data:
        return empty_data

    for observation in observations_data:
        coordinates.append(observation["location"].coords)
        times.append(observation["recorded_at"])

    return {"coordinates": coordinates, "times": times}

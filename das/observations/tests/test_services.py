import uuid

import pytest

from observations.services import (
    get_observation_by_id,
    get_observation_coordinates_and_times_by_subject_id_and_source_id,
)


@pytest.mark.django_db
def test_get_observation_coordinates_and_times_by_subject_id_and_source_id_with_data(
    subject_source_with_observations,
) -> None:
    subject_source, observation = subject_source_with_observations
    source = subject_source.source
    subject = subject_source.subject

    data = get_observation_coordinates_and_times_by_subject_id_and_source_id(subject_id=subject.id, source_id=source.id)

    assert isinstance(data, dict)
    assert data == {"coordinates": [observation.location.coords], "times": [observation.recorded_at]}


@pytest.mark.django_db
def test_get_observation_coordinates_and_times_by_subject_id_and_source_id_empty(
    subject, source, subject_source
) -> None:
    subject_source.subject = subject
    subject_source.source = source
    subject_source.save()

    data = get_observation_coordinates_and_times_by_subject_id_and_source_id(subject_id=subject.id, source_id=source.id)

    assert len(data["coordinates"]) == 0
    assert len(data["times"]) == 0


@pytest.mark.django_db
def test_get_observation_coordinates_and_times_by_subject_id_and_source_id_subjectsource_not_found() -> None:
    data = get_observation_coordinates_and_times_by_subject_id_and_source_id(
        subject_id=uuid.uuid4(), source_id=uuid.uuid4()
    )
    assert len(data["coordinates"]) == 0
    assert len(data["times"]) == 0


@pytest.mark.django_db
def test_get_observation_by_id(observation) -> None:
    obj = get_observation_by_id(id=observation.id)

    assert obj.id == observation.id


@pytest.mark.django_db
def test_get_observation_by_id_wring_id() -> None:
    obj = get_observation_by_id(id=uuid.uuid4())

    assert obj is None

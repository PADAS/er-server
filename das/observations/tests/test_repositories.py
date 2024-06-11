import uuid

import pytest

from observations.domain.observation import ObservationData
from observations.services.exceptions import ObservationDoesNotExist
from observations.services.repositories import ReadObservationRepository

repository = ReadObservationRepository("database")


@pytest.mark.django_db
@pytest.mark.parametrize("source", [ReadObservationRepository("database")])
def test_get_observations_instance(observation, source) -> None:
    observation_data = source.get_by_id(id=observation.id)

    assert isinstance(observation_data, ObservationData)
    assert observation_data.id == observation.id


@pytest.mark.django_db
@pytest.mark.parametrize("source", [ReadObservationRepository("database")])
def test_get_observations_instance_does_not_exists(source) -> None:
    with pytest.raises(ObservationDoesNotExist):
        source.get_by_id(id=uuid.uuid4())


@pytest.mark.django_db
@pytest.mark.parametrize("repository", [ReadObservationRepository("database")])
def test_get_observations_by_subject_id_and_source_id(subject_source_with_observations, repository):
    subject = subject_source_with_observations[0].subject
    source = subject_source_with_observations[0].source
    observation = subject_source_with_observations[1]

    data = repository.get_observations_by_subject_id_and_source_id(subject_id=subject.id, source_id=source.id)

    assert data[0].id == observation.id

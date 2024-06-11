import uuid

import pytest

from observations.domain.observation import ObservationData
from observations.services.exceptions import ObservationDoesNotExist
from observations.services.repositories import ReadObservationRepository


@pytest.mark.django_db
@pytest.mark.parametrize("data_source", ["database"])
class TestRepositories:
    def test_get_observations_instance(self, observation, data_source) -> None:
        repository = ReadObservationRepository(data_source)
        observation_data = repository.get_by_id(id=observation.id)

        assert isinstance(observation_data, ObservationData)
        assert observation_data.id == observation.id

    def test_get_observations_instance_does_not_exists(self, data_source) -> None:
        repository = ReadObservationRepository(data_source)

        with pytest.raises(ObservationDoesNotExist):
            repository.get_by_id(id=uuid.uuid4())

    def test_get_observations_by_subject_id_and_source_id(self, subject_source_with_observations, data_source):
        subject = subject_source_with_observations[0].subject
        source = subject_source_with_observations[0].source
        observation = subject_source_with_observations[1]

        repository = ReadObservationRepository(data_source)
        data = repository.get_observations_by_subject_id_and_source_id(subject_id=subject.id, source_id=source.id)

        assert data[0].id == observation.id

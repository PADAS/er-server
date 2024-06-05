import uuid

import pytest

from observations.domain.observation import ObservationData
from observations.services.exceptions import ObservationDoesNotExist
from observations.services.repositories import ReadObservationRepository

repository = ReadObservationRepository("database")


@pytest.mark.django_db
def test_get_observations_instance(observation) -> None:
    observation_data = repository.get_by_id(id=observation.id)

    assert isinstance(observation_data, ObservationData)
    assert observation_data.id == observation.id


@pytest.mark.django_db
def test_get_observations_instance_does_not_exists() -> None:
    with pytest.raises(ObservationDoesNotExist):
        repository.get_by_id(id=uuid.uuid4())

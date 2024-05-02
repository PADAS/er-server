import uuid

import pytest

from observations.dataclasses import ObservationData
from observations.repositories import ObservationRepository


@pytest.mark.django_db
class TestObservationsRepository:
    repository = ObservationRepository()

    def test_get_all(self, five_observations) -> None:
        observations = self.repository.get_all()

        assert isinstance(observations, list)
        assert len(observations) == 5

    def test_get_all_empty(self) -> None:
        observations = self.repository.get_all()

        assert isinstance(observations, list)
        assert len(observations) == 0

    def test_filter(self, five_observations) -> None:
        observation = five_observations[3]
        observations_data = self.repository.filter(
            fields={"source": observation.source, "das_tenant": observation.das_tenant}
        )

        assert isinstance(observations_data, list)
        assert len(observations_data) == 1
        assert observations_data[0].id == observation.id
        assert observations_data[0].source == observation.source.id
        assert observations_data[0].das_tenant == observation.das_tenant.id
        assert observations_data[0].recorded_at == observation.recorded_at

    def test_get_by_id(self, observation) -> None:
        observation_data = self.repository.get_by_id(observation_id=observation.id)

        assert isinstance(observation_data, ObservationData)
        assert observation_data.id == observation.id

    def test_get_by_id_observation_dont_exist(self) -> None:
        observation_data = self.repository.get_by_id(observation_id=uuid.uuid4())

        assert observation_data is None

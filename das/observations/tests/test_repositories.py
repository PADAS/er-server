import uuid

import pytest

from observations.models import Observation
from observations.services.repositories.observation import (
    ReadDjangoObservationRepository,
)

repository = ReadDjangoObservationRepository()


@pytest.mark.django_db
def test_get_observations_queryset_get_all(five_observations) -> None:
    qs = repository.get()

    assert qs.count() == 5


@pytest.mark.django_db
def test_get_observations_queryset_with_simple_filters(five_observations) -> None:
    observation = five_observations[1]

    qs = repository.get(filter_fields={"id": observation.pk})

    assert qs.count() == 1
    assert observation.id == qs[0].id


@pytest.mark.django_db
def test_get_observations_queryset_with_q_filters(subject_source_with_observations) -> None:
    subject_source, observation = subject_source_with_observations
    since = subject_source.safe_assigned_range.lower
    until = subject_source.safe_assigned_range.upper

    filter_q = {"recorded_at__range": [since, until]}

    qs = repository.get(filter_q_fields=filter_q)

    assert qs[0].id == observation.id


@pytest.mark.django_db
def test_get_observations_queryset_with_exclude(five_observations) -> None:
    excluded_observation = five_observations[0]

    qs = repository.get(
        exclude_fields={"id": excluded_observation.id},
    )

    assert qs.count() == 4
    assert qs.filter(id=excluded_observation.id).count() == 0


@pytest.mark.django_db
def test_get_observations_instance(observation) -> None:
    obj = repository.get_by_id(id=observation.id)

    assert isinstance(obj, Observation)
    assert obj.id == observation.id


@pytest.mark.django_db
def test_get_observations_instance_does_not_exists() -> None:
    obj = repository.get_by_id(id=uuid.uuid4())

    assert obj is None

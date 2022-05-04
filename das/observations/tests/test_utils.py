from datetime import datetime

import pytest
import pytz

from django.contrib.gis.geos import Point

from observations.models import (STATIONARY_SUBJECT_VALUE, Observation,
                                 SubjectType)
from observations.utils import is_observation_stationary_subject


@pytest.mark.django_db
class TestObservationUtils:

    def test_is_an_observation_for_stationary_subject(self, subject_source):
        source = subject_source.source
        subject_type_stationary_object = SubjectType.objects.get(
            value=STATIONARY_SUBJECT_VALUE)
        subject = subject_source.subject
        subject.subject_subtype.subject_type = subject_type_stationary_object
        subject.subject_subtype.save()

        observation = Observation.objects.create(
            recorded_at=datetime.now(tz=pytz.utc),
            location=Point(0, 0),
            source=source
        )

        assert is_observation_stationary_subject(observation)

    def test_is_not_an_observation_for_stationary_subject(self, subject_source):
        source = subject_source.source
        subject_type_stationary_object = SubjectType.objects.get(
            value="vehicle")
        subject = subject_source.subject
        subject.subject_subtype.subject_type = subject_type_stationary_object
        subject.subject_subtype.save()

        observation = Observation.objects.create(
            recorded_at=datetime.now(tz=pytz.utc),
            location=Point(0, 0),
            source=source
        )

        assert not is_observation_stationary_subject(observation)

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import pytz
from django.contrib.gis.geos import Point

from observations.models import (STATIONARY_SUBJECT_VALUE, Observation,
                                 SubjectType)
from observations.utils import calculate_speed, has_exceed_speed
from observations.utils import is_observation_stationary_subject

positions = [
    {
        "datetime": 1664722800.0,
        "position": {
            "latitude": 19.62706626871261,
            "longitude": -104.1229248046875,
        },
    },
    {
        "datetime": 1664719200.0,
        "position": {
            "latitude": 21.099875492701216,
            "longitude": -105.00732421875,
        },
    },
]

positions2 = [
    {
        "datetime": 1664722800.0,
        "position": {
            "latitude": 19.62706626871261,
            "longitude": -104.1229248046875,
        },
    },
    {
        "datetime": 1664719200.0,
        "position": {
            "latitude": 19.769288277210887,
            "longitude": -104.4305419921875,
        },
    },
]


@pytest.mark.django_db
class TestSpeedCalculation:
    @patch("observations.utils.remove_outdated_positions", return_value=None)
    @patch("observations.utils.get_parsed_positions", return_value=positions)
    def test_calculate_speed(self, monkeypatch, another):
        user = MagicMock()

        speed = calculate_speed(user)

        assert int(speed) == 187

    @patch("observations.utils.remove_outdated_positions", return_value=None)
    @patch("observations.utils.get_parsed_positions", return_value=positions)
    def test_user_has_exceed_speed(self, monkeypatch, another):
        user = MagicMock()

        exceed_speed = has_exceed_speed(user)

        assert exceed_speed

    @patch("observations.utils.remove_outdated_positions", return_value=None)
    @patch("observations.utils.get_parsed_positions", return_value=positions2)
    def test_user_has_not_exceed_speed(self, monkeypatch, another):
        user = MagicMock()

        exceed_speed = has_exceed_speed(user)

        assert not exceed_speed


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

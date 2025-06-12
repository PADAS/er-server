from unittest.mock import MagicMock, patch

import pytest

from observations.utils import calculate_speed, has_exceed_speed

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
@pytest.mark.usefixtures("tenant_settings")
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

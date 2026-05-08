from datetime import datetime, timedelta
from datetime import timezone as tz
from unittest.mock import MagicMock, Mock, patch
from zoneinfo import ZoneInfo

import pytest

from django.utils import timezone

from utils.date import convert_to_timezone, get_current_time_zone, get_timezone_offset


@pytest.fixture
def get_current_timezone_name_mock():
    mock = MagicMock()
    mock.return_value = "America/New_York"
    return mock


@pytest.fixture
def mock_time_zone():
    mock = MagicMock()
    mock.return_value = tz(timedelta(hours=2))
    return mock


def test_get_timezone_offset_utc():
    current_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tz.utc)
    assert get_timezone_offset(current_date) == "GMT+0:0"


def test_get_timezone_offset_positive_offset():
    tzinfo = tz(timedelta(hours=5, minutes=30))
    current_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tzinfo)
    assert get_timezone_offset(current_date) == "GMT+5:30"


def test_get_timezone_offset_negative_offset():
    tzinfo = tz(timedelta(hours=-4))
    current_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tzinfo)
    assert get_timezone_offset(current_date) == "GMT-4:0"


def test_get_current_time_zone_non_utc():
    current_tz = ZoneInfo(timezone.get_current_timezone_name())

    assert current_tz == get_current_time_zone()


def test_convert_naive_datetime(mock_time_zone: Mock):
    naive_date = datetime(2023, 10, 1, 12, 0, 0)
    expected_date = naive_date.replace(tzinfo=tz.utc).astimezone(tz=mock_time_zone.return_value)

    with patch("utils.date.get_current_time_zone", mock_time_zone):
        with patch("utils.date.is_naive", return_value=True):
            result = convert_to_timezone(naive_date)
            assert result == expected_date


def test_convert_aware_datetime(mock_time_zone: Mock):
    aware_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tz.utc)
    expected_date = aware_date.astimezone(tz=mock_time_zone.return_value)

    with patch("utils.date.get_current_time_zone", mock_time_zone):
        with patch("utils.date.is_naive", return_value=False):
            result = convert_to_timezone(aware_date)
            assert result == expected_date


def test_convert_to_timezone_specific_tz():
    specific_tz = tz(timedelta(hours=5, minutes=30))
    aware_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tz.utc)
    expected_date = aware_date.astimezone(tz=specific_tz)
    assert convert_to_timezone(aware_date, specific_tz) == expected_date

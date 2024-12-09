from datetime import datetime, timedelta
from datetime import timezone as tz
from datetime import tzinfo
from unittest.mock import MagicMock, patch

import pytest
import pytz

from django.utils import timezone
from django.utils.timezone import is_naive


def get_timezone_offset(current_date: datetime) -> str:
    tz_difference = current_date.utcoffset().total_seconds() / 60 / 60
    tz_offset = (
        f"GMT{'+' if tz_difference >= 0 else ''} {int(tz_difference)}:{int((tz_difference - int(tz_difference)) * 60)}"
    )
    return tz_offset


def get_current_time_zone() -> tzinfo:
    current_tz_name = timezone.get_current_timezone_name()
    current_tz = pytz.timezone(zone=current_tz_name)
    return current_tz


def convert_to_timezone(date: datetime, time_zone: tzinfo = get_current_time_zone()):
    if is_naive(date):
        date = date.replace(tzinfo=timezone.utc)

    result = date.astimezone(tz=time_zone)
    return result


@pytest.fixture
def mock_time_zone():
    mock = MagicMock()
    mock.return_value = tz(timedelta(hours=2))
    return mock


def test_convert_naive_datetime(mock_time_zone):
    naive_date = datetime(2023, 10, 1, 12, 0, 0)
    expected_date = naive_date.replace(tzinfo=tz.utc).astimezone(tz=mock_time_zone.return_value)

    with patch("utils.date.get_current_time_zone", mock_time_zone):
        with patch("utils.date.is_naive", return_value=True):
            result = convert_to_timezone(naive_date)
            assert result == expected_date


def test_convert_aware_datetime(mock_time_zone):
    aware_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tz.utc)
    expected_date = aware_date.astimezone(tz=mock_time_zone.return_value)

    with patch("utils.date.get_current_time_zone", mock_time_zone):
        with patch("utils.date.is_naive", return_value=False):
            result = convert_to_timezone(aware_date)
            assert result == expected_date

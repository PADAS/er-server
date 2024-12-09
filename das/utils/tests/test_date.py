from datetime import datetime, timedelta, timezone

import pytz

from django.utils import timezone

from utils.date import convert_to_timezone, get_current_time_zone, get_timezone_offset


def test_get_timezone_offset_utc():
    current_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert get_timezone_offset(current_date) == "GMT+ 0:0"


def test_get_timezone_offset_positive_offset():
    tzinfo = timezone(timedelta(hours=5, minutes=30))
    current_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tzinfo)
    assert get_timezone_offset(current_date) == "GMT+ 5:30"


def test_get_timezone_offset_negative_offset():
    tzinfo = timezone(timedelta(hours=-4))
    current_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=tzinfo)
    assert get_timezone_offset(current_date) == "GMT- 4:0"


def test_get_current_time_zone_non_utc(mocker):
    mocker.patch("django.utils.timezone.get_current_timezone_name", return_value="America/New_York")

    current_tz = get_current_time_zone()

    assert current_tz == pytz.timezone("America/New_York")


def test_convert_to_timezone_naive(mocker):
    mocker.patch("utils.date.get_current_time_zone", return_value=timezone(timedelta(hours=2)))
    naive_date = datetime(2023, 10, 1, 12, 0, 0)
    expected_date = naive_date.replace(tzinfo=timezone.utc).astimezone(tz=timezone(timedelta(hours=2)))
    assert convert_to_timezone(naive_date) == expected_date


def test_convert_to_timezone_aware(mocker):
    mocker.patch("utils.date.get_current_time_zone", return_value=timezone(timedelta(hours=2)))
    aware_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    expected_date = aware_date.astimezone(tz=timezone(timedelta(hours=2)))
    assert convert_to_timezone(aware_date) == expected_date


def test_convert_to_timezone_specific_tz():
    specific_tz = timezone(timedelta(hours=5, minutes=30))
    aware_date = datetime(2023, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    expected_date = aware_date.astimezone(tz=specific_tz)
    assert convert_to_timezone(aware_date, specific_tz) == expected_date

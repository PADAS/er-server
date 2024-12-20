"""
Helper functions to deal with dates and timezones.
"""

from datetime import datetime, tzinfo

import pytz

from django.utils import timezone
from django.utils.timezone import is_naive


def get_timezone_offset(current_date: datetime) -> str:
    """
    Return the offset of `current_date` to UTC as a string.
    """
    tz_difference = current_date.utcoffset().total_seconds() / 60 / 60
    tz_offset = (
        f"GMT{'+' if tz_difference >= 0 else ''}{int(tz_difference)}:{int((tz_difference - int(tz_difference)) * 60)}"
    )
    return tz_offset


def get_current_time_zone() -> tzinfo:
    """
    Return the current timezone used by the django server.
    """
    current_tz_name = timezone.get_current_timezone_name()
    current_tz = pytz.timezone(zone=current_tz_name)
    return current_tz


def convert_to_timezone(date: datetime, time_zone: tzinfo = get_current_time_zone()):
    """
    Convert the provided `date` that can be set to any timezone into the `time_zone`.

    Args:
        date (datetime): datetime to convert.
        time_zone (tzinfo): timezone to use.

    Returns:
        tz_date (datetime): new date representing the `date` in the `time_zone`.
    """
    if is_naive(date):
        date = date.replace(tzinfo=timezone.utc)

    result = date.astimezone(tz=time_zone)
    return result

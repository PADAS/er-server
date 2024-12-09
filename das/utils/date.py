from datetime import datetime, tzinfo

import pytz

from django.utils import timezone
from django.utils.timezone import is_naive


def get_timezone_offset(current_date: datetime) -> str:
    tz_difference = current_date.utcoffset().total_seconds() / 60 / 60
    tz_offset = (
        f"GMT{'+' if tz_difference >= 0 else ''}{int(tz_difference)}:{int((tz_difference - int(tz_difference)) * 60)}"
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

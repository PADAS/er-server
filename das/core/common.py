from django.utils.timezone import get_default_timezone_name


def timezone_used():
    tz = get_default_timezone_name()
    return tz

TIMEZONE_USED = timezone_used()
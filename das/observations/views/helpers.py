from datetime import datetime
from typing import Optional

from observations.utils import dateparse


def check_valid_date_string(date_str: Optional[str], parameter_name: str) -> (bool, Optional[datetime]):
    if not date_str:
        return False, None

    try:
        return True, dateparse(date_str)
    except ValueError:
        raise ValueError("Invalid value for %s: '%s'" % (parameter_name, date_str))

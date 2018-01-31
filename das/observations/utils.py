from datetime import datetime, timedelta
import pytz

from observations.models import Subject
import logging

logger = logging.getLogger(__name__)


def calculate_subject_view_window(user, maximum_history_days=60):
    '''
    For the given user, calculate the Subject Tracks View Window timestamps.
    :param user: A DAS user
    :param maximum_history_days: A maximum number days 'from now'.
    :return: 2-tuple with (lower, upper) timestamps.
    '''

    current_timestamp = datetime.now(tz=pytz.utc)

    # Ratchet down the 'begin days ago' according to available
    # view-window-permissions.
    try:
        x, begin_days_ago = next(
            p for p in Subject.VIEW_BEGIN_ORDERED_DESC if user.has_perm(p[0]))
    except StopIteration:
        begin_days_ago = -1

    # Ratchet up the 'end days ago' according to available
    # view-window-permissions.
    try:
        x, end_days_ago = next(
            p for p in Subject.VIEW_END_ORDERED_ASC if user.has_perm(p[0]))
    except StopIteration:
        end_days_ago = 1000

    begin_days_ago = min(begin_days_ago, maximum_history_days)

    (lower, upper) = current_timestamp - timedelta(days=begin_days_ago), \
        current_timestamp - timedelta(days=end_days_ago)

    # If a user is tagged with an 'expiry' date, adjust accordingly.
    expiry_date = getattr(user, 'mou_expiry_date', None)
    if expiry_date:
        (lower, upper) = (min(lower, expiry_date), min(upper, expiry_date))

    return lower, upper

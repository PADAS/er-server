import logging
from datetime import datetime, timedelta

import dateutil.parser
import pytz
from django.core.exceptions import PermissionDenied
from django.conf import settings

logger = logging.getLogger(__name__)


VIEW_POSITION_PERMS = ('observations.view_last_position',
                       'observations.view_real_time')
VIEW_DELAYED_PERMS = ('observations.view_delayed',)

VIEW_BEGIN_WINDOWS = (('observations.access_begins_7', 7),
                      ('observations.access_begins_16', 16),
                      ('observations.access_begins_30', 30),
                      ('observations.access_begins_60', 60),
                      ('observations.access_begins_all', 36500))

VIEW_END_WINDOWS = (('observations.access_ends_0', 0),
                    ('observations.access_ends_1', 1),
                    ('observations.access_ends_3', 3),
                    ('observations.access_ends_7', 7))

VIEW_BEGIN_ORDERED_DESC = sorted(
    VIEW_BEGIN_WINDOWS, key=lambda _: _[1], reverse=True)
VIEW_END_ORDERED_ASC = sorted(VIEW_END_WINDOWS, key=lambda _: _[1])

VIEW_SUBJECT_PERMS = ('observations.view_subject',) + \
    VIEW_BEGIN_WINDOWS + VIEW_END_WINDOWS


def get_maximum_allowed_age(user):
    maximum_allowed_age = None
    for permission_tuple in sorted(VIEW_BEGIN_WINDOWS,
                                   key=lambda _: _[1], reverse=True):
        if user.has_perm(permission_tuple[0]) and (
                maximum_allowed_age is None or permission_tuple[1] > maximum_allowed_age):
            maximum_allowed_age = permission_tuple[1]
            break
    return maximum_allowed_age


def get_minimum_allowed_age(user):
    minimum_allowed_age = None
    for permission_tuple in sorted(VIEW_END_WINDOWS,
                                   key=lambda _: _[1]):
        if user.has_perm(permission_tuple[0]) and (
                minimum_allowed_age is None or permission_tuple[1] < minimum_allowed_age):
            minimum_allowed_age = permission_tuple[1]
            break
    return minimum_allowed_age


def calculate_track_range(user, since, until, limit):
    """
    Find the min and max boundaries for track data based on user permissions

    :param user:
    :param since:
    :param until:
    :param limit:
    :return: Max number of observations in the track
    """
    oldest_age_allowed = -1
    newest_age_allowed = 999
    mou_expiry_date = user.additional.get('expiry', None)

    for permission_tuple in sorted(VIEW_BEGIN_WINDOWS,
                                   key=lambda _: _[1], reverse=True):
        if permission_tuple[
            1] > oldest_age_allowed and user.has_perm(
                permission_tuple[0]):
            oldest_age_allowed = permission_tuple[1]
            break

    for permission_tuple in sorted(VIEW_END_WINDOWS,
                                   key=lambda _: _[1]):
        if permission_tuple[
            1] < newest_age_allowed and user.has_perm(
                permission_tuple[0]):
            newest_age_allowed = permission_tuple[1]
            break

    if oldest_age_allowed < 0 or newest_age_allowed > oldest_age_allowed:
        raise PermissionDenied

    requested_oldest_age = since
    requested_newest_age = until

    now = pytz.utc.localize(datetime.utcnow())

    if requested_oldest_age is None:
        oldest_age = min(settings.SHOW_TRACK_DAYS, oldest_age_allowed)
    else:
        requested_oldest_age = (now - requested_oldest_age).days
        oldest_age = min(requested_oldest_age, oldest_age_allowed)

    if requested_newest_age is None:
        newest_age = newest_age_allowed
    else:
        requested_newest_age = (now - requested_newest_age).days
        newest_age = max(requested_newest_age, newest_age_allowed)

    if mou_expiry_date is not None:
        now = pytz.utc.localize(datetime.utcnow())
        mou_expiry_date = pytz.utc.localize(
            dateutil.parser.parse(mou_expiry_date))
        mou_expiry_age = now - mou_expiry_date

        newest_age = max(mou_expiry_age.days, newest_age)
        if oldest_age < newest_age:
            raise PermissionDenied()

    begin = now - timedelta(days=oldest_age)

    if newest_age > 0:
        until = now - timedelta(days=newest_age)
    else:
        until = now + timedelta(minutes=20)

    return begin, until, limit


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
            p for p in VIEW_BEGIN_ORDERED_DESC if user.has_perm(p[0]))
    except StopIteration:
        begin_days_ago = -1

    # Ratchet up the 'end days ago' according to available
    # view-window-permissions.
    try:
        x, end_days_ago = next(
            p for p in VIEW_END_ORDERED_ASC if user.has_perm(p[0]))
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

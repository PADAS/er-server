import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

import dateutil.parser
import pytz
from dateutil.parser import parse
from geopy.distance import geodesic
from pytz import timezone

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Aggregate

from core import persistent_storage

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

VIEW_SUBJECTGROUP_PERMS = ('observations.view_subjectgroup', )

VIEW_OBSERVATION_PERMS = ('observations.view_observation', )

LOCATION = "location"
GEO_BANNED = "geo-banned"


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
        mou_expiry_date = dateutil.parser.parse(mou_expiry_date)
        if not mou_expiry_date.tzinfo:
            mou_expiry_date = pytz.utc.localize(mou_expiry_date)
        mou_expiry_age = now - mou_expiry_date

        newest_age = max(mou_expiry_age.days, newest_age)
        # if oldest_age < newest_age:
        #     raise PermissionDenied()

    if since:
        age_secs = (now - since).seconds
        if oldest_age == 0 and since.date() == now.date():
            begin = now - timedelta(seconds=age_secs)
        else:
            begin = now - timedelta(days=oldest_age, seconds=age_secs)
    else:
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


def check_to_include_inactive_subjects(request, full_queryset):
    # by default return only active subjects
    queryset = full_queryset.by_is_active()

    # return all subjects if parameter is passed and set to true
    params = request.GET.get("include_inactive", None)
    try:
        if params and json.loads(params.lower()):
            queryset = full_queryset
    except Exception:
        pass
    return queryset


def assigned_range_dates(o):
    # return subject source assigned range dates
    start_date, end_date = o.safe_assigned_range.lower, o.safe_assigned_range.upper
    if start_date.year <= 1000:
        start_date = '-'
    if end_date.year >= 9999:
        end_date = '-'
    return start_date, end_date


def convert_date_string(date_str):
    # Get timezone from settings and convert date_string into datetime object
    # with settings's timezone
    time_zone = timezone(settings.TIME_ZONE)
    datetime_object = parse(date_str)
    localize_date = time_zone.localize(datetime_object)

    # Convert datetime's timezone with UTC
    utc_date = localize_date.astimezone(timezone('UTC'))
    return utc_date.isoformat()


def dateparse(date_str: str, default_tz=pytz.utc):
    dt = dateutil.parser.parse(date_str)
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=default_tz)
    return dt


def get_null_point():
    from django.contrib.gis.geos import Point
    point = Point(0, 0)
    return point


def get_chunk_file(file, chunksize=5120):
    return iter(lambda: file.read(chunksize), b'')


def ensure_timezone_aware(dt: datetime, default_timezone: timezone = pytz.utc):
    if dt is None:
        return dt

    return dt if dt.tzinfo else dt.replace(tzinfo=default_timezone)


def get_cyclic_subjectgroup():
    with connection.cursor() as cursor:
        cursor.execute("""
        WITH RECURSIVE graph AS (
            SELECT from_subjectgroup_id
            , ARRAY[to_subjectgroup_id, from_subjectgroup_id] AS path
            , (to_subjectgroup_id = from_subjectgroup_id) AS cycle
            FROM  observations_subjectgroup_children

            UNION ALL

            SELECT sgc.from_subjectgroup_id,
                sgc.to_subjectgroup_id || path ,
                sgc.to_subjectgroup_id = ANY(path)
            FROM   graph g
            JOIN   observations_subjectgroup_children sgc ON sgc.from_subjectgroup_id = g.path[1]
            WHERE  NOT g.cycle
        )
        SELECT DISTINCT graph.from_subjectgroup_id 
        FROM   graph
        JOIN observations_subjectgroup sg ON sg.id = graph.from_subjectgroup_id
        WHERE  cycle;
        """)
        return [row[0] for row in cursor.fetchall()]


def find_paths(item, accum=None, prefix=None):
    """
    Accumulate unique "paths" along with sample data.
    :param item:
    :param accum:
    :param prefix:
    :return:
    """

    accum = accum if accum is not None else {}
    prefix = prefix or []

    if isinstance(item, (str, bool, int, float)):
        accum.setdefault('.'.join(prefix), set()).add(item)

    elif isinstance(item, dict):
        for k, v in item.items():
            if isinstance(v, (list, dict)):
                find_paths(v, accum=accum, prefix=prefix + [k])
            else:
                accum.setdefault('.'.join(prefix + [k]), set()).add(v)

    elif isinstance(item, list):
        for v in item:
            find_paths(v, accum=accum, prefix=prefix + ['[]'])


class JsonAgg(Aggregate):
    function = 'jsonb_agg'
    template = '%(function)s(to_jsonb(%(expressions)s))'


def parse_comma(q):
    """Parse comma-separated query param"""
    if q:
        vals = [v.strip() for v in q.split(',')]
        try:
            return list(map(uuid.UUID, vals))
        except ValueError:
            return vals
        except TypeError:
            return vals
    return


def has_exceed_speed(user):
    speed = calculate_speed(user)
    exceed = speed > settings.GEO_PERMISSION_SPEED_KM_H
    if exceed:
        logger.info(
            f"Speed exceed for user {user.username} with id {user.id}, speed {speed}")
    return exceed


def get_position(key):
    value = persistent_storage.get_latest_item_in_sorted_set(key)
    if value:
        decoded_value = value[0].decode("utf8")
        return json.loads(decoded_value)
    return None


def calculate_speed(user):
    remove_outdated_positions(user)
    key = get_user_key(user, LOCATION)
    positions = get_parsed_positions(key)
    if positions:
        distance = get_distance_points(positions)
        lag_in_hour = get_lag_hours(
            first_datetime=positions[0].get("datetime"),
            second_datetime=positions[-1].get("datetime"),
        )
        if distance and lag_in_hour:
            return distance.km / lag_in_hour
    return 0


def remove_outdated_positions(user):
    key = get_user_key(user, LOCATION)
    now_before_two_hours = datetime.timestamp(
        datetime.now() - timedelta(hours=2))
    persistent_storage.slice_sorted_set(key, now_before_two_hours)


def get_parsed_positions(key):
    positions = persistent_storage.get_sorted_set(key)
    return [
        json.loads(position.decode("utf8")) for position in positions
    ]


def get_distance_points(positions):
    points = tuple(
        (
            position.get("position").get("latitude"),
            position.get("position").get("longitude"),
        )
        for position in positions
    )
    if len(points) > 1:
        return geodesic(*points)
    return 0


def get_lag_hours(first_datetime: float, second_datetime: float):
    """
    Return the difference of two timestamp in hours, rounded two decimals
    """
    lag = datetime.fromtimestamp(first_datetime) - \
        datetime.fromtimestamp(second_datetime)
    return round(((lag.seconds / 60) / 60), 2)


def block_user_temp(user):
    if has_exceed_speed(user):
        key = get_user_key(user, GEO_BANNED)
        persistent_storage.insert_key(
            key, True, settings.GEO_PERMISSION_VIOLATION_BAN_DURATION_MIN * 60)
        logger.info(
            f"Banning user {user.username} with ID {user.id} for {settings.GEO_PERMISSION_VIOLATION_BAN_DURATION_MIN} minutes.")
        persistent_storage.delete_key(get_user_key(user, LOCATION))


def get_user_key(user, key: str):
    return f"{key}:{user.id}"


def is_banned(user):
    key = get_user_key(user, GEO_BANNED)
    return persistent_storage.get_key(key)


def is_subject_stationary_subject(subject):
    return subject.subject_subtype.subject_type.value == "stationary-object"


def is_observation_stationary_subject(observation):
    subject_source = observation.source.subjectsource_set.last()
    if subject_source:
        return is_subject_stationary_subject(subject_source.subject)
    return False

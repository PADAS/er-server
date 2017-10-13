import logging
import collections
import redis
import datetime
import pytz

from django.contrib.gis.geos import Polygon, MultiPolygon
from observations.models import SocketClient

from django.conf import settings
from utils import json

logger = logging.getLogger(__name__)
redis_client = redis.from_url(settings.REALTIME_BROKER_URL)
CLIENT_LIST_KEY = 'realtime_connections'

FIELDS = ['username', 'sid', 'bbox']
ClientData = collections.namedtuple('ClientData', FIELDS)

# bbox, where bbox is the (west, south, east, north) lon,lat pairs.
BBOX_FIELDS = ['west', 'south', 'east', 'north']
Bbox = collections.namedtuple('Bbox', BBOX_FIELDS)


def now(tz=pytz.utc):
    return tz.localize(datetime.datetime.utcnow())


def update_client(sid, bbox=None, event_filter=None):
    sid = str(sid)
    logger.info('update_client, sid: %s', sid)
    client_data = get_client(sid)

    # Sometimes we get back None from get_client (per messages in
    # realtime-stderr.log)
    if client_data:
        client_data = ClientData(sid=client_data.sid,
                                 username=client_data.username,
                                 bbox=bbox)
        add_client(sid, client_data)

        update_values = {}
        if bbox:
            bbox_geom = MultiPolygon(Polygon.from_bbox(bbox))
            update_values['bbox'] = bbox_geom
        if event_filter:
            update_values['event_filter'] = event_filter

        if update_values:
            update_values['username'] = client_data.username
            socket_client, created = SocketClient.objects.update_or_create(
                id=sid, defaults=update_values)


def get_client_list():
    for data in redis_client.hgetall(CLIENT_LIST_KEY).items():
        sid = str(data[0], 'utf-8')
        c = _restore_client_data(str(data[1], 'utf-8'))
        if c:
            client_data = c
            yield client_data
        else:
            remove_client(sid)


def add_client(sid, data):
    sid = str(sid)
    logger.info('Adding socket client. sid=%s, data=%s', sid, data)
    logger.info('Adding client to session list. key=%s, sid=%s, data=%s',
                CLIENT_LIST_KEY, sid, json.dumps(data))
    hset_result = redis_client.hset(
        CLIENT_LIST_KEY, sid, json.dumps(data))
    logger.info('hset_result = %s', hset_result)


def _restore_client_data(data):
    try:
        data = json.loads(data)
    except json.JSONDecodeError:
        data = None
    if not data or isinstance(data, str) or isinstance(data, int):
        return None

    bbox = Bbox(**data['bbox']) if data.get('bbox') else None
    return ClientData(sid=data['sid'],
                      username=data['username'],
                      bbox=bbox)


def get_client(sid):
    sid = str(sid)
    logger.debug('Get client for sid=%s', sid)
    data = str(redis_client.hget(CLIENT_LIST_KEY, sid), 'utf-8')

    logger.debug('Got client for sid=%s, data=%s', sid, data)
    if data:
        return _restore_client_data(data)


def is_client(sid):
    return redis_client.hexists(CLIENT_LIST_KEY, sid)


def remove_client(sid):
    sid = str(sid)
    logger.info('Removing client for sid: %s', sid)
    redis_client.hdel(CLIENT_LIST_KEY, sid)
    try:
        SocketClient.objects.filter(id=sid).delete()
    except ValueError:
        logger.exception('Invalid sid deleting SocketClient record: %s', sid)

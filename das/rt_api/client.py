import logging
import collections
import redis
import datetime

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

import pytz


def now(tz=pytz.utc):
    return tz.localize(datetime.datetime.utcnow())


def update_client(sid, bbox=None, event_filter=None):
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
        c = _restore_client_data(data[1])
        if c:
            client_data = c
            yield client_data


def add_client(sid, data):
    redis_client.hset(CLIENT_LIST_KEY, str(sid), json.dumps(data))


def _restore_client_data(data):
    data = json.loads(str(data, 'utf-8'))
    if isinstance(data, str) or isinstance(data, int):
        return None

    bbox = Bbox(**data['bbox']) if data.get('bbox') else None
    return ClientData(sid=data['sid'],
                      username=data['username'],
                      bbox=bbox)


def get_client(sid):
    data = redis_client.hget(CLIENT_LIST_KEY, str(sid))
    if data:
        return _restore_client_data(data)


def is_client(sid):
    return redis_client.hexists(CLIENT_LIST_KEY, str(sid))


def remove_client(sid):
    redis_client.hdel(CLIENT_LIST_KEY, str(sid))
    SocketClient.objects.filter(id=sid).delete()

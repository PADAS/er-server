import logging
import collections
import socket
import uuid

import redis
import datetime
import pytz

from django.contrib.gis.geos import Polygon, MultiPolygon
from observations.models import SocketClient

from django.conf import settings
from utils import json

logger = logging.getLogger(__name__)
redis_client = redis.from_url(settings.REALTIME_BROKER_URL)

# intended to be long lived
# XXX see if there is a better key mapped
SERVICE_UUID = uuid.uuid4().hex
CLIENT_LIST_KEY = 'rt_api.{}.service'.format(SERVICE_UUID)
REALTIME_SERVICES_KEY = 'rt_api.services'

FIELDS = ['username', 'sid', 'bbox']
ClientData = collections.namedtuple('ClientData', FIELDS)

# bbox, where bbox is the (west, south, east, north) lon,lat pairs.
BBOX_FIELDS = ['west', 'south', 'east', 'north']
Bbox = collections.namedtuple('Bbox', BBOX_FIELDS)

# add the service as a member of a set
redis_client.sadd(REALTIME_SERVICES_KEY, CLIENT_LIST_KEY)


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


def update_ttl(sid, ttl_ms):
    ''' TODO: Add expiry value to hash entry sid:json_blob:ttl_ms '''
    pass


def get_all_client_list():
    '''
    Grab the existing client lists, and iterate through them,
    deleting the empty sessions. We hold onto the server key,
    as we iterate, if we need to delete them
    TODO Refactor this method and get_client_list - DRY
    '''
    client_list = {}
    for rt_server_key in get_rt_service_list():
        clients = redis_client.hgetall(rt_server_key)
        if clients:
            client_list[rt_server_key] = clients
    for key in client_list:
        for client in client_list[key].items():
            sid = client[0].decode('utf-8')
            c = _restore_client_data(client[1].decode('utf-8'))
            if c:
                client_data = c
                yield client_data
            else:
                remove_client(sid)


def get_client_list(server_key=CLIENT_LIST_KEY):
    '''
    Grab the existing client lists, and iterate through them,
    deleting the empty sessions. We hold onto the server key,
    as we iterate, if we need to delete them
    '''
    for data in redis_client.hgetall(server_key).items():
        sid = data[0].decode('utf-8')
        c = _restore_client_data(data[1].decode('utf-8'))
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
    hset_result = redis_client.hset(CLIENT_LIST_KEY, sid, json.dumps(data),  )
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
                      filter=data['filter'],
                      bbox=bbox)


def get_client(sid):
    sid = str(sid)
    logger.debug('Get client for sid=%s', sid)
    data = redis_client.hget(CLIENT_LIST_KEY, sid)
    if data:
        data = data.decode('utf-8')
        result = _restore_client_data(data)
        if result:
            logger.debug('Got client for sid=%s, data=%s', sid, data)
            return result


def is_client(sid):
    return redis_client.hexists(CLIENT_LIST_KEY, str(sid))


def remove_client(cl_key=CLIENT_LIST_KEY, sid):
    remove_clients(cl_key, sid)


def remove_clients(cl_key=CLIENT_LIST_KEY, *sids):
    '''
    Handle a list of sids to delete them from both the database and cache.
    :param sids:
    :return:
    '''
    if not sids:
        return

    sids = set((str(sid) for sid in sids))
    logger.info('Removing clients for sids: %s', sids)
    redis_client.hdel(cl_key, *sids)
    try:
        SocketClient.objects.filter(id__in=sids).delete()
    except ValueError:
        logger.exception('Failed to remove SocketClients for sids: %s', sids)


def get_rt_service_list():
    '''
    :return: List of realtime services that have registered with redis.
    '''
    services = redis_client.smembers(REALTIME_SERVICES_KEY)
    return services


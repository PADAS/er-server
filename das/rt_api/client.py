import logging
import collections
import redis
import datetime
import pytz
import socket
import atexit

from django.contrib.gis.geos import Polygon, MultiPolygon
from observations.models import SocketClient

from django.conf import settings
from utils import json

logger = logging.getLogger(__name__)
redis_client = redis.from_url(settings.REALTIME_BROKER_URL)


# looks like socket.gethostname is not viable on all python distros,
# so we make a connection to a private address, and get the host ip
def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]


SERVICE_ID = str(get_ip_address())
CLIENT_LIST_KEY = 'rt_api.{}'.format(SERVICE_ID)
REALTIME_SERVICES_KEY = 'rt_api.services'


FIELDS = ['username', 'sid', 'bbox']
ClientData = collections.namedtuple('ClientData', FIELDS)

# bbox, where bbox is the (west, south, east, north) lon,lat pairs.
BBOX_FIELDS = ['west', 'south', 'east', 'north']
Bbox = collections.namedtuple('Bbox', BBOX_FIELDS)


def init_redis_storage():
    # first, remove existing key to remove stale clients
    redis_client.delete(CLIENT_LIST_KEY)
    # add the service as a member of services set
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


def get_all_connections():
    all_conns = {}
    for rt_server_key in get_rt_service_list():
        data = redis_client.hgetall(rt_server_key)
        logger.info('Retrieved client connections. service_id=%s, data=%s', rt_server_key, data)
        if data:
            all_conns.update(data)
    return all_conns


def get_client_list():
    for data in redis_client.hgetall(CLIENT_LIST_KEY).items():
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
    data = redis_client.hget(CLIENT_LIST_KEY, sid)
    if data:
        data = data.decode('utf-8')
        result = _restore_client_data(data)
        if result:
            logger.debug('Got client for sid=%s, data=%s', sid, data)
            return result


def is_client(sid):
    return redis_client.hexists(CLIENT_LIST_KEY, str(sid))


def remove_client(sid):
    remove_clients(sid)


def remove_clients(*sids):
    '''
    Handle a list of sids to delete them from both the database and cache.
    :param sids:
    :return:
    '''
    if not sids:
        return

    sids = set((str(sid) for sid in sids))
    logger.info('Removing clients for sids: %s', sids)
    redis_client.hdel(CLIENT_LIST_KEY, *sids)
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


def remove_rt_service(service_key):
    '''
    Removes service key, and connection list for that key
    :return:
    '''
    redis_client.srem(REALTIME_SERVICES_KEY, service_key)
    redis_client.delete(service_key)


def remove_all_rt_services():
    '''
    Removes all service keys, and connection list for those keys. We
    leave the
    :return:
    '''
    rt_services = redis_client.srem(REALTIME_SERVICES_KEY)
    for rt_svc in rt_services:
        remove_rt_service(rt_svc)


def shutdown_cleanup():
    remove_rt_service(CLIENT_LIST_KEY)


# shutdown hook to clean up service keys on service exit
atexit.register(shutdown_cleanup)

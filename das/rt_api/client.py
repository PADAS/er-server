import logging
import collections
import redis
import datetime
import pytz
import socket
import signal

from django.contrib.gis.geos import Polygon, MultiPolygon
from psycopg2.extras import DateTimeTZRange

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


SERVICE_ID = socket.gethostbyname(socket.gethostname()) or str(get_ip_address())
CLIENT_LIST_KEY = 'rt_api.{}'.format(SERVICE_ID)
EXPIRED_CLIENT_TRACES_LIST = 'rt_api.expired_traces'
REALTIME_SERVICES_KEY = 'rt_api.services'
TRACE_TTL = 60

FIELDS = ['username', 'sid', 'bbox']
ClientData = collections.namedtuple('ClientData', FIELDS)

# bbox, where bbox is the (west, south, east, north) lon,lat pairs.
BBOX_FIELDS = ['west', 'south', 'east', 'north']
Bbox = collections.namedtuple('Bbox', BBOX_FIELDS)

DEFAULT_SESSION_TIMESTAMP = 'rt_api.default_session_timestamp'
SESSION_TIMESTAMP_PER_SUBJECT = 'rt_api.sessiontime_per_subject'



def init_redis_storage():
    logger.info("Initializing redis storage")
    # first, remove existing key to remove stale clients
    redis_client.delete(CLIENT_LIST_KEY)

    redis_client.delete(DEFAULT_SESSION_TIMESTAMP)
    redis_client.delete(SESSION_TIMESTAMP_PER_SUBJECT)

    # add the service as a member of services set
    redis_client.sadd(REALTIME_SERVICES_KEY, CLIENT_LIST_KEY)


def now(tz=pytz.utc):
    return tz.localize(datetime.datetime.utcnow())


def update_client(sid, bbox=None, event_filter=None, patrol_filter=None):
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

        if patrol_filter:
            update_values['patrol_filter'] = patrol_filter

        if update_values:
            from observations.models import SocketClient
            update_values['username'] = client_data.username
            socket_client, created = SocketClient.objects.update_or_create(
                id=sid, defaults=update_values)


def create_update_user_session(sid):
    from observations.models import UserSession
    socket_client, created = UserSession.objects.update_or_create(id=sid)
    if created:
        socket_client.time_range = DateTimeTZRange(lower=datetime.datetime.now(tz=pytz.utc))
        socket_client.save()


def get_all_connections():
    all_conns = redis_client.hgetall(CLIENT_LIST_KEY)
    return all_conns


def get_all_connections_list():
    all_conns = {}
    for list_key in get_rt_service_list():
        conn = redis_client.hgetall(list_key)
        all_conns.update(conn)
    return all_conns


def get_session_count():
    return redis_client.hlen(CLIENT_LIST_KEY)


def get_client_list():
    for sid, client_data in redis_client.hgetall(CLIENT_LIST_KEY).items():
        client_data = _restore_client_data(client_data.decode('utf-8'))
        if client_data:
            yield client_data


def get_expired_traces_client_list():
    for sid in redis_client.hgetall(EXPIRED_CLIENT_TRACES_LIST).keys():
        yield sid.decode('utf8')


def add_client(sid, data):
    sid = str(sid)
    logger.info(f'Adding socket client. {sid}')
    logger.info(f'Adding client to session list. {CLIENT_LIST_KEY} {sid}')
    hset_result = redis_client.hset(
        CLIENT_LIST_KEY, sid, json.dumps(data))


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


def info(param):
    return redis_client.info(param)


def is_client(sid):
    return redis_client.hexists(CLIENT_LIST_KEY, str(sid))


def list_len(key):
    return redis_client.llen(key)


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
    count = redis_client.hdel(CLIENT_LIST_KEY, *sids)
    logger.info(
        f'Removed {count} clients (of {len(sids)} listed) from {CLIENT_LIST_KEY}')
    count = redis_client.hdel(EXPIRED_CLIENT_TRACES_LIST, *sids)
    logger.info(
        f'Removed {count} clients (of {len(sids)} listed) from {EXPIRED_CLIENT_TRACES_LIST}')

    count = redis_client.hdel(DEFAULT_SESSION_TIMESTAMP, *sids)
    logger.info(f"Removed {count} timestamps of {len(sids)} clients")

    count = redis_client.hdel(SESSION_TIMESTAMP_PER_SUBJECT, *sids)
    logger.info(f"Removed {count} timestamps of {len(sids)} clients")

    logger.info('Deleteing mid keys for sids %s.', sids)
    redis_client.delete(*[f'mid-{sid}' for sid in sids])

    from observations.models import SocketClient

    try:
        SocketClient.objects.filter(id__in=sids).delete()
    except ValueError:
        logger.exception('Failed to remove SocketClients for sids: %s', sids)


def update_user_session(sid):
    from observations.models import UserSession
    try:
        socket_client = UserSession.objects.get(id=sid)
    except UserSession.DoesNotExist:
        logger.info(f"sid {sid} not found in UserSession")
    else:
        socket_client.time_range = DateTimeTZRange(upper=datetime.datetime.now(pytz.utc),
                                                   lower=socket_client.time_range.lower)
        socket_client.save()


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
    rt_services = get_rt_service_list()
    for rt_svc in rt_services:
        remove_rt_service(rt_svc)


def trace_expiration_handler(msg):
    logger.info('TRACE Expiration', extra=msg)
    ch = str(msg['channel'])
    # ch = __keyspace@2__:trace-sid-timestamp
    trace_id = ch.split(":")[-1]
    if trace_id.startswith("trace"):
        sid = trace_id.split("-")[-2]
        hset_result = redis_client.hset(EXPIRED_CLIENT_TRACES_LIST, sid, msg)
        logger.info('hset_result = %s', hset_result)


def stop_trace_consumer():
    logger.warning('Trace consumer has not been started.')


def start_trace_consumer():

    logger.info('Starting trace consumer.')
    trace_pubsub = redis_client.pubsub()
    trace_pubsub.psubscribe(
        **{'__keyspace@2__:trace*': trace_expiration_handler})
    trace_consumer = trace_pubsub.run_in_thread(sleep_time=0.001)

    global stop_trace_consumer
    def stop_trace_consumer(): return (logger.info(
        'Stopping trace consumer.'), trace_consumer.stop())


def shutdown_cleanup(*args):
    logger.info('Shutdown cleanup for realtime client list: %s', CLIENT_LIST_KEY)
    remove_rt_service(CLIENT_LIST_KEY)
    signal.signal(signal.SIGINT, shutdown_cleanup)
    signal.signal(signal.SIGTERM, shutdown_cleanup)


def push_trace(trace_id, data):
    logger.info('TRACE', extra={'action': 'push', 'trace_id': trace_id})
    redis_client.setex(trace_id, data, TRACE_TTL)


def pop_trace(trace_id):
    logger.info('TRACE', extra={'action': 'pop', 'trace_id': trace_id})
    redis_client.delete(trace_id)


def message_index(sid, message_type):
    return redis_client.hincrby(f'mid-{sid}', message_type, 1)


def save_session_timestamp(sid, subject_id=None, timestamp=None):
    timestamp = timestamp or datetime.datetime.now(tz=pytz.utc)
    if subject_id:
        redis_client.hset(SESSION_TIMESTAMP_PER_SUBJECT, sid, json.dumps({subject_id: timestamp}))
    else:
        redis_client.hset(DEFAULT_SESSION_TIMESTAMP, sid, timestamp)


def retrieve_default_session_ts():
    hashed_table = {}
    saved_session_ts = redis_client.hgetall(DEFAULT_SESSION_TIMESTAMP)
    for k, v in saved_session_ts.items():
        hashed_table[k.decode()] = v.decode()
    return hashed_table


def retrieve_session_ts_subjects():
    hashed_table = {}
    saved_session_ts = redis_client.hgetall(SESSION_TIMESTAMP_PER_SUBJECT)
    for k, v in saved_session_ts.items():
        hashed_table[k.decode()] = json.loads(v.decode())
    return hashed_table

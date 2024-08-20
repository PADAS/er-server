import datetime
import logging
import signal
import socket
import uuid
from dataclasses import dataclass, field
from typing import Optional

import pytz
import redis
from dataclasses_json import config, dataclass_json
from django_multitenant.utils import get_current_tenant
from psycopg2.extras import DateTimeTZRange

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Polygon

from accounts.utils import get_profile_user
from observations.models import SocketClient, UserSession
from utils import json
from utils.tenant.managers import TenantContextManager

logger = logging.getLogger(__name__)
redis_client = redis.from_url(settings.REALTIME_BROKER_URL)


EXPIRED_CLIENT_TRACES_LIST = "rt_api.expired_traces"
REALTIME_SERVICES_KEY = "rt_api.services"
TRACE_TTL = 60
CLIENT_REALTIME_SERVICES_TTL = 3600  # 1 hour


@dataclass_json
@dataclass(frozen=True)
class Bbox:
    """Bbox, where bbox is the (west, south, east, north) lon,lat pairs."""

    west: float = field(metadata=config(field_name="west"))
    south: float = field(metadata=config(field_name="south"))
    east: float = field(metadata=config(field_name="east"))
    north: float = field(metadata=config(field_name="north"))


@dataclass_json
@dataclass(frozen=True)
class ClientData:
    username: str = field(metadata=config(field_name="username"))
    sid: str = field(metadata=config(field_name="sid"))
    bbox: Optional[Bbox] = field(metadata=config(field_name="bbox"))
    tenant_id: uuid.UUID = field(metadata=config(field_name="tenantId"))
    domain: str = field(metadata=config(field_name="domain"))
    user_id: Optional[uuid.UUID] = field(default=None, metadata=config(field_name="userId"))
    profile_id: Optional[uuid.UUID] = field(default=None, metadata=config(field_name="profileId"))


SID_SUBJECTS_TIMESTAMPS_KEY = "sid-subject-timestamps-{}"
SID_SESSION_TIMESTAMP_KEY = "sid-session-timestamp-{}"


def get_client_list_key() -> str:
    socket_instance = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    socket_instance.connect(("8.8.8.8", 80))
    ip_address = str(socket_instance.getsockname()[0])
    socket_name = socket.gethostname()
    service_id = socket.gethostbyname(socket_name) or ip_address
    return "rt_api.{}".format(service_id)


def init_redis_storage():
    logger.info("Initializing redis storage")
    # first, remove existing key to remove stale clients
    redis_client.delete(get_client_list_key())

    [redis_client.delete(key) for key in redis_client.scan_iter(SID_SESSION_TIMESTAMP_KEY.format("*"))]
    [redis_client.delete(key) for key in redis_client.scan_iter(SID_SUBJECTS_TIMESTAMPS_KEY.format("*"))]

    cleanup_socketclient()
    cleanup_usersessions()
    cleanup_rt_service_list()

    # add the service as a member of services set
    redis_client.sadd(REALTIME_SERVICES_KEY, get_client_list_key())


def now(tz=pytz.utc):
    return tz.localize(datetime.datetime.utcnow())


def update_client(sid, bbox=None, event_filter=None, patrol_filter=None, profile_id=None):
    sid = str(sid)
    logger.info("update_client, sid: %s", sid)
    client_data = get_client(sid)

    # Sometimes we get back None from get_client (per messages in
    # realtime-stderr.log)
    if client_data:
        with TenantContextManager(domain=client_data.domain):
            username = client_data.username

            if profile_id:
                profile_user = get_profile_user(client_data.user_id, profile_id)
                username = profile_user.username
            else:
                profile_id = client_data.profile_id

            client_data = ClientData(
                sid=client_data.sid,
                username=username,
                bbox=Bbox(*bbox) if bbox else client_data.bbox,
                tenant_id=client_data.tenant_id,
                domain=client_data.domain,
                user_id=client_data.user_id,
                profile_id=profile_id,
            )
            add_client(sid, client_data)

            update_values = {}
            if bbox:
                bbox_geom = MultiPolygon(Polygon.from_bbox(bbox))
                update_values["bbox"] = bbox_geom
            if event_filter:
                update_values["event_filter"] = event_filter

            if patrol_filter:
                update_values["patrol_filter"] = patrol_filter

            if update_values:
                update_values["username"] = client_data.username
                socket_client, created = SocketClient.objects.update_or_create(
                    sid=sid, das_tenant=get_current_tenant(), defaults=update_values
                )


def create_update_user_session_by_sid(sid):
    defaults = {"time_range": DateTimeTZRange(lower=datetime.datetime.now(tz=pytz.utc))}
    user_session, created = UserSession.objects.update_or_create(
        sid=sid, das_tenant=get_current_tenant(), defaults=defaults
    )


def get_all_connections():
    client_list_key = get_client_list_key()
    all_conns = redis_client.hgetall(client_list_key)
    redis_client.expire(client_list_key, CLIENT_REALTIME_SERVICES_TTL)
    return all_conns


def get_all_connections_list():
    all_conns = {}
    for list_key in get_rt_service_list():
        conn = redis_client.hgetall(list_key)
        all_conns.update(conn)
    return all_conns


def get_all_connections_list_decoded():
    sids_map = {}
    for sid, session_data in get_all_connections_list().items():
        try:
            session_data = json.loads(session_data.decode("utf-8"))
            sid = sid.decode("UTF-8")
            sids_map[sid] = session_data

        except (UnicodeDecodeError, KeyError):
            logger.warning("Failed to parse session_data=%s", session_data)
    return sids_map


def get_session_count():
    return redis_client.hlen(get_client_list_key())


def get_client_list():
    for sid, client_data in redis_client.hgetall(get_client_list_key()).items():
        client_data = _restore_client_data(client_data.decode("utf-8"))
        if client_data:
            yield client_data


def get_expired_traces_client_list():
    for sid in redis_client.hgetall(EXPIRED_CLIENT_TRACES_LIST).keys():
        yield sid.decode("utf8")


def add_client(sid, client: ClientData):
    client_list_key = get_client_list_key()
    sid = str(sid)
    logger.info(f"Adding socket client. {sid}")
    logger.info(f"Adding client to session list. {client_list_key} {sid}", extra={"client_data": client.to_json()})
    redis_client.hset(client_list_key, sid, client.to_json())
    redis_client.expire(client_list_key, CLIENT_REALTIME_SERVICES_TTL)


def _restore_client_data(data):
    try:
        client_data = ClientData.from_json(data)
    except json.JSONDecodeError:
        client_data = None
    if not client_data:
        return None

    return client_data


def get_client(sid):
    sid = str(sid)
    logger.debug("Get client for sid=%s", sid)
    data = redis_client.hget(get_client_list_key(), sid)
    if data:
        data = data.decode("utf-8")
        result = _restore_client_data(data)
        if result:
            logger.debug("Got client for sid=%s, data=%s", sid, data)
            return result


def info(param):
    return redis_client.info(param)


def is_client(sid):
    return redis_client.hexists(get_client_list_key(), str(sid))


def list_len(key):
    return redis_client.llen(key)


def remove_client(sid: str):
    sids = set()
    sids.add(sid)
    remove_clients(sids)


def remove_clients(sids: set):
    """
    Handle a list of sids to delete them from both the database and cache.
    :param sids:
    :return:
    """
    if not sids:
        return
    client_list_key = get_client_list_key()
    logger.info("Removing clients for sids: %s from key %s", sids, client_list_key)
    count = redis_client.hdel(client_list_key, *sids)
    redis_client.expire(client_list_key, CLIENT_REALTIME_SERVICES_TTL)
    logger.info("Removed %s clients (of %s listed) from %s", count, len(sids), client_list_key)

    logger.info("Removing clients for sids: %s from key %s", sids, EXPIRED_CLIENT_TRACES_LIST)
    count = redis_client.hdel(EXPIRED_CLIENT_TRACES_LIST, *sids)
    logger.info(
        "Removed %s clients (of %s listed) from %s",
        count,
        len(sids),
        EXPIRED_CLIENT_TRACES_LIST,
    )

    logger.info("Deleting mid keys for sids %s.", sids)
    redis_client.delete(*[f"mid-{sid}" for sid in sids])

    logger.info("Deleting session timestamp keys for sids %s.", sids)
    redis_client.delete(*[SID_SESSION_TIMESTAMP_KEY.format(sid) for sid in sids])
    redis_client.delete(*[SID_SUBJECTS_TIMESTAMPS_KEY.format(sid) for sid in sids])

    sockets_sessions = SocketClient.objects.filter(sid__in=sids)
    user_sessions = UserSession.objects.filter(sid__in=sids)

    if sockets_sessions.exists():
        logger.debug("SIDs on SocketClient, deleting", extra={"sids": sids})
        sockets_sessions.delete()
    if user_sessions.exists():
        logger.debug("SIDs on UserSession, deleting", extra={"sids": sids})
        user_sessions.delete()


def cleanup_usersessions():
    older_than_one_week = datetime.datetime.now(tz=pytz.utc) - datetime.timedelta(days=7)
    UserSession.objects.filter(time_range__startswith__lte=older_than_one_week).delete()


def cleanup_socketclient():
    live_sids = get_all_connections_list_decoded()
    for socket_client in SocketClient.objects.values("sid", "username"):
        sid = socket_client["sid"]
        if sid not in live_sids:
            remove_client(str(sid))


def update_user_session_by_sid(sid):
    try:
        user_session = UserSession.objects.get(sid=sid)
    except UserSession.DoesNotExist:
        logger.warning(f"sid {sid} not found in UserSession")
    else:
        if not user_session.time_range:
            logger.warning(f"UserSession missing time_range: {user_session}")
            user_session.time_range = DateTimeTZRange(lower=datetime.datetime.now(tz=pytz.utc))
        else:
            user_session.time_range = DateTimeTZRange(
                upper=datetime.datetime.now(pytz.utc), lower=user_session.time_range.lower
            )
        user_session.save()


def get_rt_service_list():
    """
    :return: List of realtime services that have registered with redis.
    """
    services = redis_client.smembers(REALTIME_SERVICES_KEY)
    return services


def cleanup_rt_service_list():
    """walk the list of servers mentioned in the REALTIME_SERVICES_KEY
    and remove any servers that don't have client keys existing
    """
    registered_services = get_rt_service_list()
    current_alive_service = get_client_list_key()
    service_to_avoid = bytes(current_alive_service, "utf-8")
    registered_services.discard(service_to_avoid)
    if not registered_services:
        logger.info("empty services list to cleanup, doing nothing.")
        return
    for service in registered_services:
        service_key = service.decode("utf-8")
        if not redis_client.exists(service_key):
            logger.warning("service is abandoned: %s. Remove it from REALTIME_SERVICES_KEY", service_key)
            remove_rt_service(service_key=service_key)


def remove_rt_service(service_key):
    """
    Removes service key, and connection list for that key
    :return:
    """
    redis_client.srem(REALTIME_SERVICES_KEY, service_key)
    redis_client.delete(service_key)


def remove_invalid_rt_service_key() -> None:
    """
    Removes invalid rt services from `REALTIME_SERVICES_KEY`
    This removed all of the services in the list except for the current server
    """
    registered_services = get_rt_service_list()
    logger.warning("registered services", extra={"services": registered_services})
    current_alive_service = get_client_list_key()
    logger.warning("current rt api service address: %s", current_alive_service)
    service_to_avoid = bytes(current_alive_service, "utf-8")
    registered_services.discard(service_to_avoid)
    if not registered_services:
        logger.warning("empty services list to remove, doing nothing.")
        return
    for service in registered_services:
        logger.warning("service: %s. send to remove", service.decode("utf-8"))
        remove_rt_service(service_key=service.decode("utf-8"))


def remove_all_rt_services():
    """
    Removes all service keys, and connection list for those keys. We
    leave the
    :return:
    """
    rt_services = get_rt_service_list()
    for rt_svc in rt_services:
        remove_rt_service(rt_svc)


def trace_expiration_handler(msg):
    logger.info("TRACE Expiration", extra=msg)
    ch = str(msg["channel"])
    # ch = __keyspace@2__:trace-sid-timestamp
    trace_id = ch.split(":")[-1]
    if trace_id.startswith("trace"):
        sid = trace_id.split("-")[-2]
        hset_result = redis_client.hset(EXPIRED_CLIENT_TRACES_LIST, sid, msg)
        logger.info("hset_result = %s", hset_result)


def stop_trace_consumer():
    logger.warning("Trace consumer has not been started.")


def start_trace_consumer():
    logger.info("Starting trace consumer.")
    trace_pubsub = redis_client.pubsub()
    trace_pubsub.psubscribe(**{"__keyspace@2__:trace*": trace_expiration_handler})
    trace_consumer = trace_pubsub.run_in_thread(sleep_time=0.001)

    global stop_trace_consumer

    def stop_trace_consumer():
        return (logger.info("Stopping trace consumer."), trace_consumer.stop())


def shutdown_cleanup(*args):
    logger.info("Shutdown cleanup for realtime client list: %s", get_client_list_key())
    remove_rt_service(get_client_list_key())
    signal.signal(signal.SIGINT, shutdown_cleanup)
    signal.signal(signal.SIGTERM, shutdown_cleanup)


def push_trace(trace_id, data):
    logger.info("TRACE", extra={"action": "push", "trace_id": trace_id})
    redis_client.setex(trace_id, TRACE_TTL, json.dumps(data))


def pop_trace(trace_id):
    logger.info("TRACE", extra={"action": "pop", "trace_id": trace_id})
    redis_client.delete(trace_id)


def message_index(sid, message_type):
    return redis_client.hincrby(f"mid-{sid}", message_type, 1)


def save_session_timestamp(sid, subject_id=None):
    timestamp = datetime.datetime.now(tz=pytz.utc).isoformat()

    if subject_id:
        redis_client.hset(SID_SUBJECTS_TIMESTAMPS_KEY.format(sid), subject_id, timestamp)

    # Always set the session's default timestamp.
    redis_client.set(SID_SESSION_TIMESTAMP_KEY.format(sid), timestamp)


def get_sid_subject_timestamp(sid, subject_id):
    """retrieve session timestamp"""
    ts = redis_client.hget(SID_SUBJECTS_TIMESTAMPS_KEY.format(sid), subject_id)
    sid_ts = redis_client.get(SID_SESSION_TIMESTAMP_KEY.format(sid))
    ts = ts or sid_ts
    return ts.decode() if ts else datetime.datetime.now(tz=pytz.utc).isoformat()

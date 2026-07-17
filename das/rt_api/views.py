import logging
import time
import uuid

import eventlet

from django.conf import settings
from django.db import close_old_connections
from django.shortcuts import render
from django.views.generic import View
from rest_framework.exceptions import AuthenticationFailed

import rt_api.pubsub_listener
import utils.json
from rt_api import client
from rt_api.rest_api_interface.dummy_request import (
    DummyRequest,
    wrap_dummy_request_with_drf_request,
)
from rt_api.server import DasSocketIOServer
from utils import stats
from utils.tenant import get_tenant_settings
from utils.tenant.cors import get_tenant_aware_cors_allowed_origins
from utils.tenant.managers import TenantContextManager
from utils.tenant.providers import get_tenant_data_by_host

from .managers import DASKombuManager

logger = logging.getLogger("rt_api")

RT_NAMESPACE = "/das"
LOGIN_NAMESPACE = "/"

GLOBAL_SIO = None


def create_rt_socketio():
    client.init_redis_storage()
    client.start_trace_consumer()

    global GLOBAL_SIO
    if GLOBAL_SIO is None:
        connection_options = dict(transport_options=settings.REALTIME_BROKER_OPTIONS)
        client_mgr = DASKombuManager(url=settings.REALTIME_BROKER_URL, connection_options=connection_options)
        server_options = dict(async_mode=settings.ASYNC_MODE)
        server_options["cors_credentials"] = getattr(settings, "CORS_ALLOW_CREDENTIALS", False)

        if getattr(settings, "CORS_ORIGIN_ALLOW_ALL", False):
            server_options["cors_allowed_origins"] = "*"
        else:
            server_options["cors_allowed_origins"] = get_tenant_aware_cors_allowed_origins()

        socketio_logger = logging.getLogger("rt_api.socketio")
        sio = DasSocketIOServer(
            client_manager=client_mgr,
            json=utils.json,
            logger=socketio_logger,
            engineio_logger=socketio_logger,
            async_handlers=False,
            **server_options,
        )

        realtime_services = create_realtime_handler(sio)
        rt_api.pubsub_listener.start(realtime_services)
        GLOBAL_SIO = sio

    close_old_connections()

    return GLOBAL_SIO


def validate_event_filter(ef):
    if not isinstance(ef.get("text", ""), (str, bytes)):
        raise ValueError("Event filter is invalid. value=%s", str(ef))
    return ef


def receipt_callback(trace_id, *args, **kwargs):
    client.pop_trace(trace_id)


AUTH_CHECK_SLEEP_TIME = getattr(settings, "REALTIME_AUTH_TIMEOUT_SECONDS", 1.0)


def confirm_authorzation(sid, sios):
    extra = dict(sid=sid)
    logger.debug("Confirming auth for new socket connection (waiting %s seconds).", AUTH_CHECK_SLEEP_TIME, extra=extra)
    eventlet.sleep(AUTH_CHECK_SLEEP_TIME)
    if not client.is_client(sid):
        logger.debug("Disconnecting unauthenticated socket connection %s", sid, extra=extra)
        sios.disconnect(sid)
    else:
        logger.debug("New socket connection is authenticated. sid=%s", sid, extra=extra)


def connect_ack(sid, sios):
    logger.debug("Acknowledge connection for sid: %s", sid)
    eventlet.sleep(1.0)
    sios.emit(
        "connect_ack",
        {"type": "connect_ack", "message": "Connect acknowledgment."},
        room=str(sid),
        namespace=RT_NAMESPACE,
    )


CLIENT_CLEANUP_INTERVAL = 30  # seconds


def get_sid_list(sios):
    return [sios.manager.sid_from_eio_sid(eio_sid, RT_NAMESPACE) for eio_sid in list(sios.eio.sockets.keys())]


def cleanup_disconnected_clients(sios):
    try:
        sid_list = get_sid_list(sios)
        if sid_list:
            client_list = set(client.get_client_list())

            stats.update_gauge("rt.clientcount", len(client_list), sample_rate=0.5)
            remove_these_clients = set([c for c in client_list if c.sid not in sid_list])

            expired_clients = [
                client for sid in client.get_expired_traces_client_list() for client in client_list if client.sid == sid
            ]

            disconnect_these_sids = [
                key for sid in client.get_expired_traces_client_list() for key in sid_list if key == sid
            ]

            remove_these_clients = remove_these_clients.union(expired_clients)

            logger.info(
                "inside cleanup disconnected clients, available sockets are: %s",
                str(sid_list),
            )
            if len(remove_these_clients) > 0:
                logger.info("Clients to cleanup and disconnect: %s", len(remove_these_clients))

                remove_sids = set([str(dropping_client.sid) for dropping_client in remove_these_clients])
                client.remove_clients(remove_sids)

                for sid in disconnect_these_sids:
                    sios.disconnect(sid)

            else:
                logger.info("No sockets to clean up. %d Existing sockets connected", len(sid_list))

    finally:
        eventlet.spawn_after(CLIENT_CLEANUP_INTERVAL, cleanup_disconnected_clients, sios)


def create_realtime_handler(sios):
    class RealtimeServices:
        supported_message_types = [
            "new_event",
            "update_event",
            "delete_event",
            "count_event",
            "service_status",
            "subject_status",
            "new_patrol",
            "update_patrol",
            "delete_patrol",
            "subject_track_merge",
            "radio_message",
            "delete_message",
            "new_announcement",
            "new_subject",
            "delete_subject",
        ]

        do_not_trace_these_types = [
            "service_status",
        ]

        @sios.on("connect", namespace=RT_NAMESPACE)
        def on_connect(sid, environ, *args):
            domain = RealtimeServices.get_tenant_domain_from_host(RealtimeServices.get_host_from_environ(environ))
            logger.info("on_connect: socket connecting for sid '%s' under domain '%s'", sid, domain)
            with TenantContextManager(domain):
                # Drop the user if they don't authenticate immediately
                environ["authed"] = False
                client.add_client(
                    sid,
                    client.ClientData(
                        username="",
                        sid=sid,
                        bbox=None,
                        tenant_id=get_tenant_settings().id,
                        domain=get_tenant_settings().domain,
                        user_id=None,
                        profile_id=None,
                    ),
                )

                logger.info("on_connect", extra={"sid": str(sid)})
                logger.debug("on_connect", extra={"sid": str(sid), "environ": repr(environ)})

                # Send a connect acknowledgment (helpful for troubleshooting).
                eventlet.spawn(connect_ack, sid, sios)

                # Make sure the connection authenticates immediately
                eventlet.spawn(confirm_authorzation, sid, sios)

        @sios.on("disconnect", namespace=RT_NAMESPACE)
        def on_disconnect(sid, *args):
            sid_list = get_sid_list(sios)
            extra = dict(sid=sid)
            logger.info("inside on_disconnect, available sockets at sios.eio.sockets are: %s", str(sid_list))
            logger.info("Client disconnect %s", sid, extra=extra)
            client.remove_client(sid)
            client.update_user_session_by_sid(sid)

        @sios.on("authorization", namespace=RT_NAMESPACE)
        def on_authenticate(sid, data):
            logger.info("on_authenticate: socket authenticating for sid '%s'", sid)
            try:
                # validate the data
                for param in ("type", "authorization", "id"):
                    if param not in data:
                        sios.emit(
                            "resp_authorization",
                            {
                                "resp_id": data["id"],
                                "status": {"code": 400, "message": 'Required fields: "type", "authorization", "id"'},
                            },
                            room=str(sid),
                            namespace=RT_NAMESPACE,
                        )
                        logger.debug("Disconnecting sid: %s...", sid)
                        sios.disconnect(sid)
                        client.remove_client

                # To authenticate the token, we need to create a fake http
                # request for oauth to authenticate
                client_data = client.get_client(sid)
                with TenantContextManager(domain=client_data.domain):
                    dummy_request = DummyRequest(headers={"HTTP_AUTHORIZATION": data["authorization"]})
                    # Use DRF Request which automatically handles authentication
                    drf_request = wrap_dummy_request_with_drf_request(dummy_request)
                    try:
                        # Accessing .user triggers DRF's authentication workflow
                        user = drf_request.user if drf_request.user.is_authenticated else None
                        logger.debug("Request successfull auth class: %s", drf_request.successful_authenticator)
                    except AuthenticationFailed as exc:
                        logger.info("Socket auth rejected for sid=%s: %s", sid, exc)
                        user = None
                    except Exception:
                        logger.exception("Error accessing user from DRF request")
                        user = None
                    # The token checks out
                    if user is not None:
                        extra = dict(sid=sid, user_id=user.id)
                        logger.info("Socket sid=%s, user=%s authenticated successfully", sid, user, extra=extra)

                        # Put the user into redis
                        client_data = client.ClientData(
                            sid=sid,
                            username=user.username,
                            bbox=None,
                            tenant_id=get_tenant_settings().id,
                            domain=get_tenant_settings().domain,
                            user_id=user.id,
                            profile_id=None,
                        )
                        client.add_client(sid, client_data)
                        client.save_session_timestamp(sid)

                        # Put the connection into the correct rooms
                        sios.manager.enter_room(sid, RT_NAMESPACE, "all_clients")
                        sios.manager.enter_room(sid, RT_NAMESPACE, sid)

                        # tell the user that they've been authenticated
                        sios.emit(
                            "resp_authorization",
                            {
                                "type": "resp_authorization",
                                "resp_id": data["id"],
                                "status": {"code": 200, "message": "OK"},
                            },
                            room=str(sid),
                            namespace=RT_NAMESPACE,
                        )

                        client.create_update_user_session_by_sid(sid)

                    else:
                        extra = dict(sid=sid)
                        logger.warning("User is None, so disconnecting. sid=%s, data=%s", sid, data, extra=extra)
                        status = {"code": 401, "message": "Invalid credentials"}
                        # When the MFA gate rejected the token for step-up, it recorded an RFC 9470
                        # challenge on the request. Surface it so socket clients can distinguish a
                        # step-up 401 from an ordinary invalid-credentials 401 and drive graceful re-MFA.
                        step_up_challenge = getattr(drf_request, "_auth0_step_up_challenge", None)
                        if step_up_challenge:
                            status["www_authenticate"] = step_up_challenge
                        sios.emit(
                            "resp_authorization",
                            {
                                "type": "resp_authorization",
                                "resp_id": data["id"],
                                "status": status,
                            },
                            room=str(sid),
                            namespace=RT_NAMESPACE,
                        )

            except Exception as exc:
                sios.emit(
                    "resp_authorization",
                    {
                        "type": "resp_authorization",
                        "resp_id": data["id"],
                        "status": {"code": 401, "message": "Authentication error"},
                    },
                    room=str(sid),
                    namespace=RT_NAMESPACE,
                )
                sios.disconnect(sid)
                logger.exception("Disconnecting session", extra={"data": data, "exc": exc})

        @sios.on("bbox", namespace=RT_NAMESPACE)
        def on_bbox(sid, data):
            extra = dict(sid=sid, data=data)
            bbox = data["data"]
            if bbox:
                bbox = bbox.split(",")
                bbox = [float(v) for v in bbox]
                if len(bbox) != 4:
                    raise ValueError("invalid bbox param")

            client.update_client(sid, bbox=bbox)
            sios.emit(
                "bbox_resp",
                {"type": "bbox_resp", "message": "bbox saved.", "bbox": bbox},
                room=str(sid),
                namespace=RT_NAMESPACE,
            )

        @sios.on("event_filter", namespace=RT_NAMESPACE)
        def on_event_filter(sid, event_filter):
            """
            This is expecting a dict containing custom filter attributes.

            :param event_filter: Event filter (Ex. {'text': 'arrest'}) can also be an empty dict.
            :return: None
            """
            try:
                event_filter = validate_event_filter(event_filter)
                client.update_client(sid, event_filter=event_filter)

                extra = dict(sid=sid, event_filter=event_filter)
                logger.info("on_event_filter", extra=extra)

                sios.emit(
                    "event_filter_response",
                    {
                        "message": "Event filter has been saved.",
                        "filter": event_filter,
                    },
                    room=str(sid),
                    namespace=RT_NAMESPACE,
                )
            except ValueError as ve:
                sios.emit(
                    "event_filter_response",
                    {
                        "message": "Failed to set event_filter.",
                        "error": str(ve),
                    },
                    room=str(sid),
                    namespace=RT_NAMESPACE,
                )

        @sios.on("patrol_filter", namespace=RT_NAMESPACE)
        def on_patrol_filter(sid, patrol_filter):
            """
            This is expecting a dict containing custom filter attributes.

            :param patrol_filter:
            :return:
            """
            try:
                client.update_client(sid, patrol_filter=patrol_filter)
                extra = dict(sid=sid, patrol_filter=patrol_filter)
                logger.info("on_patrol_filter", extra=extra)

                sios.emit(
                    "patrol_filter_response",
                    {
                        "message": "Patrol filter has been saved.",
                        "filter": patrol_filter,
                    },
                    room=str(sid),
                    namespace=RT_NAMESPACE,
                )
            except ValueError as ve:
                sios.emit(
                    "patrol_filter_response",
                    {
                        "message": "Failed to set patrol_filter.",
                        "error": str(ve),
                    },
                    room=str(sid),
                    namespace=RT_NAMESPACE,
                )

        @sios.on("profile", namespace=RT_NAMESPACE)
        def on_profile_change(sid, profile_message):
            PROFILE_RESP = "profile_resp"
            try:
                profile_id = uuid.UUID(profile_message["profile_id"])

                client.update_client(sid, profile_id=profile_id)
                extra = dict(sid=sid, profile_message=profile_message)
                logger.info("on_profile_change", extra=extra)

                sios.emit(
                    PROFILE_RESP,
                    {"message": "User Profile has been changed.", "type": PROFILE_RESP, "profile_id": str(profile_id)},
                    room=str(sid),
                    namespace=RT_NAMESPACE,
                )
            except ValueError as ve:
                sios.emit(
                    PROFILE_RESP,
                    {
                        "message": "Failed to set user profile.",
                        "type": PROFILE_RESP,
                        "error": str(ve),
                    },
                    room=str(sid),
                    namespace=RT_NAMESPACE,
                )

        @sios.on("echo", namespace=RT_NAMESPACE)
        def on_echo(sid, *args):
            sios.emit(
                "echo_resp",
                {"type": "echo_resp", "resp_id": 5, "message": args[0]["data"]},
                room=str(sid),
                namespace=RT_NAMESPACE,
            )

        @staticmethod
        def emit(message_type, data, socketid=None):
            # user is the SID if set
            if not sios.manager.is_connected(socketid, RT_NAMESPACE):
                client.remove_client(socketid)
                # extra = dict(sid=user)
                logger.warning("Tried to send a message to a disconnected client.", extra={"sid": socketid})
                return

            try:
                # Add a message index. The client can use this to identify gaps
                # in message streams.
                data["mid"] = client.message_index(socketid, message_type)

                # Add trace ID to message. It will be sent back in callback.
                if message_type not in RealtimeServices.do_not_trace_these_types and isinstance(data, dict):
                    data["trace_id"] = f"trace-{socketid}-{time.time()}"
                    client.push_trace(data["trace_id"], data)

                if socketid is None:
                    sios.emit(message_type, data, namespace=RT_NAMESPACE, callback=receipt_callback)
                else:
                    # Sample 10% of realtime messages per message-type.
                    stats.increment("rt.emit", tags=["service:realtime", f"name:{message_type}"], sample_rate=0.1)

                    extra = {"socket_id": str(socketid), "namespace": RT_NAMESPACE}
                    logger.debug("Emit message from SocketIO server", extra=extra)
                    sios.emit(message_type, data, room=str(socketid), namespace=RT_NAMESPACE, callback=receipt_callback)

            except Exception:
                if socketid:
                    client.remove_client(socketid)
                    logger.exception(f"Error emitting event over socket {socketid}")
                else:
                    logger.exception(f"Error emitting event over socket")

        @staticmethod
        def send_realtime_message(message_data):
            if message_data["type"] in RealtimeServices.supported_message_types:
                extra = dict(sid=message_data["sid"], type=message_data["type"])
                logger.info("Sending realtime messsage to %s", message_data["sid"], extra=extra)
                RealtimeServices.emit(
                    message_type=message_data["type"], data=message_data["data"], socketid=message_data["sid"]
                )
            else:
                logger.error("Realtime server received invalid message type: %s", message_data["type"])

        @staticmethod
        def get_host_from_environ(environ):
            if settings.USE_X_FORWARDED_HOST and ("HTTP_X_FORWARDED_HOST" in environ):
                host = environ["HTTP_X_FORWARDED_HOST"]
            elif "HTTP_HOST" in environ:
                host = environ["HTTP_HOST"]
            else:
                host = environ["SERVER_NAME"]
            return host

        @staticmethod
        def get_tenant_domain_from_host(host):
            tenant_data = get_tenant_data_by_host(host.split(":")[0])
            return tenant_data["domain"]

        @staticmethod
        def update_cors_allowed_origins():
            if not getattr(settings, "CORS_ORIGIN_ALLOW_ALL", False):
                logger.info("Updating RT Server CORS_ALLOWED_ORIGINS list")
                cors_allowed_origins = get_tenant_aware_cors_allowed_origins()
                sios.set_cors_allowed_origins(cors_allowed_origins)
                logger.debug("Updated RT Server CORS_ALLOWED_ORIGINS list", extra={"cors": cors_allowed_origins})

    # Start up recursive calls to clean up disconnected clients.
    eventlet.spawn_after(CLIENT_CLEANUP_INTERVAL, cleanup_disconnected_clients, sios)

    return RealtimeServices


class RTMClient(View):
    template_name = "rtmclient.html"

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {})

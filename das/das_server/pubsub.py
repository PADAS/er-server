"""
message publishing module
"""

from __future__ import annotations

import logging
import re
import signal
import socket
import uuid
from functools import wraps
from importlib import import_module
from threading import Thread
from typing import Callable, ParamSpec, TypeVar

from kombu import Connection, Consumer, Exchange, Queue
from kombu.exceptions import OperationalError
from kombu.utils import nested
from redis.exceptions import ConnectionError

from django.apps import apps
from django.conf import settings

from das_server.pubsub_gcloud_listener import setup_gcloud_pubsub_listener
from das_server.utils import (
    append_domain_to_message,
    wrap_message_processing_with_tenant_context,
)
from utils import stats
from utils.decorator import retry_on_exception
from utils.tenant.decorators import append_tenant_domain

logger = logging.getLogger(__name__)

# Kombu invokes a consumer callback as callback(body, message), but the body type
# varies per routing key (dict for the das.* handlers, str for das.realtime.emit),
# so swallow_callback_exceptions stays generic over the callback it wraps instead
# of pinning a body type that would be wrong for half its call sites.
_CallbackParams = ParamSpec("_CallbackParams")
_CallbackReturn = TypeVar("_CallbackReturn")

PUBLISH_TIMEOUT = 5  # seconds
DAS_PUBSUB_CHANNEL_NAME = "das"
das_exchange = Exchange(DAS_PUBSUB_CHANNEL_NAME, type="topic", durable=True)
_pool = None


def get_pool():
    global _pool
    if not _pool:
        _pool = (
            Connection(settings.PUBSUB_BROKER_URL, transport_options=settings.PUBSUB_BROKER_OPTIONS)
            .ensure_connection(max_retries=5, interval_max=2)
            .Pool(20)
        )
    return _pool


@append_tenant_domain
def publish(message, routing_key="das", **kwargs):
    """Broadcast a message.

    :param message: JSONifyable message to send
    :param routing_key: routing key for the message. defaults to 'das'
        routing key is used in the topic exchange, so must be a list of words
        delimited by dots, up to the limit of 255 characters. Should begin
        with the string 'das'

        Example routing keys:
            das.event.analyzer.error
            das.tracking.data_input

    """

    # noinspection PyBroadException
    try:
        logger.debug("publish received message: {}" "  routing_key: {}".format(message, routing_key))

        stats.increment("publish", tags=[f"routing_key:{routing_key}"], sample_rate=1.0)
        with get_pool().acquire(block=True, timeout=PUBLISH_TIMEOUT) as conn:
            producer = conn.Producer(exchange=das_exchange)
            message = append_domain_to_message(message=message, domain=kwargs.get("domain"))
            producer.publish(message, routing_key=routing_key)

    except Exception:
        logger.exception("Unhandled exception during publish")


def subscribe_without_retry(subscription_list, loop_forever=True):
    """Create a set of subscriptions to messages routed by routing_key

    :param subscription_list: a list of dictionaries with keys
        'routing_key' and 'callback'.

    routing_key is the routing key for the message. defaults to 'das.#'
        routing key is used in the topic exchange, so must be a list of words
        delimited by dots, up to the limit of 255 characters. Should begin
        with the string 'das'

    callback is the function to call on the message.

    This function will block, but can be run in a thread

    Every failure — including a redis ConnectionError — propagates to the
    caller. Use this only from a caller that supervises its own restart,
    backoff and metrics (rt_api.pubsub_listener); otherwise use `subscribe`.
    """

    with Connection(settings.PUBSUB_BROKER_URL, transport_options=settings.PUBSUB_BROKER_OPTIONS) as conn:
        consumers = []

        for subscription in subscription_list:
            consumer = get_consumer(
                conn, subscription["routing_key"], subscription["callback"], name=subscription.get("name", None)
            )
            consumers.append(consumer)

        with nested(*consumers):
            while True:
                try:
                    conn.drain_events(timeout=5)
                except socket.timeout:
                    if not loop_forever:
                        break


# Default entry point: retries a redis ConnectionError forever, in-place. The
# retry is applied here rather than as a decorator on the function above so that
# a caller running its own supervision loop can reach the unwrapped
# implementation by name instead of through `subscribe.__wrapped__`.
subscribe = retry_on_exception(exception_type=ConnectionError, retry_forever=True)(subscribe_without_retry)


def installed_apps_subscriptions(submodule="pubsub_registry", ignore_re="(djgeojson|django)"):
    """
    Automatically import {{ app_name }}.pubsub_registry modules.
    :param submodules: module name(s) within INSTALLED_APPS.
    :param ignore_re: an re to ignore installed apps by pattern.
    :return: a generator of tuples representing subscriptions.
    """

    for app_config in apps.get_app_configs():
        if re.match(ignore_re, app_config.name):
            continue

        logger.debug("registering tasks for app {}".format(app_config.name))
        module_name = "{}.{}".format(app_config.name, submodule)

        try:
            app_submodule = import_module(module_name)
            for subscription in app_submodule.PUBSUB_SUBSCRIPTIONS:
                if len(subscription) == 2:
                    routing_key, callback = subscription
                    name = None
                else:
                    routing_key, callback, name = subscription
                logger.info("registering routing key {} to {}" "".format(routing_key, callback.__name__))
                yield (routing_key, callback, name)

        except AttributeError as e:
            logger.warning(
                "{}.PUBSUB_SUBSCRIPTIONS should be a sequence of"
                " (routing_key, callback) sequences. {}"
                "".format(module_name, e)
            )
        except ImportError:
            logger.debug("No pubsub registrations imported for app {}" "".format(app_config.name))


def get_consumer(connection, routing_key, callback, name=None):
    """returns a kombu.Consumer which routes messages from connection
    with routing_key to callback"""

    if not name:
        name = "das.{0}".format(uuid.uuid4())

    queue = Queue(
        name=name, channel=connection, exchange=das_exchange, routing_key=routing_key, no_ack=True, auto_delete=True
    )
    consumer = Consumer(connection, queues=[queue], callbacks=[callback])
    return consumer


running = True


def stats_decorator(f, routing_key):
    metric_type = "mql"
    tags = [f"route:{routing_key}", f"handler:{f.__name__}"]

    @wraps(f)
    def wrapper(*args, **kwargs):
        stats.increment(metric_type, sample_rate=1.0, tags=tags)
        return f(*args, **kwargs)

    return wrapper


def swallow_callback_exceptions(
    callback: Callable[_CallbackParams, _CallbackReturn],
    routing_key: str,
) -> Callable[_CallbackParams, _CallbackReturn | None]:
    """Wrap a pub/sub callback so a poison message cannot kill the consumer.

    Kombu queues here are declared ``no_ack=True``: by the time the callback
    runs the message has already been removed from the broker, so swallowing the
    error only drops that one (ephemeral) message. Letting the exception escape
    ``conn.drain_events`` instead tears down the whole subscription loop, which
    historically left the durable binding LPUSHing into an unconsumed Redis list
    forever. We log with full traceback and emit a metric so poison messages are
    still visible without taking the listener down.

    Returns a callable with the same ``(body, message)`` signature as ``callback``
    whose return type widens to include ``None`` — the value returned when a
    message is dropped. Kombu ignores callback return values, so no caller has to
    handle the ``None``.
    """

    @wraps(callback)
    def wrapper(*args: _CallbackParams.args, **kwargs: _CallbackParams.kwargs) -> _CallbackReturn | None:
        try:
            return callback(*args, **kwargs)
        except Exception:
            logger.exception(
                "Unhandled exception in pub/sub callback; dropping message. routing_key=%s handler=%s",
                routing_key,
                getattr(callback, "__name__", repr(callback)),
            )
            stats.increment(
                "pubsub_callback_error",
                tags=[f"route:{routing_key}", f"handler:{getattr(callback, '__name__', 'unknown')}"],
            )

    return wrapper


@retry_on_exception(exception_type=ConnectionError, retry_forever=True, delay=3)
@retry_on_exception(exception_type=OperationalError, retry_forever=True, delay=3)
def start_message_queue_listeners():
    logger.debug("begin start_message_queue_listeners")

    def signal_handler(*args):
        logger.warning("SIGINT caught")
        global running
        running = False

    signal.signal(signal.SIGINT, signal_handler)

    with Connection(settings.PUBSUB_BROKER_URL, transport_options=settings.PUBSUB_BROKER_OPTIONS) as conn:
        consumers = []

        for routing_key, callback, name in installed_apps_subscriptions():
            consumer = get_consumer(
                conn,
                routing_key,
                wrap_message_processing_with_tenant_context(stats_decorator(callback, routing_key)),
                name,
            )
            consumers.append(consumer)

        with nested(*consumers):
            logger.debug("running start_message_queue_listeners")
            while running:
                try:
                    conn.drain_events(timeout=2)
                except socket.timeout:
                    pass

    logger.debug("end start_message_queue_listeners")


def start_gcloud_pubsub_listener():
    thread = Thread(target=setup_gcloud_pubsub_listener)
    thread.daemon = True
    thread.start()

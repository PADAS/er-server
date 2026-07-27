from __future__ import annotations

import logging
import time
from threading import Thread

import utils.json as json
from das_server import pubsub
from rt_api import client
from rt_api.pubsub_subscriptions import SUBSCRIPTIONS, queue_name_for
from rt_api.tasks import (
    handle_delete_event,
    handle_delete_message,
    handle_delete_patrol,
    handle_delete_subject,
    handle_new_announcement,
    handle_new_event,
    handle_new_message,
    handle_new_patrol,
    handle_new_subject,
    handle_new_subject_observation,
    handle_subjectstatus_update,
    handle_update_event,
    handle_update_message,
    handle_update_patrol,
)
from utils import stats

logger = logging.getLogger(__name__)

# Seconds to wait before re-subscribing after a listener loop exits or raises.
# Short enough that a transient broker blip recovers quickly, long enough that a
# hard-failing subscription doesn't spin a CPU.
LISTENER_RESTART_DELAY_SECONDS = 5


def start(realtime_server):
    def new_event_handler(data, message):
        logger.debug("new_event_handler. data=%s, message=%s", data, message)
        logger.info("Calling handle_new_event function from pubsub")
        handle_new_event.apply_async(
            args=(data["event_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def update_event_handler(data, message):
        logger.debug("update_event_handler. data=%s, message=%s", data, message)
        handle_update_event.apply_async(
            args=(data["event_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def delete_event_handler(data, message):
        logger.debug("delete_event_handler. data=%s, message=%s", data, message)
        handle_delete_event.apply_async(
            args=(data["event_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def new_observation_handler(data, message):

        if subject_id := data.get("subject_id"):
            handle_new_subject_observation.apply_async(
                args=(subject_id,),
                kwargs={"domain": data.pop("domain", None)},
            )
        elif source_id := data.get("source_id"):
            domain = data.pop("domain", None)
            if not domain:
                logger.warning(
                    "new_observation_handler: dropping source_id=%s — missing/empty domain in pubsub message",
                    source_id,
                )
                return
            client.add_pending_source_observation(domain, source_id)
            logger.debug("Accumulating source_id=%s for domain=%s", source_id, domain)

    def subjectstatus_update_handler(data, message):
        logger.debug("das.subjectstatus.update %s", data)
        if "subject_id" in data:
            handle_subjectstatus_update.apply_async(
                args=(data["subject_id"],),
                kwargs={"domain": data.pop("domain", None)},
            )

    def new_patrol_handler(data, message):
        logger.debug("new_patrol_handler. data=%s, message=%s", data, message)
        handle_new_patrol.apply_async(
            args=(data["patrol_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def update_patrol_handler(data, message):
        logger.debug("update_patrol_handler. data=%s, message=%s", data, message)
        handle_update_patrol.apply_async(
            args=(data["patrol_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def delete_patrol_handler(data, message):
        logger.debug("delete_patrol_handler. data=%s, message=%s", data, message)
        handle_delete_patrol.apply_async(
            args=(data["patrol_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def emit_handler(data, message):
        message_data = json.loads(data)
        if message_data.get("type", "") == "new_event":
            event_id = message_data.get("data", {}).get("event_id", "")
            sid = message_data.get("sid", "")
            logger.info("Pushing event %s to sid %s", event_id, sid)
        realtime_server.send_realtime_message(message_data)

    def new_message_handler(data, message):
        logger.debug("new_message_handler. data=%s, message=%s", data, message)

        handle_new_message.apply_async(
            args=(data["message_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def update_message_handler(data, message):
        logger.debug("update_message_handler. data=%s, message=%s", data, message)
        handle_update_message.apply_async(
            args=(data["message_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def delete_message_handler(data, message):
        logger.debug("delete_message_handler. data=%s, message=%s", data, message)
        handle_delete_message.apply_async(
            args=(data["message_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def new_announcement_handler(data, message):
        logger.debug("new_announcement_handler. data=%s, message=%s", data, message)
        handle_new_announcement.apply_async(
            args=(data["announcement_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def new_subject_handler(data, message):
        logger.debug("new_subject_handler. data=%s, message=%s", data, message)
        handle_new_subject.apply_async(
            args=(data["subject_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def delete_subject_handler(data, message):
        logger.debug("delete_subject_handler. data=%s, message=%s", data, message)
        handle_delete_subject.apply_async(
            args=(data["subject_id"],),
            kwargs={"domain": data.pop("domain", None)},
        )

    def das_tenant_updated_handler(data, message):
        logger.info("das_tenant_updated_handler. data=%s, message=%s", data, message)
        realtime_server.update_cors_allowed_origins()

    # Map the canonical subscription table (routing_key -> callback name) to the
    # local handler closures defined above. Keeping the table in
    # rt_api.pubsub_subscriptions (instead of inline here) lets the monitoring
    # and backstop Celery tasks derive the exact same queue names without
    # importing this module — see pubsub_subscriptions for the rationale.
    callbacks_by_name = {
        "das_tenant_updated_handler": das_tenant_updated_handler,
        "new_observation_handler": new_observation_handler,
        "subjectstatus_update_handler": subjectstatus_update_handler,
        "new_event_handler": new_event_handler,
        "update_event_handler": update_event_handler,
        "delete_event_handler": delete_event_handler,
        "new_patrol_handler": new_patrol_handler,
        "update_patrol_handler": update_patrol_handler,
        "delete_patrol_handler": delete_patrol_handler,
        "emit_handler": emit_handler,
        "new_message_handler": new_message_handler,
        "update_message_handler": update_message_handler,
        "delete_message_handler": delete_message_handler,
        "new_announcement_handler": new_announcement_handler,
        "new_subject_handler": new_subject_handler,
        "delete_subject_handler": delete_subject_handler,
    }

    def build_subscriptions():
        subscriptions = []
        for subscription in SUBSCRIPTIONS:
            callback = callbacks_by_name[subscription.callback_name]
            # Wrap each callback so a single poison message is logged + metered
            # and dropped (queues are no_ack=True) instead of escaping
            # drain_events and tearing down the whole subscription loop.
            safe_callback = pubsub.swallow_callback_exceptions(callback, subscription.routing_key)
            name = queue_name_for(subscription.callback_name)
            logger.info('Adding subscription for "%s"', name)
            subscriptions.append(
                {
                    "routing_key": subscription.routing_key,
                    "callback": safe_callback,
                    "name": name,
                }
            )
        return subscriptions

    def pubsub_listener(listener_name: str):
        # Supervision loop: subscribe blocks while draining events. If it ever
        # returns (graceful shutdown) or raises (broker error, etc.), we log it,
        # count the churn, wait, and re-subscribe. The thread only exits on
        # interpreter shutdown via SystemExit / KeyboardInterrupt, which are
        # BaseExceptions and intentionally escape the `except Exception` below.
        #
        # subscribe_without_retry, not subscribe: the latter is wrapped in
        # retry_on_exception(ConnectionError, retry_forever=True, delay=1), which
        # would retry the most common broker failure inside the call — the
        # restart metric would never increment and the backoff below would never
        # apply. This loop is the single owner of retry/backoff/metrics for every
        # exception type.
        logger.info("Starting pubsub listener %s", listener_name)
        # Built once per thread, not per attempt: the list holds only strings and
        # stateless callables, and subscribe declares its kombu Queue/Consumer
        # objects fresh against a new Connection on every call, so nothing
        # connection-bound is carried into the next attempt. Rebuilding per
        # attempt re-logged one line per routing key, which during a prolonged
        # broker outage meant len(SUBSCRIPTIONS) x 5 threads of log spam every
        # LISTENER_RESTART_DELAY_SECONDS.
        subscriptions = build_subscriptions()
        while True:
            try:
                pubsub.subscribe_without_retry(subscriptions)
                logger.warning("PubSub subscriber %s returned; restarting", listener_name)
                reason = "returned"
            except Exception:
                logger.exception("PubSub subscriber %s raised; restarting", listener_name)
                reason = "exception"

            stats.increment(
                "rt_pubsub_listener_restart",
                tags=[f"listener:{listener_name}", f"reason:{reason}"],
            )
            time.sleep(LISTENER_RESTART_DELAY_SECONDS)

    logger.info("Starting pubsub listener threads.")
    for thread_index in range(5):
        logger.info("Starting pubsub listener thread (%s).", thread_index)
        name = f"pubsub-listener-{thread_index}"
        Thread(target=pubsub_listener, name=name, args=(name,)).start()

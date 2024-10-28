import logging
from threading import Thread

import utils.json as json
from das_server import pubsub
from rt_api.tasks import (
    handle_delete_event,
    handle_delete_message,
    handle_delete_patrol,
    handle_new_announcement,
    handle_new_event,
    handle_new_message,
    handle_new_patrol,
    handle_new_source_observation,
    handle_new_subject_observation,
    handle_subjectstatus_update,
    handle_update_event,
    handle_update_message,
    handle_update_patrol,
)

logger = logging.getLogger(__name__)


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
            handle_new_source_observation.apply_async(
                args=(source_id,),
                kwargs={"domain": data.pop("domain", None)},
            )

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

    def das_tenant_updated_handler(data, message):
        logger.info("das_tenant_updated_handler. data=%s, message=%s", data, message)
        realtime_server.update_cors_allowed_origins()

    def pubsub_listener(listener_name: str):
        logger.info("Starting pubsub listener")
        subscriptions = [
            {"routing_key": "das.tenant.new", "callback": das_tenant_updated_handler},
            {"routing_key": "das.tenant.update", "callback": das_tenant_updated_handler},
            {"routing_key": "das.tracking.source.observations.new", "callback": new_observation_handler},
            {
                "routing_key": "das.subjectstatus.update",
                "callback": subjectstatus_update_handler,
            },
            {"routing_key": "das.event.new", "callback": new_event_handler},
            {"routing_key": "das.event.update", "callback": update_event_handler},
            {"routing_key": "das.event.delete", "callback": delete_event_handler},
            {"routing_key": "das.patrol.new", "callback": new_patrol_handler},
            {"routing_key": "das.patrol.update", "callback": update_patrol_handler},
            {"routing_key": "das.patrol.delete", "callback": delete_patrol_handler},
            {"routing_key": "das.realtime.emit", "callback": emit_handler},
            {
                "routing_key": "das.message.new",
                "callback": new_message_handler,
            },
            {
                "routing_key": "das.message.update",
                "callback": update_message_handler,
            },
            {
                "routing_key": "das.message.delete",
                "callback": delete_message_handler,
            },
            {
                "routing_key": "das.announcement.new",
                "callback": new_announcement_handler,
            },
        ]
        for subscription in subscriptions:
            subscription["name"] = "rt_api.{0}".format(subscription["callback"].__name__)

            logger.info('Adding subscription for "%s"', subscription["name"])
        try:
            pubsub.subscribe(subscriptions)
            logger.warning("PubSub subscriber %s shutting down", listener_name)
        except Exception as error:
            logger.exception("Error subscribing to pubsub, error %s", error)

    logger.info("Starting pubsub listener threads.")
    for thread_index in range(5):
        logger.info("Starting pubsub listener thread (%s).", thread_index)
        name = f"pubsub-listener-{thread_index}"
        Thread(target=pubsub_listener, name=name, args=(name,)).start()

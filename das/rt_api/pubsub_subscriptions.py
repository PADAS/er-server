"""Canonical table of rt_api Kombu pub/sub subscriptions.

This module is intentionally dependency-free: it must be importable from both
the rtserver process (``rt_api.pubsub_listener.start``) and from Celery workers
(``rt_api.tasks.check_redis_queues`` / the queue backstop) without dragging in
the socketio server or ``rt_api.tasks`` — ``pubsub_listener`` imports from
``rt_api.tasks``, so importing ``pubsub_listener`` from a Celery worker would
risk a circular import and needlessly load the realtime server stack.

Each subscription is identified by the *callback name* its handler closure has
in ``pubsub_listener.start``. That function names the durable Kombu queue
``rt_api.<callback_name>`` — it passes ``name=QUEUE_NAME_PREFIX + callback_name``
to ``das_server.pubsub.get_consumer`` (which otherwise just uses whatever
``name`` it is given, falling back to ``das.<uuid>``) — so the queue name for a
subscription is ``QUEUE_NAME_PREFIX + callback_name``. Both the listener (which
maps these names back to local handler closures) and the monitoring/backstop
tasks (which derive the Redis list keys to gauge and trim) read from this single
source of truth so the two can never drift.
"""

from __future__ import annotations

from typing import Final, NamedTuple

# rt_api.pubsub_listener.start names each per-consumer Kombu queue
# "rt_api.<callback_name>" by passing name=QUEUE_NAME_PREFIX + callback_name to
# das_server.pubsub.get_consumer; the Redis list backing that queue uses the
# same key.
QUEUE_NAME_PREFIX: Final = "rt_api."


class PubSubSubscription(NamedTuple):
    routing_key: str
    # The ``__name__`` of the handler closure registered in
    # ``pubsub_listener.start``. Also the suffix of the Kombu queue name.
    callback_name: str


# Order is irrelevant; this is the authoritative set of routing-key -> handler
# pairs that pubsub_listener.start registers. Keep it in sync with the handler
# closures defined there (a unit test asserts the two match).
SUBSCRIPTIONS: Final[tuple[PubSubSubscription, ...]] = (
    PubSubSubscription("das.tenant.new", "das_tenant_updated_handler"),
    PubSubSubscription("das.tenant.update", "das_tenant_updated_handler"),
    PubSubSubscription("das.tracking.source.observations.new", "new_observation_handler"),
    PubSubSubscription("das.subjectstatus.update", "subjectstatus_update_handler"),
    PubSubSubscription("das.event.new", "new_event_handler"),
    PubSubSubscription("das.event.update", "update_event_handler"),
    PubSubSubscription("das.event.delete", "delete_event_handler"),
    PubSubSubscription("das.patrol.new", "new_patrol_handler"),
    PubSubSubscription("das.patrol.update", "update_patrol_handler"),
    PubSubSubscription("das.patrol.delete", "delete_patrol_handler"),
    PubSubSubscription("das.realtime.emit", "emit_handler"),
    PubSubSubscription("das.message.new", "new_message_handler"),
    PubSubSubscription("das.message.update", "update_message_handler"),
    PubSubSubscription("das.message.delete", "delete_message_handler"),
    PubSubSubscription("das.announcement.new", "new_announcement_handler"),
    PubSubSubscription("das.subject.new", "new_subject_handler"),
    PubSubSubscription("das.subject.delete", "delete_subject_handler"),
)


def queue_name_for(callback_name: str) -> str:
    """Return the Kombu/Redis queue list key for a given handler name."""
    return f"{QUEUE_NAME_PREFIX}{callback_name}"


def all_queue_names() -> list[str]:
    """Return the distinct queue list keys for every rt_api subscription.

    Several routing keys (e.g. das.tenant.new / das.tenant.update) share one
    handler and therefore one queue, so the names are de-duplicated.
    """
    return list(dict.fromkeys(queue_name_for(s.callback_name) for s in SUBSCRIPTIONS))

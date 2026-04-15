"""Event rendering and state inference utilities for the alerting system."""

import logging

from activity.models import Event, EventDetails
from activity.permissions import EventCategoryPermissions
from activity.serializers import EventSerializer
from core.utils import NonHttpRequest
from revision.manager import ACTION_ADDED

logger = logging.getLogger(__name__)


def render_event(event, user, method="GET"):
    # This is a covenience function to render an Event
    request = NonHttpRequest()
    request.method = method
    request.user = user

    if EventCategoryPermissions().has_object_permission(request, None, event):
        event_data = EventSerializer(event, context={"request": request}).data
        event_data["inferred_state"] = infer_event_state(event)
        return event_data
    else:
        logger.info("Permission denied when rendering event %s for user %s.", event.serial_number, user)
        return None


def infer_event_state(event):
    """
    When state is not 'resolved', it can be coerced to 'active' if its latest revision is 'updated'.
    :return: an inferred state (one of 'new', 'active', 'resolved')
    """

    if event.state in (Event.SC_RESOLVED, Event.SC_ACTIVE):
        return event.state

    event_revision, details_revision = resolve_event_revisions(event)
    inferred_state = Event.SC_NEW if event_revision and event_revision.action == "added" else Event.SC_ACTIVE
    return inferred_state


def resolve_event_revisions(event):
    """
    We end up in this code path in a few ways. Some data associated with the
    event has changed, but it could be the event itself or the event_details
    which contains the schema data. Or it could be both. It all depends on
    what fields were changed in the event update.

    To figure out what change(s) brought us here, we need to look at the
    timestamps on the latest revisions to both the event and eventdetails
    objects and see which one is newer.

    :param event_id:
    :return:
    """
    revision = event.revision.all_user().latest("revision_at")
    try:
        details_revision = event.event_details.latest("updated_at").revision.all_user().latest("revision_at")
    except (AttributeError, EventDetails.DoesNotExist):
        return revision, None

    # If the revision and details revision are both added, return the revisions.
    # because of the db transaction and contention in the save, have seen the
    # the difference between the revision.revision_at and details_revision.revision_at
    # be greater than 1 second.
    if revision.action == ACTION_ADDED and details_revision.action == ACTION_ADDED:
        return revision, details_revision

    diff = (revision.revision_at - details_revision.revision_at).total_seconds()

    # If the timestamps are < 1 second apart, they were very likely made
    # together
    if abs(diff) < 1:
        return revision, details_revision
    # If the changes are farther apart, take the later one only
    elif diff < 0:
        return None, details_revision
    else:
        return revision, None

from django.contrib.gis.geos import Point

from activity.models import Event, EventSource
from utils import add_base_url
from utils.json import empty_geojson_feature


def resolve_image_url(event):
    return event.image_url


def get_update_type(revision, previous_revisions=[]):
    field_mapping = (
        ("location", "update_location"),
        ("message", "update_message"),
        ("event_time", "update_datetime"),
        ("reported_by_id", "update_reported_by"),
        ("state", "update_event_state"),
        ("priority", "update_event_priority"),
        ("event_type", "update_event_type"),
    )
    model_name = revision._meta.model_name
    action = revision.action
    data = revision.data
    if action == "added":
        return "add_{0}".format(model_name.replace("revision", ""))
    elif action == "updated":
        event_state = data.get("state", None)
        if event_state:
            if event_state == Event.SC_RESOLVED:
                return Event.SC_RESOLVED
            if event_state == Event.SC_NEW:
                return "mark_as_new"
            for row in reversed(previous_revisions):
                prev_state = row.data.get("state", None)
                if prev_state:
                    if prev_state == Event.SC_RESOLVED:
                        return "unresolved"
                    if prev_state == Event.SC_NEW and event_state == Event.SC_ACTIVE:
                        return "read"
                    break
        for k, v in field_mapping:
            if k in data:
                return v
        return "update_event"
    return "other"


def get_user_display(user):
    if not user:
        return ""
    try:
        if user.get_full_name():
            return user.get_full_name()
    except NotImplementedError:
        pass
    return user.get_username()


def resolve_external_event_source(user, external_event_type):
    """Resolve external event source."""
    try:
        eventsource = EventSource.objects.get(owner=user, external_event_type=external_event_type)
        return eventsource
    except EventSource.DoesNotExist:
        pass


def get_allowed_actions_for_category(user, category_name):
    allowed_actions = set()
    geo_perm_actions = ("view", "add", "change", "delete")

    actions = {
        "create": "create",
        "update": "update",
        "read": "read",
        "delete": "delete",
        "add": "create",
        "change": "update",
        "view": "read",
    }

    for action in ("create", "update", "read", "delete") + geo_perm_actions:
        perm_name = f"activity.{category_name}_{action}"
        geo_perm_name = f"activity.{action}_{category_name}_geographic_distance"
        if user.has_perm(perm_name) or user.has_perm(geo_perm_name):
            action = actions[action]
            allowed_actions.add(action)
    return list(allowed_actions)


def make_feature(request, event):
    is_point = isinstance(event.coordinates, Point)
    image_url = resolve_image_url(event)
    image_url = add_base_url(request, image_url)
    feature = empty_geojson_feature()
    if event.coordinates:
        feature["geometry"] = {
            "type": "LineString" if not is_point else "Point",
            "coordinates": event.coordinates if not is_point else event.coordinates.tuple,
        }
    feature["properties"] = {
        "message": event.message,
        "datetime": event.time if isinstance(event.time, str) else event.time.isoformat(),
        "image": image_url,
    }

    properties = feature["properties"]
    if image_url:  # hasattr(event, 'image_url'):
        properties["icon"] = {
            "iconUrl": image_url,
            "iconSize": [25, 25],
            "iconAncor": [12, 12],
            "popupAncor": [0, -13],
            "className": "dot",
        }
    return feature

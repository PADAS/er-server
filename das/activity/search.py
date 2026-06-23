from __future__ import annotations

from django.db.models import F

from activity.models import Community, Event, EventCategory, EventType
from observations.models import Subject

EVENT_FILTER_SCHEMA = {
    "schema": {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Event Filter Specification Schema",
        "version": "1",
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "event_filter_id": {"type": "string"},
            "date_range": {
                "type": "object",
                "properties": {
                    "lower": {"type": "string", "format": "date-time"},
                    "upper": {"type": "string", "format": "date-time"},
                },
            },
            "duration": {"type": "string"},
            "priority": {"type": "array", "items": {"type": "string", "enum": []}},
            "state": {"type": "array", "items": {"type": "string", "enum": []}},
            "event_category": {"type": "array", "items": {"type": "string", "enum": []}},
            "event_type": {"type": "array", "items": {"type": "string", "enum": []}},
            "reported_by": {"type": "array", "items": {"type": "string", "enum": []}},
        },
    }
}


def castIdToString(o):
    o["id"] = str(o["id"])
    return o


from copy import deepcopy


def get_event_search_schema() -> dict:
    schema = deepcopy(EVENT_FILTER_SCHEMA)

    properties = schema["schema"]["properties"]

    event_types = EventType.objects.filter(category__is_active=True).values("id", "category_id", "display", "value")
    properties["event_type"]["items"]["enum"] = [castIdToString(i) for i in event_types]

    event_categories = EventCategory.objects.filter(is_active=True).values("id", "display", "value")
    properties["event_category"]["items"]["enum"] = [castIdToString(i) for i in event_categories]

    # Import inside the function to avoid any module-level import cycles and to
    # ensure the preview-feature flag is read at request time (tenant context is
    # set by middleware, not at import time).
    from activity.serializers.helpers import get_hidden_event_states

    hidden_states = get_hidden_event_states()
    properties["state"]["items"]["enum"] = [
        {"id": s[0], "display": s[1]} for s in Event.STATE_CHOICES if s[0] not in hidden_states
    ]
    properties["priority"]["items"]["enum"] = [{"id": s[0], "display": s[1]} for s in Event.PRIORITY_CHOICES]

    reported_by = list(Community.objects.all().annotate(display=F("name")).values("id", "display")) + list(
        Subject.objects.filter(
            subject_subtype="person",
        )
        .annotate(display=F("name"))
        .values("id", "display")
    )
    properties["reported_by"]["items"]["enum"] = [castIdToString(o) for o in reported_by]

    # template = Template(schema)
    # rendered_template = template.render(Context(parameters, autoescape=False))
    # schema = json.loads(rendered_template, object_pairs_hook=OrderedDict)

    return schema

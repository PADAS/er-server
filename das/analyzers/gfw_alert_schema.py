import json

from activity.models import EventType, EventCategory
from analyzers.environmental import EventTypeSpec

GENERIC_GFW_ALERT_SCHEMA = {
    "schema": {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "Event Type Global Forest Watch Alert",
        "type": "object",
        "properties": {
            "subscription_name": {
                "type": "string",
                "title": "Name of subscription with Global Forest Watch"
            },
            "alert_link": {
                "type": "string",
                "title": "URL of the map for this alert"
            },
        },
    },
    "definition": [
        "subscription_name",
        "alert_link"
    ]
}

GFWGladEventTypeSpec = EventTypeSpec(value='gfw_glad_alert',
                                  display='Global Forest Watch GLAD Tree-Loss Alert',
                                  schema=GENERIC_GFW_ALERT_SCHEMA)

GFWTerraiAlertEventTypeSpec = EventTypeSpec(value='gfw_terrai_alert',
                                  display='Global Forest Watch Terra-i Tree-Loss Alert',
                                  schema=GENERIC_GFW_ALERT_SCHEMA)

GFWActiveFireAlertEventTypeSpec = EventTypeSpec(value='gfw_activefire_alert',
                                  display='Global Forest Watch Active Fire Alert',
                                  schema=GENERIC_GFW_ALERT_SCHEMA)

# Map GFW Layer-Slug to an EarthRanger event-type.
GFW_EVENT_TYPES_MAP = {
    'viirs-active-fires': GFWActiveFireAlertEventTypeSpec.value,
    'glad-alerts': GFWGladEventTypeSpec.value,
    'terrai-alerts': GFWTerraiAlertEventTypeSpec.value
}

def ensure_gfw_event_types():
    ec, created = EventCategory.objects.get_or_create(
        value='analyzer_event', defaults=dict(display='Analyzer Events'))

    for event_type_spec in (GFWGladEventTypeSpec, GFWTerraiAlertEventTypeSpec, GFWActiveFireAlertEventTypeSpec):
        EventType.objects.get_or_create(value=event_type_spec.value,
                                        category=ec,
                                        defaults=dict(display=event_type_spec.display,
                                                      schema=json.dumps(event_type_spec.schema,
                                                                        indent=2,
                                                                        default=str)))

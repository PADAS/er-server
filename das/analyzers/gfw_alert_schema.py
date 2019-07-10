import json

from activity.models import EventType, EventCategory
from analyzers.environmental import EventTypeSpec

GFW_ALERT_SCHEMA = {
    "schema": {
        "$schema": "http://json-schema.org/draft-04/schema#",
        "title": "EventType Data",
        "type": "object",
        "properties": {
            "gfw_alert_type": {
                "type": "string",
                "title": "Type of GFW alert"
            },
            "subscription_name": {
                "type": "string",
                "title": "Name of subscription as specfied at GFW"
            },
            "selected_area": {
                "type": "string",
                "title": "Area in meters"
            },
            "subscriptions_url": {
                "type": "string",
                "title": "URL for user subscriptions"
            },
            "alert_url": {
                "type": "string",
                "title": "URL of the map for this alert"
            },
            "unsubscribe_url": {
                "type": "string",
                "title": "URL to unsubscribe for these alerts"
            },
        },
    },
    "definition": [
        "gfw_alert_type",
        "subscription_name",
        "selected_area",
        "subscriptions_url",
        "alert_url",
        "unsubscribe_url"
    ]
}

GFWAlertEventType = EventTypeSpec(value='gfw_alert',
                                  display='Global Forest Watch Alert',
                                  schema=GFW_ALERT_SCHEMA)


def ensure_gfw_event_type():
    ec, created = EventCategory.objects.get_or_create(
        value='analyzer_event', defaults=dict(display='Analyzer Events'))

    EventType.objects.get_or_create(value=GFWAlertEventType.value,
                                    category=ec,
                                    defaults=dict(display=GFWAlertEventType.display,
                                                  schema=json.dumps(GFWAlertEventType.schema,
                                                                    indent=2,
                                                                    default=str)))

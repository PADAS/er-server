import json

from activity.models import EventType, EventCategory
from analyzers.environmental import EventTypeSpec

GENERIC_GFW_TREE_LOSS_SCHEMA = {
   "schema":{
      "$schema":"http://json-schema.org/draft-04/schema#",
      "title":"Event Type Global Forest Watch Tree Loss Alert",
      "type":"object",
      "properties":{
         "subscription_name":{
            "type":"string",
            "title":"Name of subscription with Global Forest Watch"
         },
         "alert_link":{
            "type":"string",
            "title":"URL of the map for this alert",
            "format":"uri"
         },
         "confidence":{
            "type":"number",
            "title":"Confidence level of alert"
         },
         "num_clustered_alerts":{
            "type":"number",
            "title":"Number of clustered alerts"
         }
      }
   },
   "definition":[
      "subscription_name",
      "alert_link",
      "confidence",
      "num_clustered_alerts"
   ]
}

GENERIC_GFW_ACTIVE_FIRE_SCHEMA = {
   "schema":{
      "$schema":"http://json-schema.org/draft-04/schema#",
      "title":"Event Type Global Forest Watch Active Fire Alert",
      "type":"object",
      "properties":{
         "bright_ti4": {
            "type": "string",
            "title": "VIIRS I-4 channel brightness (Kelvin)"
         },
         "bright_ti5": {
            "type": "string",
            "title": "VIIRS I-5 channel brightness (Kelvin)"
         },
         "scan": {
            "type": "string",
            "title": "VIIRS Scan"
         },
         "track": {
            "type": "string",
            "title": "Satellite Track"
         },
         "frp": {
            "type": "string",
            "title": "Fire Radiative Power (MW)"
         },
         "subscription_name":{
            "type":"string",
            "title":"Name of subscription with Global Forest Watch"
         },
         "alert_link":{
            "type":"string",
            "title":"URL of the map for this alert",
            "format":"uri"
         },
         "confidence":{
            "type":"string",
            "title":"Confidence level of alert"
         },
         "num_clustered_alerts":{
            "type":"number",
            "title":"Number of clustered alerts"
         }
      }
   },
   "definition":[
      "bright_ti4",
      "bright_ti5",
      "scan",
      "track",
      "frp",
      "subscription_name",
      "alert_link",
      "confidence",
      "num_clustered_alerts"
   ]
}

GFWGladEventTypeSpec = EventTypeSpec(value='gfw_glad_alert',
                                     display='GLAD Tree-Loss Alert (GFW)',
                                     schema=GENERIC_GFW_TREE_LOSS_SCHEMA,
                                     icon='deforestation_rep')

GFWActiveFireAlertEventTypeSpec = EventTypeSpec(value='gfw_activefire_alert',
                                                display='Active Fire Alert (GFW)',
                                                schema=GENERIC_GFW_ACTIVE_FIRE_SCHEMA,
                                                icon='fire_rep')

# Map GFW Layer-Slug to an EarthRanger event-type.
GFW_EVENT_TYPES_MAP = {
    'viirs-active-fires': GFWActiveFireAlertEventTypeSpec.value,
    'glad-alerts': GFWGladEventTypeSpec.value,
}


def ensure_gfw_event_types():
    ec, created = EventCategory.objects.get_or_create(
        value='analyzer_event', defaults=dict(display='Analyzer Events'))

    for event_type_spec in (GFWGladEventTypeSpec, GFWActiveFireAlertEventTypeSpec):
        EventType.objects.get_or_create(value=event_type_spec.value,
                                        category=ec,
                                        defaults=dict(display=event_type_spec.display,
                                                      icon=event_type_spec.icon,
                                                      schema=json.dumps(event_type_spec.schema,
                                                                        indent=2,
                                                                        default=str)))

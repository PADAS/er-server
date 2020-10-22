.. _activity:

Input Reports
===========================

Input Reports in EarthRanger are used primarily for capturing observed data.
For example, a ranger observing a wildlife sighting or finding a broken fence.
An automated system publishes FIRMS reports. Most reports have a lat/lon georeference as part of the observation.

Input Reports are referred to as events internally. You may encounter language such as events, event_type or event_details.
The event is the common data across all reports. Event_details stores the json document of report specific data.
The event_type describes the schema for the event_details using JSON Schema.

See the EarthRanger Admin guide, specifically on the section "REPORT AND EVENT TYPE CONFIGURATION" which will
walk you through create a new report and the schema describing the data to be collected in the report.


Look here for the interactive API docs. Reports/events are found in the Activity section.
`here </api/v1.0/docs/interactive/>`_

This API is used to publish reports either from a UI or from another external entity.
It is assumed the event type has already been created and the API user references that when publishing data.

To take a tour through the API:

1. Retrieve the list of schemas '</api/v1.0/activity/events/schema/>'
2. Retrieve the schema of on event_type, this returns the arrest_rep schema '</api/v1.0/activity/events/schema/eventtype/arrest_rep>'
3. To Post a new event, we post the json document to: '</api/v1.0/activity/events>'
    Example::
        {
            "event_type": "arrest_rep",
            "icon_id": "arrest_rep",
            "is_collection": false,
            "location": null,
            "priority": 0,
            "reported_by": null,
            "time": "2020-10-22T05:03:17.374Z",
            "event_details": {
                "arrestrep_name": "John Doe",
                "arrestrep_age": 30,
                "arrestrep_villagename": "Bellevue",
                "arrestrep_nationality": "chad",
                "arrestrep_reaonforarrest": "charcoal",
                "arrestrep_arrestingranger": "John"
            }
        }
ER FAQ
========================
## General

## API
### Reports
Internally, ER Input Reports are referred to as events. When any part of an event is updated, a field called “updated_at” reflects the time of last update. There is also an “updates” field in an event that contains the list of recent updates, including user that made the update.

ER has a paging API, with the default being 25 items per page. The default is to return items sorted by descending “updated_at”.

#### Search
We have basic keyword search capability.

#### Real-time updates
An alternative to polling for updates, ER provides a real-time SocketIO based api which pushes event updates. https://easterisland.pamdas.org/docs/realtime.html

#### Report Schema
For each report type, you can ask for the schema which lists the enumerations for a field. 
See https://easterisland.pamdas.org/api/v1.0/docs/#!/activity/Event_Types_GET to get a list of eventtypes then use this to get the schema: https://easterisland.pamdas.org/api/v1.0/docs/#!/activity/Event_Schema_GET

#### Collections and Incidents
Events can be contained in another event called an Incident or more generally a collection. You will see this in the event data returned.

#### Attachments
Events can contain attachments which are listed. Images or office documents are the predominant type of attachments.

#### GMT or Local time?
All times in ER are stored as GMT and includes the time offset if included.


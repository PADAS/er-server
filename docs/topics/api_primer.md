# EarthRanger API Primer
As a developer onboarding to publish data to ER or otherwise use the ER API, here is some overview information.
After sending you a link to this page, we will set you up with an account on an ER server we setup explicitely for testing against.
You’ll get an email momentarily with an invite to a sandbox server.
 
On the development side, take a look here for overall API descriptions: https://sandbox.pamdas.org/api/v1.0/docs/
There is also an interactive API found here: [interactive API](https://sandbox.pamdas.org/api/v1.0/docs/interactive/) . Be sure to login here before accessing the interactive API [ER Admin](https://sandbox.pamdas.org/admin/)
 
You can create an oauth token here: https://sandbox.pamdas.org/admin/oauth2_provider/accesstoken/
 
There’s a fairly rudimentary Python library here: https://github.com/PADAS/das-clients/
 
If you want to proceed without the Python library, the more general sensor integration is at: https://sandbox.pamdas.org/api/v1.0/sensors/generic/<source_provider>/status
where <source_provider> is the key of the source provider defined at https://sandbox.pamdas.org/admin/observations/sourceprovider/


## Posting sensor data
The general concept is that a source provides location information for a subject.  For example, a collar is a source and an elephant is the subject.  The source provider is a service that provides information about those sources.  For example, Acme Collars.  With that in mind...
 
As is typical, API headers:
~~~
               Authorization: Bearer <token>
               Accept: application/json
               Content-Disposition: attachment; filename={}
               Content-Type: application/json
~~~

The body of a location request looks like:        
~~~
        {
               "location":
               {
                               "lat":47.123,
                               "lon":-122.123
               },
               "recorded_at":"2019-02-19T13:59:15.000Z",
               "manufacturer_id":"SomeUniqueIDForTheDevice",
               "subject_name":"Car 4",
               "subject_type":"vehicle",
               "subject_subtype":"car",
               "model_name":"Land Cruiser",
               "source_type":"tracking_device",
               "additional":{}
        }
~~~

Note that if you pass in an observation where the system hasn’t seen that source-provider / manufacturer_id combination before it’ll create sources and subjects as necessary.
 
For posting events (like a detected chainsaw), here are some sample API calls:
 
## Create an event

POST to https://sandbox.pamdas.org/api/v1.0/activity/events
 
Headers:
~~~
·         Authorization: Bearer xxxxxxxx
·         Accept: application/json
·         Content-Disposition: attachment; filename={}
·         Content-Type: application/json
~~~ 
Body example:
~~~
{
               "event_type": "mist_rep",
              "time": "2019-01-17T06:18:44.056439",
              "location": {"latitude": 47.123, "longitude": -122.123},
              "event_details": {
               "mistrep_Method": "Bagel slicer",
                           "mistrep_Injury": "Severed thumb",
                                "mistrep_Symptoms": "Missing thumb",
                                "mistrep_Treatment": "Band-aid"
},
"priority": 100
}
~~~

Note that event_type and the fields for event_details correspond to the entry in the Django admin’s Activity > Event types page
  
## Add attachment (like an audio file)

POST to https://sandbox.pamdas.org/api/v1.0/activity/event/{EVENT_ID}/files/

•	The EVENT_ID is the GUID that gets created when you create the event (above)
 
Headers:
~~~
·         Authorization: Bearer xxxxxxxx
·         Accept: application/json
·         Content-Disposition: attachment; filename={}
·         Content-Type: application/json
~~~
Body: form-data
~~~
filecontent.file: <file>
~~~

## Create an event and associate a subject to it
In the case where a subject (animal, vehicle, person) is associated with the event, relate that existing subject with the event.

POST to https://sandbox.pamdas.org/api/v1.0/activity/events
 
Headers:
~~~
·         Authorization: Bearer xxxxxxxx
·         Accept: application/json
·         Content-Disposition: attachment; filename={}
·         Content-Type: application/json
~~~ 
Body example:
~~~
{
        "event_type": "geofence_rep",
        "time": "2019-01-17T06:18:44.056439",
        "location": {"latitude": 47.123, "longitude": -122.123},
        "event_details": {
            "speed": 50
        },
        "priority": 100,
        related_subjects: [
                {
                    "content_type": "observations.subject",
                    "id": "74865994-5ce9-486e-a953-42e802c38275"
                }
        ]
}
~~~

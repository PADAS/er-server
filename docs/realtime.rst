.. _realtime:

Real-time DAS API
===========================

Requests
----------------------------
From the client to the server, these are the requests. The first request is the authenticate request.
All client messages are to include an integer id that is used
to match the response from the server. The matching id is found in resp_id field
found in the response message.

authorization
^^^^^^^^^^^^^^^^^^^^^^^^^^^
The first thing to do after the low level websocket is connected is to send an
authorization message to the server. Failure to do this will result in the
server disconnecting the websocket.

.. code-block:: json

    {
    "type": "authorization",
    "Authorization": "Bearer <code here that came from OAuth call>",
    "id": 1
    }

resp_authorization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
This is the response from an authorization call to the server

.. code-block:: json

    {
    "type": "resp_authorization",
    "resp_id": 1,
    "status": {
        "code": 200,
        "message": "OK"
        }
    }



Messages
-----------------------------
These are the messages originating from the server and sent out to the registered clients.

subject_update
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The "data" block contains a single subject, plus if the user is authorized subject contains
a field "track" which is the latest geojson track for that subject.

.. code-block:: json

    {
    "type": "subject_update"
    "data": {
    }
    }
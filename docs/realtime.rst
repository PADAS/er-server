.. _realtime:

Real-time DAS API
===========================

Requests
----------------------------
From the client to the server, these are the requests. The first request is the authenticate request

authorization
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: json

    {
    "type": "authorization",
    "Authorization": "Bearer <code here that came from OAuth call>",
    "id": 1
    }

return authorization success value

.. code-block:: json

    {
    "return_id": 1,
    "status": {
        "code": 200,
        "message": "OK"
        }
    }



Messages
-----------------------------
These are the messages originating from the server out to the registered clients

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
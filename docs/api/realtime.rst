.. _realtime:

Real-time DAS API
===========================

DAS realtime communications are performed using SocketIO compliant protocols. Several libraries exist in javascript and other languages.
See here for more information on using the basic protocol (SocketIO)[https://socket.io/]

The DAS server is today using this library to implement our Socket IO server (python-socketio)[https://github.com/miguelgrinberg/python-socketio]

Requests
----------------------------
All client messages are to include an integer id that is used
to match the response from the server. The matching id is found in resp_id field
found in the response message.

SocketIO does not define authentication handshakes directly. To address authentication, we use our OAuth token as retrieved from login to authorize communication across this channel.

authorization
^^^^^^^^^^^^^^^^^^^^^^^^^^^
The first thing to do after the low level websocket is connected is to send an
authorization message to the server. Failure to do this will result in the
server disconnecting the websocket. Expect to send the autorization message soon after websocket connect as the window of time from web connect to sending the authorization is short.

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



Event Messages
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

Request Messages
----------------------------
The authorization message above is an example of a request to the server.


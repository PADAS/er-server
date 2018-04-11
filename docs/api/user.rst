.. _user:

Users and Permissions
===========================

New User Requirements
---------------------------
username
 * max length 30 characters
 * must be unique
 * may only contain letters, numbers and @.+-_ characters

first_name, last_name
 * max length 30 characters

email
 * valid email address

phone
 * max length 15 characters
 * in the format +999999999

password
 * min length 9
 * cannot contain username, first_name, last_name or email
 * cannot be a common password, as found by a list of 1000 words compiled by `Mark Burnett <https://web.archive.org/web/20150315154609/https://xato.net/passwords/more-top-worst-passwords/>`_
 * cannot be all numbers

Users API
-----------------------------

.. http:get:: /users/

   Get all users in the system.

   :reqheader Authorization: Bearer <auth token>
   :reqheader Accept: application/json

   :statuscode 200: no error

.. http:get:: /user/<user id>

    Get a specific user, or the logged in user.

   **Example request**:

   .. sourcecode:: http

      GET /users/me HTTP/1.1
      Host: pamdas.org
      Accept: application/json

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json

      {
        "status": {
          "message": "OK",
          "code": 200
        },
        "data": {
            "username": "testuser",
            "created_at": "2015-10-31T17:06:41.017209+00:00",
            "id": "3AAC114D-8922-4024-8D34-377AE87D6E71",
            "name": "Test User",
            "email": "testuser@test.com"
        }
      }

   :reqheader Authorization: Bearer <auth token>
   :reqheader Accept: application/json

   :statuscode 200: no error
.. _oauth2:

OAuth 2
===========================

DAS API Authorization. All API calls must be authorized using app authorization or user authorization.
Use the client_id query parameter on all API calls if not calling in the context of a User with an Authorization Token.

.. http:get:: /oauth2/authorize/

   Get an authorization code for the currently authorized user.

   :query response_type: literally 'code'
   :query client_id: oauth2 client ID
   :query redirect_uri: The redirect URI that is registered for the given client_id
   :resheader Location: The callback location, plus auth code.
   :reqheader Authorization: Bearer authorization for the authorized user.
   :statuscode 200: no error

   **Example request**:

   .. sourcecode:: http

      GET /oauth2/authorize/ HTTP/1.1
      Host: das-server

      response_type=code&client_id=1&redirect_uri=http://tempuri.org/callback?foo=bar

   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Location: https://tempuri.org/oauth2callback?code=FGaVZHmvpeXzxSY0585wocaev0DYWnpex0U6Vfsn&foo=bar




.. http:POST:: /oauth2/token/

   Log in using username and password.

   :form grant_type: password (literally)
   :form username: A valid username
   :form password: The valid password
   :form client_id: The OAuth2 client ID
   :statuscode 200: no error

   **Example request**:

   .. sourcecode:: http

      POST /oauth2/token/ HTTP/1.1
      Host: das-server
      Content-Type: application/x-www-form-urlencoded
      Accept: application/json

      grant_type=password&username=billybob&password=foobar&client_id=1


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json

      {
        "access_token": "JlOZZ7B8syj0jvi1unArrPesy5IFwqjIMU2dw4NS",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "fHp597b9iYc0bumaUqlcwDiJsWExFW98nM0fveWM"
      }


.. http:POST:: /oauth2/token/

   Get a new access_token using a saved "refresh_token".

   :form grant_type: refresh_token (literally)
   :form refresh_token: refresh token string
   :form client_id: client ID
   :form client_secret: client secret (or empty for confidential client)
   :statuscode 200: no error

   **Example request**:

   .. sourcecode:: http

      POST /oauth2/token/ HTTP/1.1
      Host: das-server
      Content-Type: application/x-www-form-urlencoded
      Accept: application/json

      grant_type=refresh_token&refresh_token=fHp597b9iYc0bumaUqlcwDiJsWExFW98nM0fveWM&client_id=1&client_secret=gobblygook


   **Example response**:

   .. sourcecode:: http

      HTTP/1.1 200 OK
      Content-Type: application/json

      {
        "access_token": "aEr3oISDf789DuiA&89Afaoiufda3781aAF8ffeu",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "asdfoi8asf90890aafjdkajsfoiueapiueoupaeF"
      }


.. http:POST:: /oauth2/revoke_token/

    Revoke an existing token

   :form token: the token to revoke
   :form client_id: client ID
   :form client_secret: client secret (or empty for confidential client)
   :statuscode 200: no error

   **Example request**:

   .. sourcecode:: http

      POST /oauth2/revoke_token/ HTTP/1.1
      Host: das-server
      Content-Type: application/x-www-form-urlencoded
      Accept: application/json

      token=fHp597b9iYc0bumaUqlcwDiJsWExFW98nM0fveWM&client_id=das
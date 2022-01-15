:orphan:

==============
Authentication
==============

Token-based
-----------

This method uses a simple token-based HTTP Authentication scheme ideal for client-server configurations (i.e. native desktop or mobile clients). To acquire tokens, applications should use the `Token <https://lnl.wpi.edu/api/schema/swagger/#/token/Token>`_ endpoint, unless instructed otherwise by our Webmaster. Note that use of this endpoint will require an approved project registration.


Retrieving Tokens
^^^^^^^^^^^^^^^^^

Before you will be able to fetch a user's token, you will first need to direct them to grant access to your application. This can be accomplished by opening the following URL in any web browser:

.. code-block:: text

    https://lnl.wpi.edu/api/token/request/{CLIENT_ID}/

where ``{CLIENT_ID}`` is your application's assigned identifier. Once the user has enabled access to their account, they will be sent a verification code which they will then need to enter into your application. You will need to POST this code, along with your API Key and their username, to the `Token endpoint <https://lnl.wpi.edu/api/schema/swagger/#/token/Token>`_. If everything checks out, then the server will return the user's token.

-----

**Example:**

.. code-block:: text

    POST https://lnl.wpi.edu/api/token/fetch/

    {"APIKey": "API_KEY", "code": 123456, "username": "rhgoddard"}

If successful, this would return something like:

.. code-block:: text

    HTTP/1.1 200 OK
    Content-Type: application/json
    Content-Length: 52

    {"token":"9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"}

.. tip::
    Note that, at any given time, tokens can be revoked or changed either by the system or the user. Your application should therefore be prepared to handle this accordingly. To fetch the new token (if applicable), simply repeat the process above.


Using Tokens
^^^^^^^^^^^^

To authenticate using your token, simply include your key in the ``Authorization`` HTTP header. The key should be prefixed by the string literal "Token", with whitespace separating the two strings.

.. code-block:: text

    Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b

-----

Project-based
-------------

Access to some endpoints may be limited to certain registered applications only. This method is often used with backend services that do not handle user data. To gain access to an endpoint that utilizes project-based authentication, contact our `Webmaster <mailto:lnl-w@wpi.edu>`_.

`Last modified: January 15, 2022`

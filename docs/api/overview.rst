=========
LNLDB API
=========

The LNL API is a simple REST API which can be used to connect apps and services with the LNL Database (LNLDB). This
guide provides an overview of the API and its authentication methods.

-----

Getting Started
---------------

The LNL API can be accessed through standard HTTP requests and will return JSON metadata. To access protected
information, your application will be required to authenticate with the LNLDB first. The API is currently configured to
respond to the following HTTP Methods:

+---------+-------------------------------------------------+
| Method  | Action                                          |
+=========+=================================================+
| GET     | Retrieves a specified resource                  |
+---------+-------------------------------------------------+
| POST    | Sends information to the database               |
+---------+-------------------------------------------------+
| OPTIONS | Provides communication options for the endpoint |
+---------+-------------------------------------------------+

.. note::
    If attempting to communicate with the API through methods such as ajax, note that by default, CORS prohibits
    cross-origin requests. You may need to register your application with the API before using such methods. Contact
    lnl-w@wpi.edu for assistance.

-----

API Reference
-------------

.. raw:: html

    <a class="btn btn-primary" href="https://lnl.wpi.edu/api/schema/swagger/">View Reference</a>
    <br><br>

-----

Authentication
--------------

While most of our endpoints are public, some do require authentication. Check out our :doc:`Authentication <authentication>` guide for more information.

# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from data.tests.util import ViewTestCase
from django.test import TestCase
from rest_framework.exceptions import APIException, PermissionDenied
from . import models, views


# Create your tests here.
class APIViewTest(ViewTestCase):
    def setUp(self):
        endpoint = models.Endpoint.objects.create(name="Example", url="example", description="Example endpoint",
                                                  example="title=something", response="[]")
        endpoint.save()
        # Include additional methods to test various authentication options
        method = models.Method.objects.create(endpoint=endpoint, method="GET", auth="none")
        method.save()

    def test_verify_endpoint(self):
        # Try with endpoint that is not yet configured
        with self.assertRaises(APIException, detail="Configuration error. Please contact the webmaster.", code=500):
            views.verify_endpoint("Example2")

        # Try with endpoint that requires authentication - (not supported yet)
        endpoint = models.Endpoint.objects.get(name="Example")
        for method in endpoint.methods.all():
            if method.auth != "none":
                with self.assertRaises(PermissionDenied, detail="You are not allowed to access this resource.", code=403):
                    views.verify_endpoint("Example")

        # Try with properly configured endpoint
        self.assertEqual(views.verify_endpoint("Example"), None)

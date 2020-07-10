# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from data.tests.util import ViewTestCase
from django.urls.base import reverse
from django.contrib.auth.models import Group
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied
from . import models, views
from .templatetags import path_safe
from events.tests.generators import UserFactory
from events.models import OfficeHour, HourChange
from data.models import Notification
import pytz
import logging


logging.disable(logging.WARNING)


# Create your tests here.
class APIViewTest(ViewTestCase):
    def test_path_safe(self):
        string = "Home/LNL/Directory"
        output = "Home-LNL-Directory"
        self.assertEqual(path_safe.path_safe(string), output)

    def test_verify_endpoint(self):
        endpoint = models.Endpoint.objects.create(name="Example", url="example", description="Example endpoint",
                                                       example="title=something", response="[]")
        # Include additional methods to test various authentication options
        endpoint_get = models.Method.objects.create(endpoint=endpoint, method="GET", auth="session")

        # Try with endpoint that is not yet configured
        with self.assertRaises(APIException, detail="Configuration error. Please contact the webmaster.", code=500):
            views.verify_endpoint("Example2")

        # Try with endpoint that requires authentication - (not supported yet)
        for method in endpoint.methods.all():
            if method.auth != "none":
                with self.assertRaises(PermissionDenied,
                                       detail="You are not allowed to access this resource.", code=403):
                    views.verify_endpoint("Example")

        # Try with properly configured endpoint
        endpoint_get.auth = "none"
        endpoint_get.save()
        self.assertEqual(views.verify_endpoint("Example"), None)

    def test_officer_endpoint(self):
        models.Endpoint.objects.create(name="Officers", url="officers", description="Officer endpoint",
                                       example="title=something", response="[]")

        # Test that we get 404 when there are no officers
        self.assertOk(self.client.get("/api/v1/officers"), 404)

        # Test that we see all officers and not normal user (will require user to have title)
        self.user.title = "President"
        self.user.first_name = "Test"
        self.user.last_name = "User"
        self.user.save()

        officer = Group.objects.create(name="Officer")
        officer.user_set.add(self.user)

        user2 = UserFactory.create(password="123", first_name="Other", last_name="Officer")
        UserFactory.create(password="456")
        officer.user_set.add(user2)

        self.assertEqual(self.client.get("/api/v1/officers").content.decode('utf-8'),
                         '[{"title":"President","name":"Test User"}]')

        user2.title = "Vice President"
        user2.save()

        self.assertEqual(self.client.get("/api/v1/officers").content.decode('utf-8'),
                         '[{"title":"President","name":"Test User"},{"title":"Vice President","name":"Other Officer"}]')

        # Test that we can get a specific officer's info (based on title)
        self.assertEqual(self.client.get("/api/v1/officers?title=president").content.decode('utf-8'),
                         '[{"title":"President","name":"Test User"}]')

        # Test that we can get a specific officer's info (based on name) - If both parameters, results must match both
        self.assertEqual(self.client.get("/api/v1/officers?first_name=test&last_name=user").content.decode('utf-8'),
                         '[{"title":"President","name":"Test User"}]')

        # Test additional custom options
        self.user.class_year = 2020
        self.user.save()

        self.assertEqual(self.client.get("/api/v1/officers?title=president&options=class_year").content.decode('utf-8'),
                         '[{"title":"President","name":"Test User","class_year":2020}]')

    def test_hour_viewset(self):
        models.Endpoint.objects.create(name="Office Hours", url="office-hours", description="Office Hours Endpoint",
                                       example="officer=president", response="[]")
        self.user.title = "President"
        self.user.save()

        user2 = UserFactory.create(password="123", title="Vice President")

        # Test that no content returns a 204
        self.assertOk(self.client.get("/api/v1/office-hours"), 204)

        # Test that we can get all office hours
        start_time = timezone.now()
        end_time = timezone.now() + timezone.timedelta(hours=1)
        hour1 = OfficeHour.objects.create(officer=self.user, day=1, hour_start=start_time.time(),
                                          hour_end=end_time.time())
        hour2 = OfficeHour.objects.create(officer=user2, day=3, hour_start=start_time.time(), hour_end=end_time.time())

        self.assertEqual(self.client.get("/api/v1/office-hours").content.decode('utf-8'),
                         '[{"officer":"President","day":1,"hour_start":"' + str(start_time.time()) + '","hour_end":"' +
                         str(end_time.time()) + '"},{"officer":"Vice President","day":3,"hour_start":"' +
                         str(start_time.time()) + '","hour_end":"' + str(end_time.time()) + '"}]')

        # Test that we can get office hours for a specific officer
        self.assertEqual(self.client.get("/api/v1/office-hours?officer=president").content.decode('utf-8'),
                         '[{"officer":"President","day":1,"hour_start":"' + str(start_time.time()) +
                         '","hour_end":"' + str(end_time.time()) + '"}]')

        # Test that we can filter office hours by the day
        self.assertEqual(self.client.get("/api/v1/office-hours?day=3").content.decode('utf-8'),
                         '[{"officer":"Vice President","day":3,"hour_start":"' + str(start_time.time()) +
                         '","hour_end":"' + str(end_time.time()) + '"}]')

        # Test that we can get office hours that start at a certain time (exact match)
        start_time = timezone.datetime.strptime('13:30', '%H:%M').replace(tzinfo=pytz.timezone('US/Eastern'))
        end_time = timezone.datetime.strptime('15:30', '%H:%M').replace(tzinfo=pytz.timezone('US/Eastern'))

        # Ensure that only 1 result will appear in the tests below
        hour1.hour_start = start_time + timezone.timedelta(hours=3)
        hour1.hour_end = end_time + timezone.timedelta(hours=2)
        hour2.hour_start = start_time + timezone.timedelta(hours=3)
        hour2.hour_end = end_time + timezone.timedelta(hours=2)
        hour1.save()
        hour2.save()

        OfficeHour.objects.create(officer=self.user, day=4,
                                  hour_start=start_time.time(),
                                  hour_end=end_time.time())

        self.assertEqual(self.client.get("/api/v1/office-hours?start=13:30:00").content.decode('utf-8'),
                         '[{"officer":"President","day":4,"hour_start":"13:30:00","hour_end":"15:30:00"}]')

        # Test that we can get office hours that end at a certain time (exact match)
        self.assertEqual(self.client.get("/api/v1/office-hours?end=15:30:00").content.decode('utf-8'),
                         '[{"officer":"President","day":4,"hour_start":"13:30:00","hour_end":"15:30:00"}]')

        # Test that if both start and end times are provided the result contains entries that overlap with those times
        self.assertEqual(self.client.get("/api/v1/office-hours?start=13:00:00&end=14:00:00").content.decode('utf-8'),
                         '[{"officer":"President","day":4,"hour_start":"13:30:00","hour_end":"15:30:00"}]')

    def test_hourchange_viewset(self):
        models.Endpoint.objects.create(name="Office Hour Updates", url="hours/updates",
                                       description="Office Hour Updates endpoint",
                                       example="expires=2020-01-01T00:00:00Z", response="[]")
        self.user.title = "President"
        self.user.save()

        user2 = UserFactory.create(password="123")
        user2.title = "Treasurer"
        user2.save()

        # Test that we get 204 response if no updates exist
        self.assertOk(self.client.get("/api/v1/hours/updates"), 204)

        post_date = timezone.datetime.strptime("2019-12-01T12:00:00Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
        expires_before = timezone.datetime.strptime("2019-12-31T23:59:00Z", "%Y-%m-%dT%H:%M:%SZ")\
            .replace(tzinfo=pytz.UTC)
        expires_match = timezone.datetime.strptime("2020-01-01T00:00:00Z", "%Y-%m-%dT%H:%M:%SZ")\
            .replace(tzinfo=pytz.UTC)
        expires_after = timezone.datetime.strptime("2020-01-03T00:00:00Z", "%Y-%m-%dT%H:%M:%SZ")\
            .replace(tzinfo=pytz.UTC)
        HourChange.objects.create(officer=self.user, expires=expires_before, message="Test Hour Change",
                                  date_posted=post_date)
        HourChange.objects.create(officer=user2, expires=expires_match, message="Another test hour change",
                                  date_posted=post_date)
        HourChange.objects.create(officer=self.user, expires=expires_after, message="Even more hours will change",
                                  date_posted=post_date)

        # Test that we get all updates
        self.assertEqual(len(self.client.get("/api/v1/hours/updates").data), 3)

        # Test that we can get updates by officer
        resp = self.client.get("/api/v1/hours/updates?officer=treasurer")
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]["message"], "Another test hour change")

        # Test that we can get updates based on when they expire (on or after specified date)
        resp = self.client.get("/api/v1/hours/updates?expires=2020-01-01T00:00:00Z")
        self.assertEqual(len(resp.data), 2)
        self.assertEqual(resp.data[0]["message"], "Another test hour change")
        self.assertEqual(resp.data[1]["message"], "Even more hours will change")

    def test_notification_viewset(self):
        models.Endpoint.objects.create(name="Notifications", url="notifications", description="Notifications endpoint",
                                       example="page_id=home", response="[]")

        # Test that we get 204 response when no notifications exist
        self.assertOk(self.client.get("/api/v1/notifications?project_id=LNL&page_id=/"), 204)

        expired = timezone.datetime.strptime("2020-01-01T00:00:00Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
        not_expired = timezone.now() + timezone.timedelta(days=15)
        not_expired = timezone.datetime.strptime(not_expired.strftime("%Y-%m-%dT%H:%M:%SZ"), "%Y-%m-%dT%H:%M:%SZ")\
            .replace(tzinfo=pytz.UTC)

        # Class I notification (see docs)
        Notification.objects.create(title="Test Notification", message="Some test text", format="notification",
                                    type="advisory", dismissible=False, target="All", expires=expired)
        # Class II notification (see docs)
        Notification.objects.create(title="Another Test Notification", message="Some test text", format="alert",
                                    type="info", dismissible=True, target="All", expires=not_expired)
        # Class III notification (see docs)
        Notification.objects.create(title="Third Notification", message="Some test text", format="notification",
                                    type="warning", dismissible=True, target="events", expires=not_expired)

        # Test that failing to include Project ID results in an error
        self.assertOk(self.client.get("/api/v1/notifications"), 404)

        # Test that failing to include Page ID results in an error
        self.assertOk(self.client.get("/api/v1/notifications?project_id=LNL"), 400)

        # Test that default configuration returns notifications with a target of "all" (includes expired alerts)
        default_response = [{"id": "LNLWN-1", "class": 1, "format": "notification", "type": "advisory",
                             "expires": expired, "title": "Test Notification", "message": "Some test text"},
                            {"id": "LNLWN-2", "class": 2, "format": "alert", "type": "info", "expires": not_expired,
                             "title": "Another Test Notification", "message": "Some test text"}]
        self.assertEqual(self.client.get("/api/v1/notifications?project_id=LNL&page_id=/").data, default_response)

        # Test directory matching
        dir_response = [{"id": "LNLWN-1", "class": 1, "format": "notification", "type": "advisory", "expires": expired,
                         "title": "Test Notification", "message": "Some test text"},
                        {"id": "LNLWN-2", "class": 2, "format": "alert", "type": "info", "expires": not_expired,
                         "title": "Another Test Notification", "message": "Some test text"},
                        {"id": "LNLWN-3", "class": 3, "format": "notification", "type": "warning",
                         "expires": not_expired, "title": "Third Notification", "message": "Some test text"}]
        self.assertEqual(self.client.get("/api/v1/notifications", {"project_id": "LNL", "page_id": "/events/index.html",
                                                                   "directory": "/events"}).data, dir_response)

        self.assertEqual(self.client.get("/api/v1/notifications",
                                         {"project_id": "LNL", "page_id": "/meetings/index.html",
                                          "directory": "/meetings"}).data, default_response)

    def test_docs(self):
        # Create a couple endpoints to include in the docs
        models.Endpoint.objects.create(name="Endpoint 1", url="first", description="First endpoint",
                                       example="id=example", response="[]")
        models.Endpoint.objects.create(name="Endpoint 2", url="second", description="Second endpoint",
                                       example="id=example", response="[]")

        self.assertOk(self.client.get(reverse("api:documentation")))

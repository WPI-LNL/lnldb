# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from data.tests.util import ViewTestCase
from django.test.client import RequestFactory
from django.urls.base import reverse
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.sites.shortcuts import get_current_site
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.authtoken.models import Token
from . import models, views
from .templatetags import path_safe
from events.tests.generators import UserFactory, Event2019Factory, CCInstanceFactory
from events.models import OfficeHour, Building, Location, CrewAttendanceRecord
from data.models import Notification, Extension, ResizedRedirect
from pages.models import Page
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
        endpoint_get = models.Method.objects.create(endpoint=endpoint, method="GET", auth="token")

        # Try with endpoint that is not yet configured
        with self.assertRaises(APIException, msg="Configuration error. Please contact the webmaster."):
            views.verify_endpoint("Example2", None)

        # Try with endpoint that requires authentication
        for method in endpoint.methods.all():
            if method.auth != "none":
                request = RequestFactory()
                request.user = self.user
                request.data = {'APIKey': 'ABCDEFG'}
                request.method = 'GET'
                with self.assertRaises(PermissionDenied, msg="You are not allowed to access this resource."):
                    views.verify_endpoint("Example", request)

        # Try with properly configured endpoint
        endpoint_get.auth = "none"
        endpoint_get.save()
        self.assertEqual(views.verify_endpoint("Example", None), None)

    def test_token_endpoint(self):
        # Check that page loads ok
        self.assertOk(self.client.get(reverse("api:request-token")))

        # If user does not have phone number and carrier listed, they will need to fill out the form
        self.assertOk(self.client.post(reverse("api:request-token")))

        self.assertFalse(models.TokenRequest.objects.filter(user=self.user).exists())

        valid_data = {
            "phone": 1234567890,
            "carrier": "vtext.com",
            "save": "Continue"
        }

        self.assertOk(self.client.post(reverse("api:request-token"), valid_data))

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, '1234567890')

        # User must confirm that information is accurate (users who have already provided this information start here)
        resp = self.client.post(reverse("api:request-token"), valid_data)
        self.assertContains(resp, "Check your messages")

        self.assertTrue(models.TokenRequest.objects.filter(user=self.user).exists())

        # If code expires on the user, check that they can request a new one (will replace exisiting code)
        resp = self.client.post(reverse("api:request-token"), valid_data)
        self.assertContains(resp, "Check your messages")

        # Ensure GET requests are not allowed when obtaining the token with verification code
        self.assertOk(self.client.get(reverse("api:fetch-token")), 405)

        # If information is missing we should get a 400 error
        self.assertOk(self.client.post(reverse("api:fetch-token"), {'code': 12345}), 400)

        # Application should send the following to obtain the token
        token_request = models.TokenRequest.objects.get(user=self.user)
        data = {
            "APIKey": "ABCDEFG",
            "code": "12345",
            "username": "testuser"
        }

        # If user or application with the given information does not exist, we should get 404
        self.assertOk(self.client.post(reverse("api:fetch-token"), data), 404)

        app = Extension.objects.create(name="Test App", developer="Lens and Lights",
                                       description="An app used for testing", api_key="ABCDEFG", enabled=True)

        # If application exists, but user has not allowed full permissions, we should get 403
        self.assertOk(self.client.post(reverse("api:fetch-token"), data), 403)

        # Simulate trusting an application
        self.user.connected_services.add(app)

        # If codes do not match we should see invalid code error and attempts count should be decreased
        self.assertEqual(self.client.post(reverse("api:fetch-token"), data).data['detail'],
                         "Invalid verification code. {} attempts remaining.".format(settings.TFV_ATTEMPTS - 1))

        data["code"] = token_request.code

        # If too much time has elapsed, request should have expired
        request = models.TokenRequest.objects.get(user=self.user)
        request.timestamp = timezone.now() + timezone.timedelta(hours=-1)
        request.save()

        self.assertOk(self.client.post(reverse("api:fetch-token"), data), 410)

        token_request.save()

        # Otherwise everything should work out just fine
        resp = self.client.post(reverse("api:fetch-token"), data).data
        self.assertIsNotNone(resp['token'])

        # If a code has already been used we should get a 410 error
        self.assertOk(self.client.post(reverse("api:fetch-token"), data), 410)

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
        building = Building.objects.create(name="Campus Center", shortname="CC")
        location = Location.objects.create(name="CC Office", building=building)
        location2 = Location.objects.create(name="Mail Room", building=building)
        hour1 = OfficeHour.objects.create(officer=self.user, day=1, location=location, hour_start=start_time.time(),
                                          hour_end=end_time.time())
        hour2 = OfficeHour.objects.create(officer=user2, day=3, location=location2, hour_start=start_time.time(),
                                          hour_end=end_time.time())

        self.assertEqual(self.client.get("/api/v1/office-hours").content.decode('utf-8'),
                         '[{"officer":"President","day":1,"location":"CC Office","hour_start":"' +
                         str(start_time.time()) + '","hour_end":"' + str(end_time.time()) +
                         '"},{"officer":"Vice President","day":3,"location":"Mail Room","hour_start":"' +
                         str(start_time.time()) + '","hour_end":"' + str(end_time.time()) + '"}]')

        # Test that we can get office hours for a specific officer
        self.assertEqual(self.client.get("/api/v1/office-hours?officer=president").content.decode('utf-8'),
                         '[{"officer":"President","day":1,"location":"CC Office","hour_start":"' +
                         str(start_time.time()) + '","hour_end":"' + str(end_time.time()) + '"}]')

        # Test that we can filter office hours by the day
        self.assertEqual(self.client.get("/api/v1/office-hours?day=3").content.decode('utf-8'),
                         '[{"officer":"Vice President","day":3,"location":"Mail Room","hour_start":"' +
                         str(start_time.time()) + '","hour_end":"' + str(end_time.time()) + '"}]')

        # Test that we can filter office hours by location
        self.assertEqual(self.client.get("/api/v1/office-hours?location=office").content.decode('utf-8'),
                         '[{"officer":"President","day":1,"location":"CC Office","hour_start":"' +
                         str(start_time.time()) + '","hour_end":"' + str(end_time.time()) + '"}]')

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

        OfficeHour.objects.create(officer=self.user, day=4, location=location, hour_start=start_time.time(),
                                  hour_end=end_time.time())

        self.assertEqual(self.client.get("/api/v1/office-hours?start=13:30:00").content.decode('utf-8'),
                         '[{"officer":"President","day":4,"location":"CC Office","hour_start":"13:30:00",'
                         '"hour_end":"15:30:00"}]')

        # Test that we can get office hours that end at a certain time (exact match)
        self.assertEqual(self.client.get("/api/v1/office-hours?end=15:30:00").content.decode('utf-8'),
                         '[{"officer":"President","day":4,"location":"CC Office","hour_start":"13:30:00",'
                         '"hour_end":"15:30:00"}]')

        # Test that if both start and end times are provided the result contains entries that overlap with those times
        self.assertEqual(self.client.get("/api/v1/office-hours?start=13:00:00&end=14:00:00").content.decode('utf-8'),
                         '[{"officer":"President","day":4,"location":"CC Office","hour_start":"13:30:00",'
                         '"hour_end":"15:30:00"}]')

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

    def test_events_endpoint(self):
        models.Endpoint.objects.create(name="Events", url="events", description="Get your event info here",
                                       example="name=Test Event", response="[]")

        # Test that we get 204 response if no events can be found matching query
        self.assertOk(self.client.get("/api/v1/events"), 204)

        building = Building.objects.create(name="Campus Center", shortname="CC")
        location1 = Location.objects.create(name="CC Office", building=building)
        location2 = Location.objects.create(name="Dunkin Donuts", building=building)
        now = timezone.now().replace(microsecond=0)
        time_past = timezone.now() + timezone.timedelta(hours=-1)
        time_past = time_past.replace(microsecond=0)
        time_future = timezone.now() + timezone.timedelta(hours=1)
        time_future = time_future.replace(microsecond=0)

        Event2019Factory.create(event_name="Test Event", location=location1, datetime_start=now,
                                datetime_end=time_future, description="An event", approved=True)
        Event2019Factory.create(event_name="Another Event", location=location2, datetime_start=time_past,
                                datetime_end=time_future, approved=True)
        Event2019Factory.create(event_name="Past Event", location=location1, datetime_start=time_past,
                                datetime_end=time_past, approved=True)

        now_str = timezone.localtime(now).strftime("%Y-%m-%dT%H:%M:%S%z")
        time_past_str = timezone.localtime(time_past).strftime("%Y-%m-%dT%H:%M:%S%z")
        time_future_str = timezone.localtime(time_future).strftime("%Y-%m-%dT%H:%M:%S%z")

        # Default response should be just upcoming events that are not sensitive, cancelled, or designated as a test
        default_response = '[{"id":1,"event_name":"Test Event","description":"An event","location":"CC Office",' \
                           '"datetime_start":"' + now_str + '","datetime_end":"' + time_future_str + '"},' \
                           '{"id":2,"event_name":"Another Event","description":null,"location":"Dunkin Donuts",' \
                           '"datetime_start":"' + time_past_str + '","datetime_end":"' + time_future_str + '"}]'

        self.assertEqual(self.client.get("/api/v1/events").content.decode('utf-8'), default_response)

        # Test filter by name
        name_response = '[{"id":1,"event_name":"Test Event","description":"An event","location":"CC Office",' \
                        '"datetime_start":"' + now_str + '","datetime_end":"' + time_future_str + '"}]'

        self.assertEqual(self.client.get("/api/v1/events", {"name": "test"}).content.decode('utf-8'), name_response)

        # Test filter by location
        location_response = '[{"id":2,"event_name":"Another Event","description":null,"location":"Dunkin Donuts",' \
                            '"datetime_start":"' + time_past_str + '","datetime_end":"' + time_future_str + '"}]'

        self.assertEqual(self.client.get("/api/v1/events", {"location": "dunkin"}).content.decode('utf-8'),
                         location_response)

        # Test filter by start or end time (match)
        start = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        end = time_future.strftime("%Y-%m-%dT%H:%M:%SZ")

        self.assertEqual(self.client.get("/api/v1/events", {"start": start}).content.decode('utf-8'), name_response)
        self.assertEqual(self.client.get("/api/v1/events", {"end": end}).content.decode('utf-8'), default_response)

        # Test both start and end time
        time_response = '[{"id":2,"event_name":"Another Event","description":null,"location":"Dunkin Donuts",' \
                        '"datetime_start":"' + time_past_str + '","datetime_end":"' + time_future_str + '"},' \
                        '{"id":3,"event_name":"Past Event","description":null,"location":"CC Office",' \
                        '"datetime_start":"' + time_past_str + '","datetime_end":"' + time_past_str + '"}]'

        self.assertEqual(self.client.get("/api/v1/events", {"start": str(time_past + timezone.timedelta(hours=-1)),
                                                            "end": str(now + timezone.timedelta(minutes=-1))}
                                         ).content.decode('utf-8'), time_response)
        self.assertEqual(self.client.get("/api/v1/events",
                                         {"start": str(now), "end": str(time_future + timezone.timedelta(hours=1))}
                                         ).content.decode('utf-8'), default_response)

    def test_crew_endpoint(self):
        models.Endpoint.objects.create(name="Crew Checkin", url="crew/checkin", description="Checkin to events",
                                       example="user=12345&event=1", response="[]")
        models.Endpoint.objects.create(name="Crew Checkout", url="crew/checkout", description="Checkout from events",
                                       example="user=12345&event=1", response="[]")

        # Get token for authentication
        token, created = Token.objects.get_or_create(user=self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

        # Test that only POST requests are permitted
        self.assertOk(client.get("/api/v1/crew/checkin"), 405)
        self.assertOk(client.get("/api/v1/crew/checkout"), 405)

        # Test that student ID is required (the next several tests will be the same for both actions)
        self.assertOk(client.post("/api/v1/crew/checkin", {'event': 1}), 400)

        # Test that failure to provide event id results in 400
        self.assertOk(client.post("/api/v1/crew/checkin", {'id': 12345}), 400)

        # Return 404 if user cannot be found with student ID
        self.assertOk(client.post("/api/v1/crew/checkin", {'id': 12345, 'event': 1}), 404)

        self.user.student_id = 12345
        self.user.save()

        # Return error if event cannot be found or is otherwise not eligible for checkin / checkout
        self.assertOk(client.post("/api/v1/crew/checkin", {'id': 12345, 'event': 1}), 404)

        event = Event2019Factory.create(event_name="Test Event")
        event.datetime_end = timezone.now() + timezone.timedelta(hours=1)
        event.max_crew = 1
        event2 = Event2019Factory.create(event_name="Another Event")
        event2.datetime_end = timezone.now() + timezone.timedelta(hours=1)
        event2.approved = True
        event2.max_crew = 1
        event.save()
        event2.save()
        CCInstanceFactory.create(crew_chief=self.user, event=event, setup_start=timezone.now())
        CCInstanceFactory.create(crew_chief=self.user, event=event2, setup_start=timezone.now())

        self.assertOk(client.post("/api/v1/crew/checkin", {'id': 12345, 'event': 1}), 403)

        event.approved = True
        event.save()

        second_user = UserFactory.create(password="9876")
        other_checkin = CrewAttendanceRecord.objects.create(event=event, user=second_user, active=True)

        # Should display an error if we have reached maximum crew
        self.assertOk(client.post("/api/v1/crew/checkin", {'id': 12345, 'event': 1}), 403)

        other_checkin.delete()

        # Check response on successful checkin
        resp = client.post("/api/v1/crew/checkin", {'id': 12345, 'event': 1})
        self.assertOk(resp, 201)

        self.assertTrue(CrewAttendanceRecord.objects.filter(user=self.user).exists())

        # Return 409 if checkin record already exists for the user (even if it's for another event)
        self.assertOk(client.post("/api/v1/crew/checkin", {'id': 12345, 'event': 2}), 409)

        # Return 404 if checkin record could not be found during checkout
        self.assertOk(client.post("/api/v1/crew/checkout", {'id': 12345, 'event': 2}), 404)

        # Test with checkout time included
        custom_datetime = timezone.now() + timezone.timedelta(days=-1)
        self.assertOk(client.post("/api/v1/crew/checkout",
                                  {'id': 12345, 'event': 1, 'checkout': custom_datetime}), 201)

        self.assertEqual(CrewAttendanceRecord.objects.get(user=self.user).checkout, custom_datetime)

        # Test with Checkin time included
        self.assertOk(client.post("/api/v1/crew/checkin",
                                  {'id': 12345, 'event': 1, 'checkin': custom_datetime}), 201)

        self.assertEqual(CrewAttendanceRecord.objects.get(user=self.user, active=True).checkin, custom_datetime)

    def test_sitemap_endpoint(self):
        models.Endpoint.objects.create(name="Sitemap", url="sitemap", example="category=Events", response="[]",
                                       description="Grab redirects and links to custom pages for sitemap")

        # Check that we get 204 if there are no redirects or page links to return
        self.assertOk(self.client.get('/api/v1/sitemap'), 204)

        request = RequestFactory()
        main_site = get_current_site(request)
        ResizedRedirect.objects.create(site=main_site, old_path='/test/', new_path=reverse('home'))
        ResizedRedirect.objects.create(name='Welcome Page', site=main_site, old_path='/test2/',
                                       new_path=reverse('index'), sitemap=True)

        Page.objects.create(title='Test Page', slug='test-page', body='<h1>Hello world</h1>')
        Page.objects.create(title='Another Test Page', slug='another-test-page', body='<h1>Another page</h1>',
                            sitemap=True, sitemap_category='Test Pages')

        # Test default response: all public redirects and pages
        default_response = '[{"title":"Another Test Page","path":"another-test-page","category":"Test Pages"},' \
                           '{"title":"Welcome Page","path":"test2/","category":"Redirects"}]'

        self.assertEqual(self.client.get('/api/v1/sitemap').content.decode('utf-8'), default_response)

        # Test response with pages only
        pages_only = '[{"title":"Another Test Page","path":"another-test-page","category":"Test Pages"}]'

        self.assertEqual(self.client.get('/api/v1/sitemap', {'type': 'page'}).content.decode('utf-8'), pages_only)

        # Test response with redirects only
        redirects_only = '[{"title":"Welcome Page","path":"test2/","category":"Redirects"}]'

        self.assertEqual(self.client.get('/api/v1/sitemap', {'type': 'redirect'}).content.decode('utf-8'),
                         redirects_only)

        # Test filter by category
        self.assertOk(self.client.get('/api/v1/sitemap', {'category': 'Events'}), 204)
        self.assertEqual(self.client.get('/api/v1/sitemap', {'category': 'test'}).content.decode('utf-8'), pages_only)

    def test_docs(self):
        # Create a couple endpoints to include in the docs
        models.Endpoint.objects.create(name="Endpoint 1", url="first", description="First endpoint",
                                       example="id=example", response="[]")
        models.Endpoint.objects.create(name="Endpoint 2", url="second", description="Second endpoint",
                                       example="id=example", response="[]")

        self.assertOk(self.client.get(reverse("api:documentation")))

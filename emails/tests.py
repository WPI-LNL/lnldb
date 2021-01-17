# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from data.tests.util import ViewTestCase
from django.urls.base import reverse
from django.core.management import call_command
from django.contrib.auth.models import Permission, Group
from django.utils import timezone
from . import generators
from events.models import Category, Service, ServiceInstance, Building, Location
from events.tests.generators import Event2019Factory
import logging


logging.disable(logging.WARNING)


class EmailTestCase(ViewTestCase):
    def setup(self):
        self.event1 = Event2019Factory.create(event_name="All set")
        self.event2 = Event2019Factory.create(event_name="Need Chiefs")
        self.event2.datetime_setup_complete = timezone.now() + timezone.timedelta(days=1)
        self.event2.datetime_start = timezone.now() + timezone.timedelta(days=2)
        self.event2.datetime_end = timezone.now() + timezone.timedelta(days=3)
        self.event2.approved = True
        self.event2.save()

        self.lighting = Category.objects.create(name="Lighting")
        self.sound = Category.objects.create(name="Sound")
        self.l1 = Service.objects.create(shortname="L1", longname="Basic Lighting", base_cost=10.00, addtl_cost=5.00,
                                         category=self.lighting)
        self.s1 = Service.objects.create(shortname="S1", longname="Basic Sound", base_cost=10.00, addtl_cost=5.00,
                                         category=self.sound)

        self.service1 = ServiceInstance.objects.create(service=self.l1, event=self.event1)
        self.service2 = ServiceInstance.objects.create(service=self.s1, event=self.event2)

    def test_dispatch_console(self):
        # By default, a regular user should not have permission
        self.assertOk(self.client.get(reverse("emails:dispatch")), 403)

        permission = Permission.objects.get(codename="send")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("emails:dispatch")))

    def test_poke_for_cc(self):
        # By default, user should not have permission
        self.assertOk(self.client.get(reverse("emails:poke-cc")), 403)

        permission = Permission.objects.get(codename="edit_event_hours")
        self.user.user_permissions.add(permission)

        # Check that if there are no events in need of a crew chief, it results in a 404
        self.assertOk(self.client.get(reverse("emails:poke-cc")), 404)

        self.setup()

        self.assertOk(self.client.get(reverse("emails:poke-cc")))

        # Check that preview can be displayed properly
        valid_data = {
            "events": [str(self.service2.pk)],
            "message": "CCs are needed for the events below:",
            "email_to": "lnl-active@wpi.edu",
            "save": "Preview"
        }

        self.assertOk(self.client.post(reverse("emails:poke-cc"), valid_data))

        # Check that invalid data reloads form
        invalid_data = valid_data
        invalid_data['events'] = []

        self.assertOk(self.client.post(reverse("emails:poke-cc"), invalid_data))

        # Check that form can be submitted successfully
        valid_data['events'] = [str(self.service2.pk)]
        valid_data['save'] = "Send"

        self.assertRedirects(self.client.post(reverse("emails:poke-cc"), valid_data), reverse("home"))

    def test_poke_cc_message_generator(self):
        self.setup()

        # Configure some additional info
        self.event1.datetime_setup_complete = timezone.now() + timezone.timedelta(days=1)
        self.event1.datetime_start = timezone.now() + timezone.timedelta(days=2)
        self.event1.datetime_end = timezone.now() + timezone.timedelta(days=2)

        building = Building.objects.create(name="Test Building", shortname="Test")
        location = Location.objects.create(name="Test Location", building=building)
        self.event1.location = location
        self.event2.location = location
        self.event1.description = "An event that is pretty much all set"
        self.event2.description = "A test event that we need CCs for"
        self.event1.save()
        self.event2.save()

        # Format the dates for output below
        event1_setup = timezone.localtime(self.event1.datetime_setup_complete).strftime("%A (%-m/%-d) %-I:%M %p")
        event1_start = timezone.localtime(self.event1.datetime_start).strftime("%A (%-m/%-d) %-I:%M %p - ")
        event1_end = timezone.localtime(self.event1.datetime_end).strftime("%-I:%M %p")

        event2_setup = timezone.localtime(self.event2.datetime_setup_complete).strftime("%A (%-m/%-d) %-I:%M %p")
        event2_start = timezone.localtime(self.event2.datetime_start).strftime("%A (%-m/%-d) %-I:%M %p to ")
        event2_end = timezone.localtime(self.event2.datetime_end).strftime("%A (%-m/%-d) %-I:%M %p")

        # Test with 1 service passed in
        expected = "Some example message<hr><strong>CC's needed:</strong> Lighting\n<strong>Services:</strong> " \
                   "Basic Lighting\n<strong>What:</strong> <a href='https://lnl.wpi.edu/db/events/view/1/'>" \
                   "All set</a>\n<strong>When:</strong> %s\n<strong>Setup by:</strong> %s\n<strong>Where:</strong> " \
                   "Test Location\n<strong>Description:</strong> An event that is pretty much all set\n\n" % \
                   (event1_start + event1_end, event1_setup)

        content = generators.generate_poke_cc_email_content([str(self.service1.pk)], "Some example message")

        self.assertEqual(content, expected)

        # Test with 2 services passed in
        expected = "Some example message<hr><strong>CC's needed:</strong> Lighting\n<strong>Services:</strong> " \
                   "Basic Lighting\n<strong>What:</strong> <a href='https://lnl.wpi.edu/db/events/view/1/'>" \
                   "All set</a>\n<strong>When:</strong> %s\n<strong>Setup by:</strong> %s\n<strong>Where:</strong> " \
                   "Test Location\n<strong>Description:</strong> An event that is pretty much all set\n\n" \
                   "<strong>CC's needed:</strong> Sound\n<strong>Services:</strong> Basic Sound\n" \
                   "<strong>What:</strong> <a href='https://lnl.wpi.edu/db/events/view/2/'>Need Chiefs</a>\n" \
                   "<strong>When:</strong> %s\n<strong>Setup by:</strong> %s\n<strong>Where:</strong> Test Location\n" \
                   "<strong>Description:</strong> A test event that we need CCs for\n\n" % \
                   (event1_start + event1_end, event1_setup, event2_start + event2_end, event2_setup)

        content = generators.generate_poke_cc_email_content([str(self.service1.pk), str(self.service2.pk)],
                                                            "Some example message")

        self.assertEqual(content, expected)

    def test_management_command(self):
        # Test send_start_end command
        args = []
        opts = {}
        call_command('send_start_end', *args, **opts)

    def test_send_if_necessary(self):
        self.setup()

        # Setup event
        self.event1.datetime_end = timezone.now() + timezone.timedelta(days=-1)
        self.event1.approved = True
        self.event1.send_survey = True
        self.event1.contact = self.user
        self.event1.save()

        generators.send_survey_if_necessary(self.event1)
        self.assertTrue(self.event1.survey_sent)

        # Check that it returns nothing if survey already sent
        self.assertIsNone(generators.send_survey_if_necessary(self.event1))

    def test_service_announcement(self):
        data = {
            "subject": "Upcoming Maintenance",
            "message": "A test message",
            "email_to": "lnl@wpi.edu",
            "save": "Send"
        }

        # By default should not have permission to access this tool
        self.assertOk(self.client.get(reverse("emails:service-announcement")), 403)

        permission = Permission.objects.get(codename="send_mtg_notice")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("emails:service-announcement")))

        # Check that announcement is sent successfully
        self.assertRedirects(self.client.post(reverse("emails:service-announcement"), data), reverse("home"))

        # Check that we get form back on invalid data
        data['subject'] = ""
        self.assertOk(self.client.post(reverse("emails:service-announcement"), data))

    def test_sms(self):
        data = {
            "message": "Hello world",
            "user": self.user.pk,
            "save": "Send"
        }

        # By default should not have permission to access this tool
        self.assertOk(self.client.get(reverse("emails:sms")), 403)

        permission = Permission.objects.get(codename="send")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("emails:sms")))

        # Test that without number or carrier we get opted-out page
        self.assertContains(self.client.post(reverse("emails:sms"), data), "Error 403")

        self.user.phone = "1234567890"
        self.user.carrier = "txt.att.net"
        self.user.save()

        # Test with valid address
        self.assertRedirects(self.client.post(reverse("emails:sms"), data), reverse("home"))

    def test_active_sms(self):
        data = {
            "message": "Some test message",
            "save": "Send"
        }

        # By default should not have permission to access this tool
        self.assertOk(self.client.get(reverse("emails:sms-active")), 403)

        permission = Permission.objects.get(codename="send")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("emails:sms-active")))

        # Display 204 error when no active users are opted-in
        self.assertContains(self.client.post(reverse("emails:sms-active"), data), "Error 204")

        # Test response with fully configured users
        Group.objects.create(name="Active").user_set.add(self.user)
        self.user.phone = "1234567890"
        self.user.carrier = "txt.att.net"
        self.user.save()

        self.assertRedirects(self.client.post(reverse("emails:sms-active"), data), reverse("home"))

    def test_event_start_end_emails(self):
        self.setup()

        self.event1.datetime_start = timezone.now()
        self.event1.save()

        # Try with start email (should return nothing)
        self.assertIsNone(generators.generate_event_start_end_emails())

        self.event1.datetime_start = timezone.now() + timezone.timedelta(hours=-1)
        self.event1.datetime_end = timezone.now()
        self.event1.save()

        # Try with strike email
        self.assertIsNone(generators.generate_event_start_end_emails())

import logging
import json
from django.shortcuts import reverse
from django.utils import timezone
from .util import ViewTestCase
from events.tests.generators import UserFactory, LocationFactory, OrgFactory, ServiceFactory, CategoryFactory, \
    Event2019Factory
from events.models import Extra, ServiceInstance


logging.disable(logging.WARNING)


class DataViewsTestCase(ViewTestCase):
    def test_maintenance(self):
        self.assertOk(self.client.get(reverse("maintenance")))

    def test_search(self):
        self.assertOk(self.client.get(reverse("search")))

        UserFactory.create(password="123", first_name="Ellen")

        self.assertContains(self.client.get(reverse("search"), {'q': 'ell'}), "Ellen")


#class WorkorderWizardEndpointTestCase(ViewTestCase):
#    def setup(self):
#        self.location = LocationFactory.create(name="Test Location", show_in_wo_form=True)
#        self.org = OrgFactory.create(name="Test Org", shortname="Test", exec_email="test@test.com", phone="1234567890")
#
#    def test_load(self):
#        expected = {
#            'locations': [],
#            'orgs': [],
#            'user': {
#                'name': self.user.get_full_name(),
#                'email': self.user.email,
#                'phone': self.user.phone,
#                'address': None
#            }
#        }
#
#        self.assertEqual(self.client.get(reverse('wizard-load')).content, json.dumps(expected).encode('utf-8'))
#
#        self.setup()
#
#        # Repeat with locations and orgs
#        expected = {
#            'locations': [{'id': self.location.pk, 'name': 'Test Location', 'building': ''}],
#            'orgs': [
#                {
#                    'id': self.org.pk,
#                    'name': 'Test Org',
#                    'shortname': 'Test',
#                    'owner': False,
#                    'member': False,
#                    'delinquent': False
#                }
#            ],
#            'user': {
#                'name': self.user.get_full_name(),
#                'email': self.user.email,
#                'phone': self.user.phone,
#                'address': None
#            }
#        }
#
#        self.assertEqual(self.client.get(reverse('wizard-load')).content, json.dumps(expected).encode('utf-8'))
#
#        # Full example when user has view_org permissions
#        self.org.user_in_charge = self.user
#        self.org.save()
#
#        expected = {
#            'locations': [{'id': self.location.pk, 'name': 'Test Location', 'building': ''}],
#            'orgs': [
#                {
#                    'id': self.org.pk,
#                    'name': 'Test Org',
#                    'shortname': 'Test',
#                    'owner': True,
#                    'member': False,
#                    'delinquent': False,
#                    'email': "test@test.com",
#                    'phone': "1234567890",
#                    'address': None
#                }
#            ],
#            'user': {
#                'name': self.user.get_full_name(),
#                'email': self.user.email,
#                'phone': self.user.phone,
#                'address': None
#            }
#        }
#
#        self.assertEqual(self.client.get(reverse('wizard-load')).content, json.dumps(expected).encode('utf-8'))
#
#    def test_submit(self):
#        self.setup()
#
#        # Test GET request not allowed
#        self.assertOk(self.client.get(reverse("wizard-submit")), 405)
#
#        # Setup event data
#        service1 = ServiceFactory.create(enabled_event2019=True)
#        service2 = ServiceFactory.create(longname="Sound", shortname="S1", enabled_event2019=True)
#        extra = Extra.objects.create(name="Flown Projector", cost=12.00, desc="Projector flying high in the sky",
#                                     category=CategoryFactory.create())
#        extra.services.add(service1)
#
#        # Test missing required fields (in this case setup_complete is missing)
#        test_data = {
#            "org": self.org.pk,
#            "event_name": "Test Event",
#            "location": self.location.pk,
#            "start": timezone.now().strftime('%Y-%m-%dT%H:%M:%S.%f%z'),
#            "end": timezone.now().strftime('%Y-%m-%dT%H:%M:%S.%f%z'),
#            "services": []
#        }
#
#        self.assertOk(
#            self.client.post(reverse("wizard-submit"), json.dumps(test_data), content_type="application/json"), 422
#        )
#
#        # Test with full data
#        test_data = {
#            "org": self.org.pk,
#            "event_name": "Test Event",
#            "description": "This is a test event",
#            "location": self.location.pk,
#            "start": timezone.now().strftime('%Y-%m-%dT%H:%M:%S.%f%z'),
#            "end": timezone.now().strftime('%Y-%m-%dT%H:%M:%S.%f%z'),
#            "setup_complete": timezone.now().strftime('%Y-%m-%dT%H:%M:%S.%f%z'),
#            "services": [{'id': 'L1', 'detail': 'I need as many lights as possible'}, {'id': 'S1'}],
#            "extras": [{'id': 'Flown Projector', 'quantity': 1}]
#        }
#        resp = self.client.post(reverse("wizard-submit"), json.dumps(test_data), content_type="application/json")
#        self.assertOk(resp)
#        self.assertEqual(resp.content, json.dumps({"event_url": reverse("events:detail", args=[1])}).encode('utf-8'))
#
#        # Show in workorder form must be set to true on the location
#        self.location.show_in_wo_form = False
#        self.location.save()
#
#        self.assertOk(
#            self.client.post(reverse("wizard-submit"), json.dumps(test_data), content_type="application/json"), 422
#        )
#
#        self.location.show_in_wo_form = True
#        self.location.save()
#
#        # Services must be enabled for 2019+ events
#        service2.enabled_event2019 = False
#        service2.save()
#
#        self.assertOk(
#            self.client.post(reverse("wizard-submit"), json.dumps(test_data), content_type="application/json"), 422
#        )
#
#        service2.enabled_event2019 = True
#        service2.save()
#
#        # Disappeared extras should not be available
#        extra.disappear = True
#        extra.save()
#
#        self.assertOk(
#            self.client.post(reverse("wizard-submit"), json.dumps(test_data), content_type="application/json"), 422
#        )
#
#    def test_find_previous(self):
#        self.setup()
#
#        # Test GET request not allowed
#        self.assertOk(self.client.get(reverse("wizard-findprevious")), 405)
#
#        # Test missing required fields (in this case location is missing)
#        test_data = {
#            "org": self.org.pk,
#            "event_name": "Test Event #2",
#            "start": timezone.now().strftime('%Y-%m-%dT%H:%M:%S.%f%z'),
#            "end": timezone.now().strftime('%Y-%m-%dT%H:%M:%S.%f%z'),
#            "setup_complete": timezone.now().strftime('%Y-%m-%dT%H:%M:%S.%f%z')
#        }
#
#        self.assertOk(
#            self.client.post(reverse("wizard-findprevious"), json.dumps(test_data), content_type="application/json"),
#            422
#        )
#
#        test_data["location"] = self.location.pk
#
#        # Test no match
#        self.assertOk(
#            self.client.post(reverse("wizard-findprevious"), json.dumps(test_data), content_type="application/json"),
#            204
#        )
#
#        # Test match but no permission to access unapproved events
#        event = Event2019Factory.create(event_name="Test Event", location=self.location,
#                                        datetime_start=timezone.now() - timezone.timedelta(days=1))
#        event.org.add(self.org)
#        service = ServiceFactory.create(shortname="S4", enabled_event2019=True)
#        ServiceInstance.objects.create(service=service, event=event, detail="Tons of wub")
#
#        self.assertOk(
#            self.client.post(reverse("wizard-findprevious"), json.dumps(test_data), content_type="application/json"),
#            204
#        )
#
#        # Test match with valid permissions
#        self.org.user_in_charge = self.user
#        self.org.save()
#
#        expected_response = {
#            "event_name": "Test Event",
#            "location": self.location.pk,
#            "start": str(event.datetime_start),
#            "services": [{"id": service.shortname, "detail": "Tons of wub"}]
#        }
#
#        resp = self.client.post(reverse("wizard-findprevious"), json.dumps(test_data), content_type="application/json")
#        self.assertOk(resp)
#        self.assertEqual(resp.content, json.dumps(expected_response).encode('utf-8'))

from django.core.urlresolvers import reverse
from django.test import TestCase
from django.utils import timezone

from events.tests.generators import EventFactory, Event2019Factory, UserFactory
from events.models import ExtraInstance, Extra, Category, MultiBilling, Organization, Lighting, ServiceInstance
from .. import views


class PdfViewTest(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.e3 = Event2019Factory.create(event_name="2019 Test Event")
        self.e4 = Event2019Factory.create(event_name="Another 2019 Test Event")
        self.user = UserFactory.create(password='123')
        self.client.login(username=self.user.username, password='123')

        self.category = Category.objects.create(name="Lighting")
        self.category.save()
        sound_cat = Category.objects.create(name="Sound")
        sound_cat.save()

        lighting = Lighting.objects.create(shortname="L1", longname="Basic Lighting", base_cost=10.00,
                                           addtl_cost=5.00, category=self.category)
        lighting.save()
        self.lighting = ServiceInstance.objects.create(service=lighting, event=self.e3)
        self.lighting.save()
        self.extra = Extra.objects.create(name="Test Extra", cost=10.00, desc="A test extra", category=self.category)
        self.extra.save()
        self.extra_instance = ExtraInstance.objects.create(event=self.e4, extra=self.extra, quant=1)
        self.extra_instance.save()

        self.organization = Organization.objects.create(name="Test org", phone="1234567890", user_in_charge=self.user)
        self.organization.save()
        self.e4.org.add(self.organization)
        self.multibilling = MultiBilling.objects.create(date_billed=timezone.datetime.today(), amount=20.00,
                                                        org=self.organization)
        self.multibilling.save()
        self.multibilling.events.add(self.e2)
        self.multibilling.events.add(self.e4)

    def test_get_category_data(self):
        event_data = {
            'event': self.e,
            'is_event2019': False
        }
        response = views.get_category_data(self.e)
        self.assertEqual(response, event_data)

        # New events
        event_data = {
            'event': self.e3,
            'is_event2019': True,
            'categories_data': [
                {
                    'category': self.category,
                    'serviceinstances_data': [{'attachment': False, 'serviceinstance': self.lighting}]
                }
            ]
        }
        response = views.get_category_data(self.e3)
        self.assertEqual(response, event_data)

    def test_get_multibill_data(self):
        response = views.get_multibill_data(self.multibilling)
        self.assertEqual(response['billing_org'], self.organization)
        self.assertEqual(list(response['events']), [self.e2, self.e4])
        self.assertEqual(response['multibilling'], self.multibilling)
        self.assertEqual(list(response['orgs']), [self.organization])
        self.assertEqual(float(response['total_cost']), 10.00)

    def test_get_extras(self):
        event_data = {
            'event': self.e,
            'extras': {}
        }
        response = views.get_extras(self.e)
        self.assertEqual(response, event_data)

        response = views.get_extras(self.e4)
        self.assertEqual(list(response['extras'][self.category]), [self.extra_instance])

    def test_event_pdf(self):
        response = self.client.get(reverse('events:pdf', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Test with new "2019" Events
        response = self.client.get(reverse('events:pdf', args=[self.e3.pk]))
        self.assertEqual(response.status_code, 200)

        # If passed "raw" parameter, display as HTML
        html_response = self.client.get(reverse('events:pdf', args=[self.e.pk]), {'raw': True})
        self.assertEqual(html_response.status_code, 200)
        self.assertContains(html_response, "WPI Lens and Lights Workorder")

    def test_currency(self):
        self.assertEqual(views.currency(1), "$1.00")
        self.assertEqual(views.currency(25.5), "$25.50")
        self.assertEqual(views.currency(0.758), "$0.76")

    def test_pdf_bill(self):
        response = self.client.get(reverse("events:bills:pdf", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)
        self.e2.reviewed = True
        self.e2.save()
        html_response = self.client.get(reverse("events:bills:pdf", args=[self.e2.pk]), {'raw': True})
        self.assertEqual(html_response.status_code, 200)
        self.assertContains(html_response, "INVOICE")

        # Test with new "2019" event (with extras)
        html_response = self.client.get(reverse("events:bills:pdf", args=[self.e4.pk]), {'raw': True})
        self.assertEqual(html_response.status_code, 200)
        self.assertContains(html_response, "QUOTE")

    def test_bill_pdf_standalone(self):
        # Test that a file is successfully returned
        self.assertIsNotNone(views.generate_event_bill_pdf_standalone(event=self.e4))

    def test_pdf_multibill(self):
        response = self.client.get(reverse('events:multibillings:pdf', args=[self.multibilling.pk]))
        self.assertEqual(response.status_code, 200)

    def test_multibill_pdf_standalone(self):
        # Test that a file is successfully returned
        self.assertIsNotNone(views.generate_multibill_pdf_standalone(multibilling=self.multibilling))

    def test_pdf_multi(self):
        response = self.client.get(reverse('events:pdf-multi', args=["%s,%s" % (self.e.pk, self.e2.pk)]))
        self.assertEqual(response.status_code, 200)

        # Test with no ids
        response = self.client.get(reverse('events:pdf-multi'))
        self.assertEqual(response.content, "Should probably give some ids to return pdfs for.")

        # Test with "2019" event
        response = self.client.get(reverse('events:pdf-multi', args=["%s,%s" % (self.e3.pk, self.e4.pk)]))
        self.assertEqual(response.status_code, 200)

    def test_bill_pdf_multi(self):
        html_response = self.client.get(reverse('events:bill-pdf-multi', args=["%s,%s" % (self.e.pk, self.e2.pk)]),
                                        {'raw': True})
        self.assertEqual(html_response.status_code, 200)
        self.assertContains(html_response, "QUOTE")

        # Test with no ids
        response = self.client.get(reverse('events:bill-pdf-multi'))
        self.assertEqual(response.content, "Should probably give some ids to return pdfs for.")

        # Test with "2019" event
        response = self.client.get(reverse('events:bill-pdf-multi', args=["%s,%s" % (self.e3.pk, self.e4.pk)]))
        self.assertEqual(response.status_code, 200)

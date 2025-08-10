import datetime

from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from pypdf import PdfReader
from io import BytesIO

from events.tests.generators import EventFactory, Event2019Factory, UserFactory, ServiceFactory
from events.models import ExtraInstance, Extra, Category, MultiBilling, Organization, Lighting, ServiceInstance, \
    Pricelist, Discount, Fee, DiscountPrice, FeePrice, Rental, Quote
from .. import views


class PdfViewTest(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="First Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.e3 = Event2019Factory.create(event_name="First 2019 Test Event")
        self.e4 = Event2019Factory.create(event_name="Another 2019 Test Event")
        self.e5 = Event2019Factory.create(event_name="New Discounts Test")
        self.user = UserFactory.create(password='123')
        self.client.login(username=self.user.username, password='123')

        self.category = Category.objects.create(name="Lighting")
        lighting = Lighting.objects.create(shortname="L1", longname="Basic Lighting", base_cost=10.00,
                                           addtl_cost=5.00, category=self.category)
        self.lighting = ServiceInstance.objects.create(service=lighting, event=self.e3)
        self.extra = Extra.objects.create(name="Test Extra", cost=10.00, desc="A test extra", category=self.category)
        self.extra_instance = ExtraInstance.objects.create(event=self.e4, extra=self.extra, quant=1)

        self.organization = Organization.objects.create(name="Test org", phone="1234567890", user_in_charge=self.user)
        self.e4.org.add(self.organization)
        self.multibilling = MultiBilling.objects.create(date_billed=timezone.datetime.today(), amount=20.00,
                                                        org=self.organization)
        self.multibilling.events.add(self.e2)
        self.multibilling.events.add(self.e4)
        self.multibilling.events.add(self.e5)

        self.pricelist = Pricelist.objects.create(name="Test Pricelist")
        self.e5.pricelist = self.pricelist
        self.e5.uses_new_discounts = True
        self.e5.save()

        lighting_service = ServiceFactory(category=self.category, longname="First Lighting Service")
        ServiceInstance.objects.create(service=lighting_service, event=self.e5)
        lighting_service_2 = ServiceFactory(category=self.category, longname="Second Lighting Service")
        ServiceInstance.objects.create(service=lighting_service_2, event=self.e5)
        ExtraInstance.objects.create(extra=self.extra, event=self.e5, quant=3)

        sound = Category.objects.create(name="Sound")
        sound_service = ServiceFactory(category=sound, longname="Sound Service")
        ServiceInstance.objects.create(service=sound_service, event=self.e5)
        sound_extra = Extra.objects.create(name="Test Sound Extra", cost=99.02, desc="A test sound extra", category=sound)
        ExtraInstance.objects.create(extra=sound_extra, event=self.e5, quant=1)

        rigging = Category.objects.create(name="Rigging")
        rigging_service = ServiceFactory(category=rigging, longname="Rigging Service")
        ServiceInstance.objects.create(service=rigging_service, event=self.e5)

        combo_discount = Discount.objects.create(name="Combo Discount")
        combo_discount.categories.add(self.category)
        combo_discount.categories.add(sound)
        self.e5.applied_discounts.add(combo_discount)
        DiscountPrice.objects.create(pricelist=self.pricelist, discount=combo_discount, percent=10)

        test_fee = Fee.objects.create(name="Test Fee")
        test_fee.categories.add(self.category)
        self.e5.applied_fees.add(test_fee)
        FeePrice.objects.create(pricelist=self.pricelist, fee=test_fee, percent=25)

        Rental.objects.create(event=self.e5, name="rental lights", cost=43, quantity=4, rental_fee_applied=True)
        Rental.objects.create(event=self.e5, name="rental transportation", cost=72, quantity=1, rental_fee_applied=False)


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
        self.assertEqual(list(response['events']), [self.e2, self.e4, self.e5])
        self.assertEqual(response['multibilling'], self.multibilling)
        self.assertEqual(list(response['orgs']), [self.organization])
        #self.assertEqual(float(response['total_cost']), 10.00)
        self.assertEqual(float(response['total_cost']), 420403.42)

    def test_get_extras(self):
        event_data = {
            'event': self.e,
            'is_event2019': False,
            'extras': {},
            'categories': [],
            'expiry_date': timezone.now() + datetime.timedelta(days=7)
        }
        response = views.get_quote_data(self.e)
        self.assertTrue(abs(response['expiry_date'] - event_data['expiry_date']) < datetime.timedelta(minutes=1))
        response.pop('expiry_date')
        event_data.pop('expiry_date')
        self.assertEqual(response, event_data)

        response = views.get_quote_data(self.e4)
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

    def test_new_pdf_bill(self):
        html_response = self.client.get(reverse("events:bills:pdf", args=[self.e5.pk]), {'raw': True})
        self.assertEqual(html_response.status_code, 200)

        response = self.client.get(reverse("events:bills:pdf", args=[self.e5.pk]))
        self.assertEqual(response.status_code, 200)

        pdf = PdfReader(BytesIO(response.content))
        text = ''.join(page.extract_text() for page in pdf.pages)
        print(text) # TEMPORARY TO FIGURE OUT WHAT'S WRONG WITH GITHUB TESTS
        self.assertTrue("QUOTE" in text)
        self.assertTrue("New Discounts Test" in text)
        self.assertTrue("First Lighting Service" in text)
        self.assertTrue("Test Extra" in text)
        self.assertTrue("Combo Discount" in text)
        self.assertTrue("Test Fee" in text)
        self.assertTrue("Sound Service" in text)
        self.assertTrue("Test Sound Extra" in text)
        self.assertTrue("Rigging Service" in text)
        self.assertTrue("rental lights" in text)
        self.assertTrue("LNL Rental Fee" in text)
        self.assertTrue("rental transportation" in text)

    def test_bill_pdf_standalone(self):
        # Test that a file is successfully returned
        self.assertIsNotNone(views.generate_event_bill_pdf_standalone(event=self.e4))

        # test with the new template
        self.assertIsNotNone(views.generate_event_bill_pdf_standalone(event=self.e5))

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
        self.assertEqual(response.content, b"Should probably give some ids to return pdfs for.")

        # Test with "2019" event
        response = self.client.get(reverse('events:pdf-multi', args=["%s,%s" % (self.e3.pk, self.e4.pk)]))
        self.assertEqual(response.status_code, 200)

    def test_bill_pdf_multi(self):
        html_response = self.client.get(reverse('events:bill-pdf-multi', args=["%s,%s" % (self.e.pk, self.e2.pk)]),
                                        {'raw': True})
        self.assertEqual(html_response.status_code, 200)
        self.assertTrue(b'QUOTE' in html_response.content)

        # Test with no ids
        response = self.client.get(reverse('events:bill-pdf-multi'))
        self.assertEqual(response.content, b"Should probably give some ids to return pdfs for.")

        # Test with "2019" event
        response = self.client.get(reverse('events:bill-pdf-multi', args=["%s,%s" % (self.e3.pk, self.e4.pk)]))
        self.assertEqual(response.status_code, 200)

        # test with both pdf templates
        response = self.client.get(reverse('events:pdf-multi', args=["%s,%s,%s,%s,%s" % (self.e.pk, self.e2.pk, self.e3.pk, self.e4.pk, self.e5.pk)]))
        self.assertEqual(response.status_code, 200)

        pdf = PdfReader(BytesIO(response.content))
        text = ''.join(page.extract_text() for page in pdf.pages)
        self.assertTrue("First Test Event" in text)
        self.assertTrue("Other Test Event" in text)
        self.assertTrue("First 2019 Test Event" in text)
        self.assertTrue("Another 2019 Test Event" in text)
        self.assertTrue("New Discounts Test" in text)

    def test_quote_logging(self):
        response = self.client.get(reverse("events:bills:pdf", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Quote.objects.get(event=self.e))

        response = self.client.get(reverse("events:bills:pdf", args=[self.e5.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Quote.objects.get(event=self.e5))

        # test that the standalone view still saves a quote
        self.assertIsNotNone(views.generate_event_bill_pdf_standalone(event=self.e4))
        self.assertTrue(Quote.objects.get(event=self.e4))

        # test that the bill pdf multi view saves quotes for each of its events
        response = self.client.get(reverse('events:bill-pdf-multi', args=["%s,%s" % (self.e2.pk, self.e3.pk)]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Quote.objects.get(event=self.e2))
        self.assertTrue(Quote.objects.get(event=self.e3))

    def test_view_quote(self):
        # make a quote
        response = self.client.get(reverse("events:bills:pdf", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)
        # extract the text from the quote
        pdf = PdfReader(BytesIO(response.content))
        original_text = ''.join(page.extract_text() for page in pdf.pages)

        # retrieve the saved quote
        pk = Quote.objects.get(event=self.e).pk
        response = self.client.get(reverse("events:view-quote", args=[pk]))
        self.assertEqual(response.status_code, 200)
        # extract its text
        pdf = PdfReader(BytesIO(response.content))
        quote_text = ''.join(page.extract_text() for page in pdf.pages)
        # make sure the original and the saved version are the same
        self.assertMultiLineEqual(original_text, quote_text)


        # test with the new quote template as well
        response = self.client.get(reverse("events:bills:pdf", args=[self.e5.pk]))
        self.assertEqual(response.status_code, 200)
        # extract the text from the quote
        pdf = PdfReader(BytesIO(response.content))
        original_text = ''.join(page.extract_text() for page in pdf.pages)

        # retrieve the saved quote
        pk = Quote.objects.get(event=self.e5).pk
        response = self.client.get(reverse("events:view-quote", args=[pk]))
        self.assertEqual(response.status_code, 200)
        # extract its text
        pdf = PdfReader(BytesIO(response.content))
        quote_text = ''.join(page.extract_text() for page in pdf.pages)
        # make sure the original and the saved version are the same
        self.assertMultiLineEqual(original_text, quote_text)

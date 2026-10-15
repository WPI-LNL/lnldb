"""
The bill and multi-bill pages, and the multi-bill invoice.

These moved here from the events app along with the bills themselves, and so
did their tests: the page tests were the events app's, the invoice tests the
pdfs app's. The events app keeps the tests for its own billing lists and for
the client's worktag form.
"""
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from data.tests.util import ViewTestCase
from events.models import Organization
from events.tests.generators import Event2019Factory, EventFactory, OrgFactory, UserFactory
from finance.models import Billing, MultiBilling
from finance.views import billing as billing_views


class BillingViewTests(ViewTestCase):
    def setup(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.e3 = Event2019Factory.create(event_name="2019 Test Event")
        self.org = OrgFactory.create(name="Test Org")

    def test_bill_add(self):
        self.setup()

        # By default, user should not have permission to create bills
        self.assertOk(self.client.get(reverse("finance:bill-new", args=[self.e.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:bill-new", args=[self.e.pk])))

        # If event is closed redirect to detail page
        self.e.closed = True
        self.e.save()

        self.assertRedirects(self.client.get(reverse("finance:bill-new", args=[self.e.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # Check with valid input
        data_email = {
            "date_billed": timezone.now().date(),
            "amount": 20.00,
            "save-and-make-email": "Save and Make Email"
        }

        data_no_email = {
            "date_billed": timezone.now().date(),
            "amount": 30.00,
            "save-and-return": "Save and Return"
        }

        self.assertRedirects(self.client.post(reverse("finance:bill-new", args=[self.e.pk]), data_email),
                             reverse("finance:bill-email", args=[self.e.pk, 1]))

        self.assertRedirects(self.client.post(reverse("finance:bill-new", args=[self.e.pk]), data_no_email),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        self.assertTrue(Billing.objects.filter(amount=20.00).exists())
        self.assertTrue(Billing.objects.filter(amount=30.00).exists())

    def test_bill_edit(self):
        self.setup()

        self.e2.closed = True
        self.e2.save()

        bill = Billing.objects.create(date_billed=timezone.now().date(), event=self.e, amount=200.00)
        another_bill = Billing.objects.create(date_billed=timezone.now().date(), event=self.e2, amount=50.00)

        # By default, user should not have permission to modify bills
        self.assertOk(self.client.get(reverse("finance:bill-edit", args=[self.e.pk, bill.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:bill-edit", args=[self.e.pk, bill.pk])))

        # If event is closed, redirect to detail page
        self.assertRedirects(self.client.get(reverse("finance:bill-edit", args=[self.e2.pk, another_bill.pk])),
                             reverse("events:detail", args=[self.e2.pk]))

        # Raise permission denied if for some reason event and bill pks do not match
        self.assertOk(self.client.get(reverse("finance:bill-edit", args=[self.e.pk, another_bill.pk])), 403)

        # Test valid input
        valid_data = {
            "date_billed": timezone.now().date(),
            "amount": 500.00,
            "save": "Save Changes"
        }
        self.assertRedirects(self.client.post(reverse("finance:bill-edit", args=[self.e.pk, bill.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        bill.refresh_from_db()
        self.assertEqual(bill.amount, 500.00)

    def test_bill_delete(self):
        self.setup()

        self.e2.closed = True
        self.e2.save()

        bill = Billing.objects.create(date_billed=timezone.now().date(), event=self.e, amount=200.00)
        another_bill = Billing.objects.create(date_billed=timezone.now().date(), event=self.e2, amount=400.00)

        # By default, user should not have permission to delete bills
        self.assertOk(self.client.get(reverse("finance:bill-delete", args=[self.e.pk, bill.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirects
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:bill-delete", args=[self.e.pk, bill.pk])))

        # If event is closed, redirect to the detail page
        self.assertRedirects(self.client.get(reverse("finance:bill-delete", args=[self.e2.pk, another_bill.pk])),
                             reverse("events:detail", args=[self.e2.pk]))

        # Raise permission denied if event and bill pks do not match and event is either closed or has been paid
        self.assertOk(self.client.get(reverse("finance:bill-delete", args=[self.e.pk, another_bill.pk])), 403)

        bill.date_paid = timezone.now().date()
        bill.save()

        self.assertOk(self.client.get(reverse("finance:bill-delete", args=[self.e.pk, bill.pk])), 403)

        bill.date_paid = None
        bill.save()

        # Test POST
        self.assertRedirects(self.client.post(reverse("finance:bill-delete", args=[self.e.pk, bill.pk])),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        self.assertFalse(Billing.objects.filter(pk=bill.pk).exists())

    def test_multibill_add(self):
        self.setup()

        self.e.reviewed = True
        self.e.billed_in_bulk = True
        self.e.billing_org = self.org
        self.e.save()

        self.e2.reviewed = True
        self.e2.billed_in_bulk = True
        self.e2.save()

        # By default, user should not have permission to create multibills
        self.assertOk(self.client.get(reverse("finance:multibill-new")), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:multibill-new")))

        # Test POST
        data_email = {
            "events": [str(self.e.pk), str(self.e2.pk)],
            "date_billed": timezone.now().date(),
            "amount": 500.00,
            "save-and-make-email": "Save and Make Email"
        }

        data_no_email = {
            "events": [str(self.e.pk), str(self.e2.pk)],
            "date_billed": timezone.now().date(),
            "amount": 400.00,
            "save-and-return": "Save and Return"
        }

        # Throw error if events do not have same billing organization
        self.assertOk(self.client.post(reverse("finance:multibill-new"), data_email))

        self.e2.org.add(self.org)
        self.e2.save()

        self.assertRedirects(self.client.post(reverse("finance:multibill-new"), data_email),
                             reverse("finance:multibill-email", args=[1]))

        self.assertRedirects(self.client.post(reverse("finance:multibill-new"), data_no_email),
                             reverse("finance:multibill-list"))

        self.assertTrue(MultiBilling.objects.filter(amount=500.00).exists())
        self.assertTrue(MultiBilling.objects.filter(amount=400.00).exists())

    def test_multibill_edit(self):
        self.setup()

        multibill = MultiBilling.objects.create(date_billed=timezone.now().date(), amount=200.00)
        multibill.events.add(self.e)
        multibill.events.add(self.e2)

        # By default, user should not have permission to edit multibills
        self.assertOk(self.client.get(reverse("finance:multibill-edit", args=[multibill.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:multibill-edit", args=[multibill.pk])))

        # Check that if one or more event is closed we get permission denied
        self.e2.closed = True
        self.e2.save()

        self.assertOk(self.client.get(reverse("finance:multibill-edit", args=[multibill.pk])), 403)

        self.e2.closed = False
        self.e2.save()

        # Check with valid input
        valid_data = {
            "date_paid": timezone.now().date(),
            "amount": 400.00,
            "save": "Save Changes"
        }
        self.assertRedirects(self.client.post(reverse("finance:multibill-edit", args=[multibill.pk]), valid_data),
                             reverse("finance:multibill-list"))

        multibill.refresh_from_db()
        self.assertEqual(multibill.amount, 400.00)

    def test_multibill_delete(self):
        self.setup()

        multibill = MultiBilling.objects.create(date_billed=timezone.now().date(), amount=1000.00)
        multibill.events.add(self.e)
        multibill.events.add(self.e2)

        # By default, user should not have permission to delete multibills
        self.assertOk(self.client.get(reverse("finance:multibill-delete", args=[multibill.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:multibill-delete", args=[multibill.pk])))

        # Check that if one or more events is closed, we get permission denied
        self.e2.closed = True
        self.e2.save()

        self.assertOk(self.client.get(reverse("finance:multibill-delete", args=[multibill.pk])), 403)

        self.e2.closed = False
        self.e2.save()

        # Check that if the bill has been paid we cannot delete it
        multibill.date_paid = timezone.now().date()
        multibill.save()

        self.assertOk(self.client.get(reverse("finance:multibill-delete", args=[multibill.pk])), 403)

        multibill.date_paid = None
        multibill.save()

        # Test POST
        self.assertRedirects(self.client.post(reverse("finance:multibill-delete", args=[multibill.pk])),
                             reverse("finance:multibill-list"))

        self.assertFalse(MultiBilling.objects.filter(pk=multibill.pk).exists())

    def test_pay(self):
        self.setup()

        b = self.e.billings.create(date_billed=timezone.now().date(), amount=3.14)

        # random clicks wont work
        self.assertOk(self.client.get(reverse('finance:bill-pay', args=[self.e.pk, b.pk])), 405)

        # User needs permission
        self.assertOk(self.client.post(reverse("finance:bill-pay", args=[self.e.pk, b.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # If event is closed, redirect to detail page
        self.e.closed = True
        self.e.save()

        self.assertRedirects(self.client.post(reverse("finance:bill-pay", args=[self.e.pk, b.pk])),
                             reverse("events:detail", args=[self.e.pk]))

        self.e.closed = False
        self.e.save()

        # on success, redirects to event page
        self.assertRedirects(self.client.post(reverse('finance:bill-pay', args=[self.e.pk, b.pk])),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

        # check it is actually paid
        b.refresh_from_db()
        self.assertIsNotNone(b.date_paid)
        self.assertTrue(self.e.paid)

        # If bill has already been paid, redirect to next page
        self.assertRedirects(self.client.post(reverse("finance:bill-pay", args=[self.e.pk, b.pk]) + "?next=/db/"),
                             reverse("home"))

    def test_billing_email(self):
        self.setup()

        b = self.e.billings.create(date_billed=timezone.now().date(), amount=75.95)

        # User needs permission to create a billing email
        self.assertOk(self.client.get(reverse("finance:bill-email", args=[self.e.pk, b.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for the redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:bill-email", args=[self.e.pk, b.pk])))

        # Test valid data
        valid_data = {
            "subject": "Your Bill",
            "message": "Thank you for choosing LNL! Now pay your bill.",
            "email_to_users": str(self.user.pk),
            "email_to_orgs": [],
            "save": "Send Email"
        }

        self.assertRedirects(self.client.post(reverse("finance:bill-email", args=[self.e.pk, b.pk]), valid_data),
                             reverse("events:detail", args=[self.e.pk]) + "#billing")

    def test_multibilling_email(self):
        self.setup()

        b = self.e.multibillings.create(date_billed=timezone.now().date(), amount=1.50)

        # User needs permission to create a billing email
        self.assertOk(self.client.get(reverse("finance:multibill-email", args=[b.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:multibill-email", args=[b.pk])))

        # Test valid input
        valid_data = {
            "subject": "Your Bill",
            "message": "Welcome back valued customer! Here's your bill.",
            "email_to_users": str(self.user.pk),
            "email_to_orgs": [],
            "save": "Send Email"
        }

        self.assertRedirects(self.client.post(reverse("finance:multibill-email", args=[b.pk]), valid_data),
                             reverse("finance:multibill-list"))

    def test_entered_into_workday(self):
        self.setup()

        # GET should not be permitted
        self.assertOk(self.client.get(reverse("finance:workday-entered", args=[self.e3.pk])), 405)

        # User will need permission
        self.assertOk(self.client.post(reverse("finance:workday-entered", args=[self.e3.pk])), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        # Will need view_event permission for redirect
        permission = Permission.objects.get(codename="view_events")
        self.user.user_permissions.add(permission)

        # Should redirect to event detail page - Event has not yet been reviewed
        self.assertRedirects(self.client.post(reverse("finance:workday-entered", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.reviewed = True
        self.e3.closed = True
        self.e3.save()

        # Should redirect to event detail page - Event is closed
        self.assertRedirects(self.client.post(reverse("finance:workday-entered", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        self.e3.closed = False
        self.e3.save()

        # Should redirect to event detail page - Event has not been billed
        self.assertRedirects(self.client.post(reverse("finance:workday-entered", args=[self.e3.pk])),
                             reverse("events:detail", args=[self.e3.pk]))

        Billing.objects.create(event=self.e3, date_billed=timezone.now().date(), amount=26.33)

        # Should now be able to mark as entered into workday
        self.assertRedirects(self.client.post(reverse("finance:workday-entered", args=[self.e3.pk])),
                             reverse("events:awaitingworkday"))

        # Check that we get no errors when trying to mark an event that has already been marked
        self.assertRedirects(self.client.post(reverse("finance:workday-entered", args=[self.e3.pk])),
                             reverse("events:awaitingworkday"))


class MultiBillInvoiceTests(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="First Test Event")
        self.e2 = Event2019Factory.create(event_name="Another 2019 Test Event")
        self.user = UserFactory.create(password='123')
        self.client.login(username=self.user.username, password='123')

        self.organization = Organization.objects.create(name="Test org", phone="1234567890", user_in_charge=self.user)
        self.e2.org.add(self.organization)
        self.multibilling = MultiBilling.objects.create(date_billed=timezone.datetime.today(), amount=20.00,
                                                        org=self.organization)
        self.multibilling.events.add(self.e)
        self.multibilling.events.add(self.e2)

    def test_get_multibill_data(self):
        response = billing_views.get_multibill_data(self.multibilling)
        self.assertEqual(response['billing_org'], self.organization)
        self.assertEqual(list(response['events']), [self.e, self.e2])
        self.assertEqual(response['multibilling'], self.multibilling)
        self.assertEqual(list(response['orgs']), [self.organization])
        self.assertEqual(response['total_cost'], self.e.cost_total + self.e2.cost_total)

    def test_pdf_multibill(self):
        response = self.client.get(reverse('finance:multibill-pdf', args=[self.multibilling.pk]))
        self.assertEqual(response.status_code, 200)

    def test_multibill_pdf_standalone(self):
        # Test that a file is successfully returned
        self.assertIsNotNone(billing_views.generate_multibill_pdf_standalone(multibilling=self.multibilling))

    def test_old_multibill_list_address_redirects(self):
        self.assertRedirects(self.client.get('/db/events/multibills/'), reverse('finance:multibill-list'),
                             fetch_redirect_response=False)

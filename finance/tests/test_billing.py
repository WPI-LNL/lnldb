"""
The bill and multi-bill pages, and the multi-bill invoice.

The first two classes moved here from the events app along with the bills
themselves: the page tests were the events app's, the invoice tests the pdfs
app's. The events app keeps the tests for its own billing lists and for the
client's worktag form.

The rest are the multi-bill's own: what it comes to and how each charge is
priced, which events it may cover and when the clients differ, its pages and
when they refuse a change, marking it paid, its invoice, and the two places
elsewhere in finance that read a multi-bill -- the rental check and revenue by
client.

WeasyPrint, which draws the invoice, needs native libraries that CI installs
and a developer's machine may not have. So the tests swap it for a blank page
(:func:`blank_page`), apart from one class that draws the invoice for real
wherever WeasyPrint can.
"""
import datetime
from decimal import Decimal
from io import BytesIO
from unittest import mock, skipUnless

from django.contrib.auth.models import Permission
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from weasyprint import HTML

from data.tests.util import ViewTestCase
from events.models import EventArbitrary, Organization, Pricelist, Quote
from events.tests.generators import Event2019Factory, EventFactory, OrgFactory, UserFactory
from finance.billing_forms import MultiBillChargeForm, MultiBillForm, billable_events
from finance.calculators import event_financials, revenue_by_client
from finance.models import Billing, MultiBilling, MultiBillingCharge, money
from finance.tests.test_event_costs import cost
from finance.tests.test_revenue_sources import event_income
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
        other = OrgFactory.create(name="Other Org")

        self.e.reviewed = True
        self.e.billed_in_bulk = True
        self.e.billing_org = self.org
        self.e.save()

        self.e2.reviewed = True
        self.e2.billed_in_bulk = True
        self.e2.billing_org = other
        self.e2.save()

        # By default, user should not have permission to create multibills
        self.assertOk(self.client.get(reverse("finance:multibill-new")), 403)

        permission = Permission.objects.get(codename="bill_event")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("finance:multibill-new")))

        # There is no total to type: the events' prices are the total
        data = {
            "events": [str(self.e.pk), str(self.e2.pk)],
            "date_billed": timezone.now().date(),
            "name": "Fall films",
        }

        # Events for different clients need the Treasurer to say so
        response = self.client.post(reverse("finance:multibill-new"), data)
        self.assertContains(response, "Bill these together")
        self.assertFalse(MultiBilling.objects.exists())

        data["confirm_mixed_clients"] = "on"
        data["org"] = str(other.pk)
        response = self.client.post(reverse("finance:multibill-new"), dict(data, **{"save-and-email": "1"}))
        bill = MultiBilling.objects.get()
        self.assertRedirects(response, reverse("finance:multibill-email", args=[bill.pk]))
        self.assertEqual(bill.name, "Fall films")
        self.assertEqual(bill.org, other)
        self.assertEqual(bill.amount, money(self.e.cost_total) + money(self.e2.cost_total))
        self.assertEqual(set(bill.events.all()), {self.e, self.e2})

    def test_multibill_edit(self):
        self.setup()

        multibill = MultiBilling.objects.create(date_billed=timezone.now().date(), amount=200.00, org=self.org)
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

        # A paid bill cannot be changed until it is marked unpaid
        multibill.date_paid = timezone.now().date()
        multibill.save()
        self.assertRedirects(self.client.get(reverse("finance:multibill-edit", args=[multibill.pk])),
                             reverse("finance:multibill-detail", args=[multibill.pk]))
        multibill.date_paid = None
        multibill.save()

        # Taking an event off and renaming it; the total follows
        valid_data = {
            "events": [str(self.e.pk)],
            "org": str(self.org.pk),
            "name": "Renamed",
            "date_billed": timezone.now().date(),
        }
        self.assertRedirects(self.client.post(reverse("finance:multibill-edit", args=[multibill.pk]), valid_data),
                             reverse("finance:multibill-detail", args=[multibill.pk]))

        multibill.refresh_from_db()
        self.assertEqual(multibill.name, "Renamed")
        self.assertEqual(list(multibill.events.all()), [self.e])
        self.assertEqual(multibill.amount, money(self.e.cost_total))

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

        # The draft is written out, as it is for a single bill
        b.name = "Spring films"
        b.save()
        response = self.client.get(reverse("finance:multibill-email", args=[b.pk]))
        self.assertOk(response)
        self.assertContains(response, "Invoice for LNL Services: Spring films")
        self.assertContains(response, self.e.event_name)

        # Test valid input
        valid_data = {
            "subject": "Your Bill",
            "message": "Welcome back valued customer! Here's your bill.",
            "email_to_users": str(self.user.pk),
            "email_to_orgs": [],
            "save": "Send Email"
        }

        with mock.patch('finance.views.billing.write_weasyprint_pdf', blank_page):
            self.assertRedirects(self.client.post(reverse("finance:multibill-email", args=[b.pk]), valid_data),
                                 reverse("finance:multibill-detail", args=[b.pk]))
        self.assertIsNotNone(b.multibillingemail_set.get().sent_at)
        self.assertEqual([(name, kind) for name, _, kind in mail.outbox[-1].attachments],
                         [("spring-films-bill.pdf", "application/pdf")])

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
        with mock.patch('finance.views.billing.write_weasyprint_pdf', blank_page):
            response = self.client.get(reverse('finance:multibill-pdf', args=[self.multibilling.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_multibill_invoice_pdf(self):
        # Test that a file is successfully returned
        with mock.patch('finance.views.billing.write_weasyprint_pdf', blank_page):
            self.assertTrue(billing_views.multibill_invoice_pdf(self.multibilling).startswith(b'%PDF'))

    def test_old_multibill_list_address_redirects(self):
        self.assertRedirects(self.client.get('/db/events/multibills/'), reverse('finance:multibill-list'),
                             fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# Multi-bills
# ---------------------------------------------------------------------------

def priced_event(name, price, org=None, **kwargs):
    """
    A reviewed event that would be billed exactly ``price`` on its own: one
    one-off charge, and nothing else for the events app to price.
    """
    kwargs.setdefault('billed_in_bulk', True)
    event = Event2019Factory(event_name=name, reviewed=True, billing_org=org, **kwargs)
    EventArbitrary.objects.create(event=event, key_name='Show', key_value=Decimal(price), key_quantity=1)
    return event


def multibill(*events, **kwargs):
    """ A multi-bill over ``events``, with its total worked out. """
    kwargs.setdefault('date_billed', datetime.date(2026, 3, 1))
    kwargs.setdefault('amount', Decimal('0.00'))
    bill = MultiBilling.objects.create(**kwargs)
    bill.events.set(events)
    bill.recalculate()
    return bill


def charge(bill, kind, description, **kwargs):
    if kind != MultiBillingCharge.PERCENT:
        kwargs.setdefault('unit_price', Decimal('0.00'))
    return MultiBillingCharge.objects.create(multibilling=bill, kind=kind, description=description, **kwargs)


def blank_page(html, pdf_file):
    """ Stands in for ``write_weasyprint_pdf``: one blank page, 200 points square, so it can be told apart. """
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(pdf_file)
    return pdf_file


def _weasyprint_draws():
    """ Whether WeasyPrint can draw a page on this machine at all. """
    try:
        HTML(string='<p>LNL</p>').write_pdf()
    except (OSError, RuntimeError):
        return False
    return True


WEASYPRINT_DRAWS = _weasyprint_draws()


class MultiBillTotalTests(TestCase):
    """ What a multi-bill comes to: its events, then its own charges, each priced as on one event. """

    def setUp(self):
        self.org = OrgFactory(name='Social Committee', shortname='SocComm')
        self.first = priced_event('Film One', '600.05', org=self.org)
        self.second = priced_event('Film Two', '400.00', org=self.org)
        self.bill = multibill(self.first, self.second, org=self.org)

    def test_the_events_alone(self):
        self.assertEqual(self.bill.amount, Decimal('1000.05'))
        breakdown = self.bill.breakdown()
        self.assertEqual([row['price'] for row in breakdown['events']], [Decimal('600.05'), Decimal('400.00')])
        self.assertEqual(breakdown['events_total'], Decimal('1000.05'))

    def test_each_kind_of_charge(self):
        """
        Two crew calls at $50, a $25 credit, a $333.33 hire with its 15% fee
        ($49.9995, rounded down to $49.99 as an event's fee is), a 10% fee on
        the events ($100.005 to $100.00) and a 5% discount (-$50.0025 to
        -$50.00): $1,508.37 in all.
        """
        charge(self.bill, MultiBillingCharge.ONE_OFF, 'Crew call', quantity=2, unit_price=Decimal('50.00'))
        charge(self.bill, MultiBillingCharge.ONE_OFF, 'Goodwill credit', unit_price=Decimal('-25.00'))
        charge(self.bill, MultiBillingCharge.RENTAL, 'Projector', unit_price=Decimal('333.33'),
               rental_fee_percent=Decimal('15'))
        charge(self.bill, MultiBillingCharge.PERCENT, 'Late booking fee', percent=Decimal('10'))
        charge(self.bill, MultiBillingCharge.PERCENT, 'Returning client', percent=Decimal('-5'))
        breakdown = self.bill.breakdown()
        self.assertEqual([row['total'] for row in breakdown['charges']],
                         [Decimal('100.00'), Decimal('-25.00'), Decimal('383.32'), Decimal('100.00'),
                          Decimal('-50.00')])
        self.assertEqual(breakdown['rentals_total'], Decimal('383.32'))
        self.assertEqual(breakdown['total'], Decimal('1508.37'))
        self.assertEqual(self.bill.rental_charges_total(), Decimal('383.32'))
        self.assertTrue(self.bill.recalculate())
        self.assertEqual(MultiBilling.objects.get(pk=self.bill.pk).amount, Decimal('1508.37'))

    def test_a_paid_bill_keeps_what_it_was_paid(self):
        self.bill.date_paid = datetime.date(2026, 4, 1)
        self.bill.save()
        EventArbitrary.objects.create(event=self.first, key_name='Late extra', key_value=Decimal('99.00'),
                                      key_quantity=1)
        self.assertFalse(self.bill.recalculate())
        self.assertEqual(MultiBilling.objects.get(pk=self.bill.pk).amount, Decimal('1000.05'))

    def test_its_name_or_what_it_covers(self):
        self.assertEqual(self.bill.display_name, '2 events for SocComm')
        self.bill.name = 'Fall films'
        self.assertEqual(self.bill.display_name, 'Fall films')


class MultiBillFormTests(TestCase):
    """ Which events a multi-bill may cover, who it is billed to, and its charges. """

    def setUp(self):
        self.socomm = OrgFactory(name='Social Committee', shortname='SocComm')
        self.lnl = OrgFactory(name='Lens and Lights', shortname='LNL')

    def form(self, events, bill=None, **data):
        data.setdefault('date_billed', '2026-03-01')
        data['events'] = [str(event.pk) for event in events]
        return MultiBillForm(data, instance=bill)

    def test_an_event_is_never_offered_to_two_bills(self):
        free = priced_event('Free', '10.00')
        taken = priced_event('Taken', '10.00')
        own_bill = priced_event('Own bill', '10.00')
        Billing.objects.create(event=own_bill, date_billed=datetime.date(2026, 3, 1), amount=Decimal('10.00'))
        other = multibill(taken, org=self.socomm)
        self.assertEqual(list(billable_events()), [free])
        # Its own events stay on offer while it is edited
        self.assertEqual(set(billable_events(other)), {free, taken})

    def test_events_not_marked_for_bulk_billing_only_when_asked(self):
        marked = priced_event('Marked', '10.00')
        unmarked = priced_event('Unmarked', '10.00', billed_in_bulk=False)
        self.assertEqual(list(billable_events()), [marked])
        self.assertEqual(set(billable_events(include_unmarked=True)), {marked, unmarked})

    def test_different_clients_need_saying_so(self):
        films = [priced_event('Film %s' % n, '10.00', org=org)
                 for n, org in enumerate((self.socomm, self.lnl, self.socomm))]
        form = self.form(films)
        self.assertFalse(form.is_valid())
        self.assertIn('confirm_mixed_clients', form.errors)
        self.assertIn('SocComm (2 events), LNL (1 event)', form.fields['confirm_mixed_clients'].label)
        # Confirmed, with nobody chosen, it goes to the client most of them are for
        form = self.form(films, confirm_mixed_clients='on')
        self.assertTrue(form.is_valid(), form.errors)
        bill = form.save()
        self.assertEqual(bill.org, self.socomm)
        self.assertEqual(bill.amount, Decimal('30.00'))

    def test_a_bill_already_for_different_clients_starts_confirmed(self):
        """ They were confirmed when it was made; editing it should not ask again before it is saved. """
        bill = multibill(priced_event('A', '10.00', org=self.socomm), priced_event('B', '10.00', org=self.lnl),
                         org=self.socomm)
        form = MultiBillForm(instance=bill)
        self.assertIn('confirm_mixed_clients', form.helper.layout.fields)
        self.assertTrue(form.fields['confirm_mixed_clients'].initial)

    def test_one_client_needs_no_confirming(self):
        form = self.form([priced_event('A', '10.00', org=self.lnl), priced_event('B', '10.00')])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['org'], self.lnl)
        self.assertNotIn('confirm_mixed_clients', [f for f in form.helper.layout.fields])

    def test_no_client_anywhere_means_choosing_one(self):
        form = self.form([priced_event('A', '10.00')])
        self.assertFalse(form.is_valid())
        self.assertIn('org', form.errors)

    def test_a_percentage_needs_a_percentage_and_nothing_else(self):
        bill = multibill(priced_event('A', '10.00'), org=self.lnl)
        form = MultiBillChargeForm({'kind': 'percent', 'description': 'Fee', 'quantity': '1'},
                                   instance=MultiBillingCharge(multibilling=bill))
        self.assertFalse(form.is_valid())
        self.assertIn('percent', form.errors)
        form = MultiBillChargeForm({'kind': 'percent', 'description': 'Fee', 'quantity': '3',
                                    'unit_price': '20.00', 'percent': '12.5'},
                                   instance=MultiBillingCharge(multibilling=bill))
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertIsNone(saved.unit_price)
        self.assertEqual(saved.quantity, 1)

    def test_a_rental_is_not_a_credit(self):
        bill = multibill(priced_event('A', '10.00'), org=self.lnl)
        form = MultiBillChargeForm({'kind': 'rental', 'description': 'Haze', 'quantity': '1',
                                    'unit_price': '-5.00'}, instance=MultiBillingCharge(multibilling=bill))
        self.assertFalse(form.is_valid())
        self.assertIn('unit_price', form.errors)

    def test_the_rental_fee_is_fixed_when_it_is_added(self):
        Pricelist.objects.create(name='Default', is_default_pricelist=True, rental_fee_percentage=Decimal('20'))
        bill = multibill(priced_event('A', '10.00'), org=self.lnl)
        form = MultiBillChargeForm({'kind': 'rental', 'description': 'Haze', 'quantity': '1',
                                    'unit_price': '100.00', 'add_rental_fee': 'on'},
                                   instance=MultiBillingCharge(multibilling=bill))
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.rental_fee_percent, Decimal('20'))
        # A later change to the default pricelist does not reprice it
        Pricelist.objects.update(rental_fee_percentage=Decimal('25'))
        form = MultiBillChargeForm({'kind': 'rental', 'description': 'Haze', 'quantity': '2',
                                    'unit_price': '100.00', 'add_rental_fee': 'on'}, instance=saved)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().rental_fee_percent, Decimal('20'))


class MultiBillPageTests(ViewTestCase):
    """ The multi-bill's pages, and when they refuse a change. """

    def setUp(self):
        super(MultiBillPageTests, self).setUp()
        self.user.user_permissions.add(Permission.objects.get(codename='bill_event'))
        self.org = OrgFactory(name='Social Committee', shortname='SocComm')
        self.first = priced_event('Film One', '500.00', org=self.org)
        self.second = priced_event('Film Two', '500.00', org=self.org)
        self.bill = multibill(self.first, self.second, org=self.org, name='Fall films')

    def url(self, name, *args):
        return reverse('finance:' + name, args=(self.bill.pk,) + args)

    def test_the_page_lays_the_bill_out(self):
        charge(self.bill, MultiBillingCharge.ONE_OFF, 'Crew call', unit_price=Decimal('50.00'))
        self.bill.recalculate()
        response = self.client.get(self.url('multibill-detail'))
        self.assertContains(response, 'Fall films')
        self.assertContains(response, 'Film One')
        self.assertContains(response, 'Crew call')
        self.assertContains(response, '$1,050.00')
        self.assertContains(response, 'Unpaid')
        self.assertNotContains(response, 'The saved total is')

    def test_the_list_shows_where_each_stands(self):
        response = self.client.get(reverse('finance:multibill-list'))
        self.assertContains(response, 'Fall films')
        self.assertContains(response, 'Never')
        self.assertContains(response, self.url('multibill-paid'))
        self.assertContains(response, self.url('multibill-email'))

    def test_adding_changing_and_removing_a_charge_moves_the_total(self):
        response = self.client.post(self.url('multibill-charge-new'),
                                    {'kind': 'oneoff', 'description': 'Crew call', 'quantity': '2',
                                     'unit_price': '50.00'})
        self.assertRedirects(response, self.url('multibill-detail'))
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.amount, Decimal('1100.00'))

        added = self.bill.charges.get()
        self.client.post(self.url('multibill-charge-edit', added.pk),
                         {'kind': 'percent', 'description': 'Fee', 'percent': '10', 'quantity': '1'})
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.amount, Decimal('1100.00'))

        self.client.post(self.url('multibill-charge-delete', added.pk))
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.amount, Decimal('1000.00'))
        self.assertFalse(self.bill.charges.exists())

    def test_a_paid_bill_takes_no_changes(self):
        self.bill.date_paid = datetime.date(2026, 4, 1)
        self.bill.save()
        response = self.client.post(self.url('multibill-charge-new'),
                                    {'kind': 'oneoff', 'description': 'Crew call', 'quantity': '1',
                                     'unit_price': '50.00'}, follow=True)
        self.assertRedirects(response, self.url('multibill-detail'))
        self.assertContains(response, 'Mark it unpaid first')
        self.assertFalse(self.bill.charges.exists())

    def test_a_closed_event_locks_the_bill(self):
        self.second.closed = True
        self.second.save()
        self.assertEqual(self.client.get(self.url('multibill-charge-new')).status_code, 403)
        response = self.client.get(self.url('multibill-paid'), follow=True)
        self.assertContains(response, 'is closed')

    def test_a_price_change_after_billing_is_flagged_and_can_be_taken_up(self):
        EventArbitrary.objects.create(event=self.first, key_name='Late extra', key_value=Decimal('25.00'),
                                      key_quantity=1)
        response = self.client.get(self.url('multibill-detail'))
        self.assertContains(response, 'The saved total is $1,000.00')
        self.assertContains(response, 'Update the total to $1,025.00')
        self.client.post(self.url('multibill-update-total'))
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.amount, Decimal('1025.00'))

    def test_marking_paid_offers_today_when_nothing_is_filed(self):
        response = self.client.get(self.url('multibill-paid'))
        self.assertEqual(response.context['form'].initial['date_paid'], datetime.date.today())
        self.assertContains(response, 'The date below is today')
        response = self.client.post(self.url('multibill-paid'),
                                    {'date_paid': '2026-04-02', 'paid_note': 'Check from SAO'})
        self.assertRedirects(response, self.url('multibill-detail'))
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.date_paid, datetime.date(2026, 4, 2))
        self.assertEqual(self.bill.paid_note, 'Check from SAO')

    def test_marking_paid_offers_the_day_the_money_arrived(self):
        event_income(self.first, '600.00', date=datetime.date(2026, 4, 10))
        event_income(self.second, '400.00', date=datetime.date(2026, 4, 17))
        response = self.client.get(self.url('multibill-paid'))
        self.assertEqual(response.context['form'].initial['date_paid'], datetime.date(2026, 4, 17))
        self.assertContains(response, 'That covers it')

    def test_marking_unpaid_opens_it_again(self):
        self.bill.date_paid = datetime.date(2026, 4, 1)
        self.bill.paid_note = 'Cash'
        self.bill.save()
        self.assertRedirects(self.client.post(self.url('multibill-unpaid')), self.url('multibill-detail'))
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)
        self.assertEqual(self.bill.paid_note, '')

    def test_the_invoice_shows_the_charges_and_the_total(self):
        charge(self.bill, MultiBillingCharge.RENTAL, 'Projector', unit_price=Decimal('100.00'),
               rental_fee_percent=Decimal('15'))
        self.bill.recalculate()
        self.user.user_permissions.add(Permission.objects.get(codename='view_event_billing'))
        response = self.client.get(self.url('multibill-pdf'), {'raw': 'true'})
        self.assertContains(response, 'Fall films')
        self.assertContains(response, 'Projector')
        self.assertContains(response, '$1,115.00')


class MultiBillInvoiceDrawingTests(ViewTestCase):
    """
    The invoice: laid out as the 2025 single-event invoice is, with the bill's
    own charges grouped as an event's are, and each event's own invoice after
    it when the bill says so.
    """

    def setUp(self):
        super(MultiBillInvoiceDrawingTests, self).setUp()
        self.user.user_permissions.add(Permission.objects.get(codename='bill_event'),
                                       Permission.objects.get(codename='view_event_billing'))
        self.socomm = OrgFactory(name='Social Committee', shortname='SocComm')
        self.first = priced_event('Film One', '500.00', org=self.socomm)
        self.second = priced_event('Film Two', '300.00', org=self.socomm)
        self.bill = multibill(self.first, self.second, org=self.socomm, name='Fall films',
                              description='The fall film series.')

    def html(self):
        return self.client.get(reverse('finance:multibill-pdf', args=(self.bill.pk,)), {'raw': 'true'})

    def pdf(self):
        with mock.patch('finance.views.billing.write_weasyprint_pdf', blank_page):
            return self.client.get(reverse('finance:multibill-pdf', args=(self.bill.pk,)))

    def test_it_is_drawn_like_the_single_event_invoice(self):
        response = self.html()
        # The same stylesheet and letterhead, and the same closing line
        self.assertContains(response, '#quote-box {')
        self.assertContains(response, 'WPI&nbsp;Lens&nbsp;and&nbsp;Lights')
        self.assertContains(response, '<h1 id="quote-box">INVOICE</h1>')
        self.assertContains(response, 'contact our treasurer')
        self.assertContains(response, 'Fall films')
        self.assertContains(response, 'The fall film series.')
        self.assertContains(response, 'Billed on: March 1, 2026')
        self.assertContains(response, 'Bill To:')
        # The events' total heads their section, and is the grand total too
        self.assertContains(response, '$800.00', count=2)

    def test_the_bills_charges_are_grouped_as_an_events_are(self):
        charge(self.bill, MultiBillingCharge.PERCENT, 'Series discount', percent=Decimal('-10'))
        charge(self.bill, MultiBillingCharge.RENTAL, 'Screen hire', quantity=2, unit_price=Decimal('40.00'))
        charge(self.bill, MultiBillingCharge.RENTAL, 'Projector hire', unit_price=Decimal('333.33'),
               rental_fee_percent=Decimal('15'))
        charge(self.bill, MultiBillingCharge.ONE_OFF, 'Credit for late start', unit_price=Decimal('-25.00'))
        self.bill.recalculate()
        response = self.html()
        body = response.content.decode()
        # A discount sits under the events it is a percentage of
        self.assertContains(response, 'Series discount (-10% of $800.00)')
        self.assertContains(response, '-$80.00')
        self.assertContains(response, '$720.00')
        # The rental carrying LNL's fee, then the fee, then the rest -- whatever order they were added in
        self.assertLess(body.index('Projector hire'), body.index('LNL Rental Fee'))
        self.assertLess(body.index('LNL Rental Fee'), body.index('Screen hire'))
        self.assertContains(response, '$49.99')
        self.assertContains(response, '$463.32')
        # A credit is written the way the 2025 invoice writes a discount
        self.assertContains(response, 'Additional Fees')
        self.assertContains(response, '-$25.00')
        self.assertContains(response, '$1,158.32')
        self.assertEqual(self.bill.amount, Decimal('1158.32'))

    def test_a_client_column_only_when_the_clients_differ(self):
        self.assertNotContains(self.html(), 'Organization</th>')
        self.bill.events.add(priced_event('Film Three', '100.00', org=OrgFactory(name='Lens and Lights')))
        self.assertContains(self.html(), 'Organization</th>')

    def test_sga_funded_events_are_marked(self):
        self.assertNotContains(self.html(), 'SGA-funded')
        self.bill.events.add(priced_event('Activities Fair', '40.00', org=self.socomm, is_sga_funded=True))
        response = self.html()
        self.assertContains(response, '<span class="sga-funded">SGA-funded</span>')
        self.assertContains(response, 'charged only for rentals and additional fees')

    def test_the_bills_own_page_alone_unless_it_says_otherwise(self):
        pages = PdfReader(BytesIO(self.pdf().content)).pages
        self.assertEqual(len(pages), 1)
        self.assertFalse(Quote.objects.exists())
        self.assertNotContains(self.html(), 'itemized invoice follows')

    def test_each_events_invoice_follows_when_asked(self):
        self.bill.attach_event_invoices = True
        self.bill.save()
        self.assertContains(self.html(), "Each event's itemized invoice follows")
        pages = PdfReader(BytesIO(self.pdf().content)).pages
        # The bill's own page first, then each event's invoice, earliest event first
        self.assertEqual(float(pages[0].mediabox.width), 200)
        self.assertEqual(len(pages), 3)
        self.assertIn('Film One', pages[1].extract_text())
        self.assertIn('Film Two', pages[2].extract_text())
        # Each made as billing the event alone makes it, which keeps a copy on the event
        self.assertEqual(sorted(Quote.objects.values_list('event', 'is_invoice')),
                         [(self.first.pk, True), (self.second.pk, True)])

    def test_the_file_is_named_after_the_bill(self):
        self.assertEqual(self.pdf()['Content-Disposition'], 'inline; filename="fall-films-bill.pdf"')
        self.bill.name = ''
        self.assertEqual(billing_views.multibill_invoice_name(self.bill), '2-events-for-soccomm-bill.pdf')

    def test_the_choice_is_made_when_creating_or_changing_the_bill(self):
        form = MultiBillForm({'events': [str(self.first.pk), str(self.second.pk)], 'date_billed': '2026-03-01',
                              'attach_event_invoices': 'on'}, instance=self.bill)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().attach_event_invoices)
        self.assertContains(self.client.get(reverse('finance:multibill-detail', args=(self.bill.pk,))),
                            "followed by each event's itemized")


@skipUnless(WEASYPRINT_DRAWS, "WeasyPrint cannot draw on this machine; it needs pango, which CI installs.")
class MultiBillInvoiceWeasyPrintTests(ViewTestCase):
    """ The invoice drawn for real, with each event's own invoice after it, old style and 2025 style. """

    def test_it_draws(self):
        self.user.user_permissions.add(Permission.objects.get(codename='view_event_billing'))
        org = OrgFactory(name='Social Committee', shortname='SocComm')
        bill = multibill(priced_event('Film One', '500.00', org=org),
                         priced_event('Film Two', '300.00', org=org, uses_new_discounts=True),
                         org=org, name='Fall films', attach_event_invoices=True)
        charge(bill, MultiBillingCharge.RENTAL, 'Projector hire', unit_price=Decimal('333.33'),
               rental_fee_percent=Decimal('15'))
        bill.recalculate()
        response = self.client.get(reverse('finance:multibill-pdf', args=(bill.pk,)))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(PdfReader(BytesIO(response.content)).pages), 3)


class MultiBillElsewhereInFinanceTests(TestCase):
    """ What the rest of finance makes of a multi-bill's charges and its client. """

    def setUp(self):
        self.socomm = OrgFactory(name='Social Committee', shortname='SocComm')
        self.lnl = OrgFactory(name='Lens and Lights', shortname='LNL')

    def test_a_hire_billed_on_the_multibill_counts_for_each_show(self):
        """
        $2,000 of gear for the whole run, plus the 15% fee, is $2,300: $1,150
        for each of two equally priced shows. The first show's hire cost
        $1,200, more than its share; the second's $1,000, less.
        """
        first = priced_event('Film One', '500.00', org=self.socomm)
        second = priced_event('Film Two', '500.00', org=self.socomm)
        bill = multibill(first, second, org=self.socomm)
        charge(bill, MultiBillingCharge.RENTAL, 'Projector', unit_price=Decimal('2000.00'),
               rental_fee_percent=Decimal('15'))
        bill.recalculate()
        cost(first, '-1200.00', 'C1')
        cost(second, '-1000.00', 'C2')
        figures = event_financials(first)
        self.assertEqual(figures['rentals_recovered'], Decimal('1150.00'))
        self.assertIn('rental_under_billed', figures['flag_keys'])
        self.assertNotIn('rental_under_billed', event_financials(second)['flag_keys'])

    def test_revenue_is_credited_to_who_the_bill_went_to(self):
        """ Two films booked under different clients, billed to one of them. """
        first = priced_event('Film One', '500.00', org=self.socomm)
        second = priced_event('Film Two', '500.00', org=self.lnl)
        multibill(first, second, org=self.socomm)
        event_income(first, '500.00')
        event_income(second, '500.00')
        clients = {row['label']: row['amount'] for row in revenue_by_client()}
        self.assertEqual(clients, {'SocComm': Decimal('1000.00')})

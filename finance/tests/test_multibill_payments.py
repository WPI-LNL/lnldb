"""
A payment for a multi-bill, linked to the bill rather than split by hand.

* **The rules.** Only money coming in may name a multi-bill, and an entry that
  names one names no event and no non-event source as well.
* **The shares.** Each event on the bill is credited with its share of the
  payment, by price, as the bill itself is split. Everything that reads what
  an event or a bill has received sees those shares: the P&L, what a bill has
  received, marking it paid, revenue by source and the Balances tab.
* **The suggestions.** The ISD number recorded on a multi-bill, or a memo
  naming one of its events for exactly its amount, fills the bill in; a
  multi-bill found by its amount alone is a chip.
* **The pages.** The queue files the payment and marks the bill paid, the
  ledger finds it from the bill and from each event, the entry page shows each
  event's share, and a bill with a payment linked cannot be deleted.
"""
import datetime
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from events.models import Event2019
from finance import balances
from finance.billing import mark_paid_from_payments
from finance.calculators import (bill_payments, event_financials, event_pnl_rows,
                                 multibill_income, received_by_event, revenue_by_source)
from finance.forms import ReconcileForm
from finance.models import MultiBilling, ParsedTransaction, TransactionStatus
from finance.suggestions import EXPORT, GUESS, MEMO, suggest_all
from finance.tests.test_bill_payments import payment
from finance.tests.test_billing_page import show
from finance.tests.test_revenue_sources import CacheResetMixin
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import fund, revenue_source

PAID_IN = datetime.date(2025, 10, 15)


class MultibillFixture(object):
    """ Two films on one $300 multi-bill, and a payment for it not yet filed. """

    def build(self):
        self.films = [show('Film 1', start=datetime.date(2025, 9, 10)),
                      show('Film 2', start=datetime.date(2025, 9, 12))]
        self.bill = MultiBilling.objects.create(name='Fall films', amount=Decimal('300.00'),
                                                date_billed=datetime.date(2025, 9, 20))
        self.bill.events.set(self.films)

    def line(self, amount='300.00', number='25100001-ISD', memo='Lens and Lights services'):
        return payment(number, amount, PAID_IN, memo=memo)

    def linked(self, amount='300.00', **extra):
        """ A payment filed against the bill, as the queue files it. """
        fields = dict(parent_transaction=self.line(amount), amount=Decimal(amount),
                      effective_date=PAID_IN, status=TransactionStatus.SETTLED,
                      linked_multibill=self.bill, fund_source=fund('legacy'))
        fields.update(extra)
        return ParsedTransaction.objects.create(**fields)


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

class RuleTests(MultibillFixture, CacheResetMixin, TestCase):

    def setUp(self):
        super(RuleTests, self).setUp()
        self.build()

    def entry(self, amount='300.00', **extra):
        fields = dict(parent_transaction=self.line(), amount=Decimal(amount), effective_date=PAID_IN,
                      linked_multibill=self.bill, fund_source=fund('legacy'))
        fields.update(extra)
        return ParsedTransaction(**fields)

    def test_a_payment_may_name_the_bill_alone(self):
        self.entry().full_clean()

    def test_not_an_event_as_well(self):
        with self.assertRaises(ValidationError) as caught:
            self.entry(linked_event=self.films[0]).full_clean()
        self.assertIn('linked_multibill', caught.exception.message_dict)

    def test_not_a_non_event_source_as_well(self):
        with self.assertRaises(ValidationError) as caught:
            self.entry(non_event_revenue_type=revenue_source('donations')).full_clean()
        self.assertIn('non_event_revenue_type', caught.exception.message_dict)

    def test_an_expense_cannot_name_one(self):
        with self.assertRaises(ValidationError) as caught:
            self.entry(amount='-300.00').full_clean()
        self.assertIn('linked_multibill', caught.exception.message_dict)

    def test_the_database_refuses_an_event_as_well(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.entry(linked_event=self.films[0]).save()

    def test_the_database_refuses_an_expense(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.entry(amount='-300.00').save()


# ---------------------------------------------------------------------------
# The shares, and everything that reads them
# ---------------------------------------------------------------------------

class ShareTests(MultibillFixture, CacheResetMixin, TestCase):

    def setUp(self):
        super(ShareTests, self).setUp()
        self.build()

    def shares(self, entries=None):
        return [(event.pk, share) for _, event, share
                in multibill_income(entries or ParsedTransaction.objects.all())]

    def test_with_no_prices_the_events_share_evenly(self):
        self.linked()
        self.assertEqual(self.shares(), [(self.films[0].pk, Decimal('150.00')),
                                         (self.films[1].pk, Decimal('150.00'))])

    def test_the_shares_follow_each_events_price(self):
        self.linked()
        prices = {self.films[0].pk: Decimal('100.00'), self.films[1].pk: Decimal('200.00')}
        with mock.patch.object(Event2019, 'cost_total', property(lambda event: prices[event.pk])):
            self.assertEqual(self.shares(), [(self.films[0].pk, Decimal('100.00')),
                                             (self.films[1].pk, Decimal('200.00'))])

    def test_an_event_paid_for_separately_is_not_counted_twice(self):
        """ Only payments linked to the bill are shared out. """
        ParsedTransaction.objects.create(
            parent_transaction=self.line(), amount=Decimal('300.00'), effective_date=PAID_IN,
            status=TransactionStatus.SETTLED, linked_event=self.films[0], fund_source=fund('legacy'))
        self.assertEqual(self.shares(), [])

    def test_each_event_has_received_its_share(self):
        self.linked()
        self.assertEqual(received_by_event([self.films[0].pk]),
                         {self.films[0].pk: (Decimal('150.00'), PAID_IN)})

    def test_the_bill_has_received_the_payment(self):
        self.linked()
        self.assertEqual(bill_payments(self.bill), (Decimal('300.00'), PAID_IN))

    def test_a_part_payment_and_a_payment_split_by_hand_add_up(self):
        self.linked('100.00')
        ParsedTransaction.objects.create(
            parent_transaction=self.line('200.00', number='25100002-ISD'), amount=Decimal('200.00'),
            effective_date=PAID_IN, status=TransactionStatus.SETTLED, linked_event=self.films[1],
            fund_source=fund('legacy'))
        self.assertEqual(bill_payments(self.bill), (Decimal('300.00'), PAID_IN))

    def test_it_covers_the_bill_so_the_bill_can_be_marked_paid(self):
        self.linked()
        self.assertEqual(mark_paid_from_payments(self.bill), PAID_IN)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.date_paid, PAID_IN)

    def test_each_events_pnl_counts_its_share(self):
        self.linked()
        self.assertEqual(event_financials(self.films[0])['received'], Decimal('150.00'))
        rows = {row['event'].pk: row for row in event_pnl_rows(fiscal_year=2026)}
        self.assertEqual({pk: (row['received'], row['entries']) for pk, row in rows.items()},
                         {self.films[0].pk: (Decimal('150.00'), 1),
                          self.films[1].pk: (Decimal('150.00'), 1)})

    def test_the_pnl_counts_it_in_the_year_each_event_ran(self):
        self.linked()
        self.assertEqual(event_pnl_rows(fiscal_year=2025), [])

    def test_it_is_event_billing(self):
        self.linked()
        rows = {row['key']: row['amount'] for row in revenue_by_source(fiscal_year=2026)}
        self.assertEqual(rows.get('event'), Decimal('300.00'))

    def test_the_balances_count_each_events_share_as_paid_in(self):
        self.linked('100.00')
        books = balances.Books()
        payments = {item.event.pk: item.payments for item in books.billed_events}
        self.assertEqual(payments[self.films[0].pk], [(PAID_IN, Decimal('50.00'))])
        unpaid = books.billed_unpaid(books.billing_account, datetime.date(2025, 10, 31))
        self.assertEqual(sum(bill.owed for bill in unpaid), Decimal('200.00'))


# ---------------------------------------------------------------------------
# The suggestions
# ---------------------------------------------------------------------------

class SuggestionTests(MultibillFixture, CacheResetMixin, TestCase):

    def setUp(self):
        super(SuggestionTests, self).setUp()
        self.build()

    def test_the_isd_number_on_the_bill_fills_it_in(self):
        self.bill.isd_number = '25100001-ISD'
        self.bill.save()
        suggestions = suggest_all(self.line())
        self.assertEqual(suggestions['linked_multibill'].value, self.bill.pk)
        self.assertEqual(suggestions['linked_multibill'].source, EXPORT)
        self.assertIsNone(suggestions['linked_event'])
        form = ReconcileForm(parent_transaction=self.line(), prefix='t')
        self.assertEqual(form.initial['linked_multibill'], self.bill.pk)
        self.assertNotIn('linked_event', form.initial)

    def test_a_memo_naming_one_of_its_events_fills_it_in_not_the_event(self):
        suggestions = suggest_all(self.line(memo='Lens and Lights services for Film 1'))
        self.assertEqual(suggestions['linked_multibill'].value, self.bill.pk)
        self.assertEqual(suggestions['linked_multibill'].source, MEMO)
        self.assertIsNone(suggestions['linked_event'])

    def test_the_amount_alone_is_only_a_guess(self):
        suggestions = suggest_all(self.line())
        self.assertEqual(suggestions['linked_multibill'].value, self.bill.pk)
        self.assertEqual(suggestions['linked_multibill'].source, GUESS)
        form = ReconcileForm(parent_transaction=self.line(), prefix='t')
        self.assertNotIn('linked_multibill', form.initial)

    def test_an_expense_has_no_multibill_box(self):
        line = payment('25100009-ISD', '-50.00', PAID_IN)
        self.assertNotIn('linked_multibill', ReconcileForm(parent_transaction=line, prefix='t').fields)


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class PageTests(MultibillFixture, CacheResetMixin, FinanceViewTestCase):

    def setUp(self):
        super(PageTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger', 'bill_event', 'view_events')
        self.build()
        self.bill.isd_number = '25100001-ISD'
        self.bill.save()

    def test_the_queue_fills_it_in_and_offers_to_mark_it_paid(self):
        self.line()
        response = self.client.get(reverse('finance:queue'), {'fy': 'all'})
        self.assertContains(response, 'or Multi-bill')
        self.assertContains(response, 'name="mark_multibill_paid" value="%s" checked' % self.bill.pk)
        self.assertContains(response, 'Mark multi-bill paid on')

    def test_filing_it_from_the_queue_marks_the_bill_paid(self):
        line = self.line()
        response = self.client.post(reverse('finance:reconcile', args=[line.pk]), {
            'txn%s-linked_multibill' % line.pk: str(self.bill.pk),
            'txn%s-fund_source' % line.pk: str(fund('legacy').pk),
            'mark_multibill_paid': str(self.bill.pk), 'bill_offered': str(self.bill.pk),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        entry = line.slices.get()
        self.assertEqual((entry.linked_multibill, entry.linked_event), (self.bill, None))
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.date_paid, PAID_IN)
        self.assertIn('Marked Fall films paid on', response.json()['message'])

    def test_the_ledger_finds_it_from_each_event_and_from_the_bill(self):
        entry = self.linked()
        for params in ({'event': self.films[1].pk}, {'multibill': self.bill.pk}):
            response = self.client.get(reverse('finance:ledger'), params)
            self.assertIn(entry, list(response.context['page_obj']), params)
        self.assertContains(response, 'Showing entries for the multi-bill')

    def test_the_entry_page_shows_each_events_share(self):
        entry = self.linked()
        response = self.client.get(reverse('finance:entry-detail', args=[entry.pk]))
        self.assertContains(response, 'Payment for a multi-bill')
        self.assertEqual([(event.pk, share) for event, share in response.context['multibill_shares']],
                         [(self.films[0].pk, Decimal('150.00')), (self.films[1].pk, Decimal('150.00'))])

    def test_a_bill_with_a_payment_linked_cannot_be_deleted(self):
        self.linked()
        response = self.client.post(reverse('finance:multibill-delete', args=[self.bill.pk]))
        self.assertRedirects(response, reverse('finance:multibill-detail', args=[self.bill.pk]),
                             fetch_redirect_response=False)
        self.assertTrue(MultiBilling.objects.filter(pk=self.bill.pk).exists())

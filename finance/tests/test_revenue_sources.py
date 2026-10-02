"""
Revenue sources, SGA's payments for funding requests, and what LNL is owed.

Five layers, tested from the bottom up:

* **The rules.** A revenue source can name the fund its money goes into, and
  then decides it. Money in a fund that draws on funding requests names the
  request SGA is paying for -- on the way in a reimbursement, on the way out
  money SGA took back -- and never one of the request's lines as well.
* **What SGA owes.** Spending that has reached Workday, less what SGA has paid
  for it, plus whatever was owed when the books started; aged by the oldest
  spending still unpaid.
* **The suggestions.** An SGA journal entry quoting a request fills the
  source, the request and the fund; a supplier's credit quoting one does not;
  money SGA takes back is offered as such; an ISD naming no event says so; a
  deposit matching a multi-bill offers to split it.
* **The figures.** Revenue by source, event billing net of what was passed
  through, new and returning clients, and both kinds of receivable.
* **The pages**, including marking a bill paid from the event P&L.
"""
import datetime
import importlib
from decimal import Decimal

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from events.models import Billing, MultiBilling
from events.tests.generators import Event2019Factory, OrgFactory
from finance.calculators import (billing_receivables, client_retention, event_billing_kept,
                                 event_financials, event_pnl_rows, revenue_by_source,
                                 sga_receivables)
from finance.forms import AllocationForm, ReconcileForm, SplitFormSet
from finance.models import (FRLineItem, FundingRequest, ParsedTransaction, RevenueSource,
                            TransactionStatus, WorkdayTransaction, reimbursement_source,
                            reset_finance_cache, revenue_sources_by_fund)
from finance.suggestions import (EXPORT, GUESS, MEMO, is_sga_transfer, suggest_all,
                                 suggest_multibill)
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund, revenue_source

MAIN = '226-AG Lens & Light Club'
JOURNAL = '26060012-JE - Worcester Polytechnic Institute - WPI - 06/12/2026'


def sga_line(memo, amount, date=datetime.date(2026, 6, 12), **worktags):
    """ SGA moving money: a journal entry on 74600 that names nobody. """
    tags = {'student_organization': MAIN, 'journal': JOURNAL,
            'ledger_account': '74600:Event Sponsorship'}
    tags.update(worktags)
    return WorkdayTransaction.objects.create(
        operational_transaction='', accounting_date=date, net_amount=Decimal(amount),
        memo=memo, worktags_json=tags)


def supplier_line(memo, amount, date=datetime.date(2026, 8, 22), **worktags):
    """ A supplier invoice line on the main account. """
    tags = {'student_organization': MAIN, 'ledger_account': '71100:Supplies'}
    tags.update(worktags)
    return WorkdayTransaction.objects.create(
        operational_transaction='Supplier Invoice: 26080001-SIN-%s' % amount,
        accounting_date=date, net_amount=Decimal(amount), memo=memo,
        supplier='Amazon Capital Services, Inc.', worktags_json=tags)


def isd_line(memo, amount, date=datetime.date(2026, 5, 15)):
    """ LNL billing a client: an Internal Service Delivery. """
    return WorkdayTransaction.objects.create(
        operational_transaction='Internal Service Delivery: 26050001-ISD-%s' % amount,
        accounting_date=date, net_amount=Decimal(amount), memo=memo,
        worktags_json={'student_organization': MAIN,
                       'ledger_account': '70050:Internal Service Provider Revenue'})


def make_request(reference='F.26.86', name='Film Posters and Concessions', fiscal_year=2026,
                 **kwargs):
    """ A request with one line, which is all spending against it needs. """
    request = FundingRequest.objects.create(name=name, reference=reference,
                                            fiscal_year=fiscal_year, **kwargs)
    FRLineItem.objects.create(funding_request=request, name='Posters',
                              amount_awarded=Decimal('20000.00'))
    return request


def spend(request, amount, date, encumbrance=False):
    """ Spending against the request's line: on a bank line, or only reserved. """
    line = request.line_items.first()
    if encumbrance:
        return ParsedTransaction.objects.create(
            amount=-Decimal(amount), effective_date=date, fund_source=fund('sga_fr'),
            fr_line_target=line, lnl_spend_category=category('consumables'))
    txn = supplier_line('Posters (%s)' % request.reference, '-%s' % amount, date=date)
    return ParsedTransaction.objects.create(
        parent_transaction=txn, amount=-Decimal(amount), effective_date=date,
        status=TransactionStatus.SETTLED, fund_source=fund('sga_fr'), fr_line_target=line,
        lnl_spend_category=category('consumables'))


def reimburse(request, amount, date=datetime.date(2026, 6, 12)):
    """ SGA paying the request back, filed as such. """
    txn = sga_line('%s %s' % (request.reference, request.name), amount, date=date)
    return ParsedTransaction.objects.create(
        parent_transaction=txn, amount=Decimal(amount), effective_date=date,
        status=TransactionStatus.SETTLED, fund_source=fund('sga_fr'),
        non_event_revenue_type=revenue_source('sga_fr_reimbursement'),
        funding_request=request)


def take_back(request, amount, date=datetime.date(2025, 7, 1)):
    """ SGA reclaiming money it paid for the request. """
    txn = sga_line('SGA FR %s was doubled paid to 226-AG' % request.reference,
                   '-%s' % amount, date=date)
    return ParsedTransaction.objects.create(
        parent_transaction=txn, amount=-Decimal(amount), effective_date=date,
        status=TransactionStatus.SETTLED, fund_source=fund('sga_fr'),
        funding_request=request)


def when(year, month, day):
    return datetime.datetime(year, month, day, 19, 0, tzinfo=datetime.timezone.utc)


def make_event(name, start, **kwargs):
    event = Event2019Factory(event_name=name, **kwargs)
    event.datetime_start = start
    event.datetime_end = start + datetime.timedelta(hours=3)
    event.save()
    return event


def event_income(event, amount, date=datetime.date(2026, 5, 15)):
    """ A deposit filed against an event. """
    txn = isd_line('Lens and Lights Services for %s' % event.event_name, amount, date=date)
    return ParsedTransaction.objects.create(
        parent_transaction=txn, amount=Decimal(amount), effective_date=date,
        status=TransactionStatus.SETTLED, linked_event=event, fund_source=fund('legacy'))


class CacheResetMixin(object):
    """ Cached table reads outlive a test's rollback; start each test clean. """

    def setUp(self):
        super(CacheResetMixin, self).setUp()
        reset_finance_cache()


# ---------------------------------------------------------------------------
# The seeded sources
# ---------------------------------------------------------------------------

class SeededSourceTests(CacheResetMixin, TestCase):
    """ SGA's three kinds of payment, each into its own fund. """

    def test_each_sga_source_names_its_fund(self):
        self.assertEqual(revenue_source('sga_fr_reimbursement').credits_fund, fund('sga_fr'))
        self.assertEqual(revenue_source('sga_baseline').credits_fund, fund('sga_budget'))
        self.assertEqual(revenue_source('sga_mandatory').credits_fund, fund('sga_mandatory'))

    def test_the_baseline_is_the_sga_budget(self):
        self.assertEqual(revenue_source('sga_baseline').name, 'SGA Budget')

    def test_a_gift_is_simply_the_accounts_own_money(self):
        self.assertIsNone(revenue_source('alumni').credits_fund)
        self.assertIsNone(revenue_source('asset_liquidation').credits_fund)

    def test_the_reimbursement_source_is_the_one_whose_fund_draws_on_requests(self):
        self.assertEqual(reimbursement_source(), revenue_source('sga_fr_reimbursement'))
        self.assertTrue(revenue_source('sga_fr_reimbursement').repays_funding_requests)
        self.assertFalse(revenue_source('sga_baseline').repays_funding_requests)

    def test_retiring_it_leaves_nothing_to_offer(self):
        source = revenue_source('sga_fr_reimbursement')
        source.is_active = False
        source.save()
        self.assertIsNone(reimbursement_source())

    def test_sources_are_indexed_by_fund(self):
        index = revenue_sources_by_fund()
        self.assertEqual(index[fund('sga_budget').pk], [revenue_source('sga_baseline')])
        self.assertNotIn(fund('legacy').pk, index)


class MigrationTests(CacheResetMixin, TestCase):
    """ 0006 and 0007 reconcile a database that ran the original seed, keeping edits. """

    def setUp(self):
        super(MigrationTests, self).setUp()
        self.migration = importlib.import_module('finance.migrations.0006_revenue_sources')

    def _as_originally_seeded(self):
        RevenueSource.objects.filter(slug__in=('sga_fr_reimbursement', 'sga_mandatory')).delete()
        RevenueSource.objects.filter(slug='sga_baseline').update(
            name='SGA Baseline', sort_order=0, credits_fund=None, description='')
        RevenueSource.objects.filter(slug='asset_liquidation').update(sort_order=1)
        RevenueSource.objects.filter(slug='alumni').update(sort_order=2)

    def test_an_untouched_install_gets_the_new_names_order_and_funds(self):
        self._as_originally_seeded()
        self.migration.describe_revenue_sources(django_apps, None)
        self.assertEqual([s.slug for s in RevenueSource.objects.all()],
                         ['sga_fr_reimbursement', 'sga_baseline', 'sga_mandatory',
                          'asset_liquidation', 'alumni'])
        self.assertEqual(revenue_source('sga_baseline').name, 'SGA Budget')
        self.assertEqual(revenue_source('sga_baseline').credits_fund, fund('sga_budget'))
        self.assertEqual(revenue_source('sga_fr_reimbursement').credits_fund, fund('sga_fr'))

    def test_a_treasurers_own_name_and_order_are_kept(self):
        self._as_originally_seeded()
        RevenueSource.objects.filter(slug='sga_baseline').update(name='SGA Annual Budget',
                                                                 sort_order=7)
        self.migration.describe_revenue_sources(django_apps, None)
        source = revenue_source('sga_baseline')
        self.assertEqual((source.name, source.sort_order), ('SGA Annual Budget', 7))

    def test_a_chosen_fund_is_not_overwritten(self):
        RevenueSource.objects.filter(slug='sga_baseline').update(credits_fund=fund('legacy'))
        self.migration.describe_revenue_sources(django_apps, None)
        self.assertEqual(revenue_source('sga_baseline').credits_fund, fund('legacy'))

    def test_0007_renames_the_name_0006_used_to_give(self):
        RevenueSource.objects.filter(slug='sga_baseline').update(name='SGA Budget Deposit')
        importlib.import_module('finance.migrations.0007_sga_budget_source_name').rename(
            django_apps, None)
        self.assertEqual(revenue_source('sga_baseline').name, 'SGA Budget')

    def test_0007_keeps_a_treasurers_own_name(self):
        RevenueSource.objects.filter(slug='sga_baseline').update(name='SGA Annual Budget')
        importlib.import_module('finance.migrations.0007_sga_budget_source_name').rename(
            django_apps, None)
        self.assertEqual(revenue_source('sga_baseline').name, 'SGA Annual Budget')

    def test_0007_never_takes_a_name_another_source_has(self):
        RevenueSource.objects.filter(slug='sga_baseline').update(name='SGA Budget Deposit')
        RevenueSource.objects.filter(slug='alumni').update(name='SGA Budget')
        importlib.import_module('finance.migrations.0007_sga_budget_source_name').rename(
            django_apps, None)
        self.assertEqual(revenue_source('sga_baseline').name, 'SGA Budget Deposit')

    def test_reimbursements_already_filed_are_given_their_request(self):
        request = make_request()
        txn = sga_line('F.26.86 Film Posters and Concessions', '500.00')
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=Decimal('500.00'), effective_date=txn.accounting_date,
            fund_source=fund('sga_fr'), non_event_revenue_type=revenue_source('alumni'))
        self.migration.link_reimbursements(django_apps, None)
        entry.refresh_from_db()
        self.assertEqual(entry.funding_request, request)


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

class SourceDecidesFundTests(CacheResetMixin, TestCase):
    """ SGA pays each kind of money into its own pot. """

    def setUp(self):
        super(SourceDecidesFundTests, self).setUp()
        self.txn = sga_line('FY27 SGA budget', '30000.00', tracking='SGA Budget')

    def _entry(self, **kwargs):
        return ParsedTransaction(parent_transaction=self.txn, amount=Decimal('30000.00'),
                                 **kwargs)

    def test_a_blank_fund_is_filled_from_the_source(self):
        entry = self._entry(non_event_revenue_type=revenue_source('sga_baseline'))
        entry.full_clean()
        self.assertEqual(entry.fund_source, fund('sga_budget'))

    def test_a_disagreeing_fund_is_refused_by_name(self):
        entry = self._entry(non_event_revenue_type=revenue_source('sga_baseline'),
                            fund_source=fund('legacy'))
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn('SGA Budget goes into SGA Budget, not Legacy',
                      str(caught.exception.message_dict['fund_source']))

    def test_a_source_with_no_fund_takes_any(self):
        entry = self._entry(non_event_revenue_type=revenue_source('alumni'),
                            fund_source=fund('legacy'))
        entry.full_clean()


class SGAPaymentRuleTests(CacheResetMixin, TestCase):
    """ What SGA pays for a request names the request, and never one of its lines. """

    def setUp(self):
        super(SGAPaymentRuleTests, self).setUp()
        self.request = make_request()

    def test_a_reimbursement_names_the_request(self):
        txn = sga_line('F.26.86 Film Posters', '500.00')
        entry = ParsedTransaction(parent_transaction=txn, amount=Decimal('500.00'),
                                  non_event_revenue_type=revenue_source('sga_fr_reimbursement'),
                                  funding_request=self.request)
        entry.full_clean()
        self.assertEqual(entry.fund_source, fund('sga_fr'))

    def test_without_it_the_request_could_never_be_credited(self):
        txn = sga_line('F.26.86 Film Posters', '500.00')
        entry = ParsedTransaction(parent_transaction=txn, amount=Decimal('500.00'),
                                  non_event_revenue_type=revenue_source('sga_fr_reimbursement'))
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn('has to name the request SGA is reimbursing',
                      str(caught.exception.message_dict['funding_request']))

    def test_only_a_fund_that_draws_on_requests_can_be_paid_for_one(self):
        txn = sga_line('F.26.86 Film Posters', '500.00')
        entry = ParsedTransaction(parent_transaction=txn, amount=Decimal('500.00'),
                                  non_event_revenue_type=revenue_source('alumni'),
                                  fund_source=fund('legacy'), funding_request=self.request)
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn('Legacy does not', str(caught.exception.message_dict['funding_request']))

    def test_money_taken_back_names_the_request_and_needs_no_line(self):
        entry = take_back(self.request, '15000.00')
        entry.full_clean()
        self.assertTrue(entry.is_sga_return)
        self.assertEqual(entry.entry_type, ParsedTransaction.EXPENSE)

    def test_spending_still_needs_a_line(self):
        txn = supplier_line('Posters', '-50.00')
        entry = ParsedTransaction(parent_transaction=txn, amount=Decimal('-50.00'),
                                  fund_source=fund('sga_fr'))
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn('name the request under SGA funding request',
                      str(caught.exception.message_dict['fr_line_target']))

    def test_a_line_and_a_request_together_are_refused(self):
        txn = supplier_line('Posters', '-50.00')
        entry = ParsedTransaction(parent_transaction=txn, amount=Decimal('-50.00'),
                                  fund_source=fund('sga_fr'),
                                  fr_line_target=self.request.line_items.first(),
                                  funding_request=self.request)
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn('already names its request',
                      str(caught.exception.message_dict['funding_request']))

    def test_the_database_refuses_a_line_and_a_request_together(self):
        txn = supplier_line('Posters', '-50.00')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParsedTransaction.objects.create(
                    parent_transaction=txn, amount=Decimal('-50.00'), fund_source=fund('sga_fr'),
                    fr_line_target=self.request.line_items.first(),
                    funding_request=self.request)

    def test_an_encumbrance_cannot_be_a_reimbursement(self):
        entry = ParsedTransaction(amount=Decimal('-50.00'), fund_source=fund('sga_fr'),
                                  funding_request=self.request)
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn('encumbrance', str(caught.exception.message_dict['funding_request']))

    def test_a_projection_request_makes_its_payment_projection_money(self):
        self.request.is_projection = True
        self.request.save()
        entry = reimburse(self.request, '500.00')
        entry.refresh_from_db()
        self.assertTrue(entry.is_projection)


# ---------------------------------------------------------------------------
# What SGA owes
# ---------------------------------------------------------------------------

class AwaitingSGATests(CacheResetMixin, TestCase):
    """ Spending that reached Workday, less what SGA paid for it. """

    def setUp(self):
        super(AwaitingSGATests, self).setUp()
        self.request = make_request()

    def test_nothing_spent_is_nothing_owed(self):
        self.assertEqual(self.request.awaiting_sga, Decimal('0.00'))
        self.assertEqual(self.request.reimbursement_status, 'Nothing spent yet')

    def test_only_spending_in_workday_is_owed(self):
        spend(self.request, '100.00', datetime.date(2025, 9, 1))
        spend(self.request, '400.00', datetime.date(2025, 9, 2), encumbrance=True)
        self.assertEqual(self.request.total_spent, Decimal('500.00'))
        self.assertEqual(self.request.total_charged, Decimal('100.00'))
        self.assertEqual(self.request.awaiting_sga, Decimal('100.00'))
        self.assertEqual(self.request.reimbursement_status, 'Awaiting $100.00 from SGA')

    def test_a_refund_unspends(self):
        purchase = spend(self.request, '100.00', datetime.date(2025, 9, 1))
        credit = supplier_line('Posters returned', '30.00', date=datetime.date(2025, 9, 5))
        ParsedTransaction.objects.create(
            parent_transaction=credit, amount=Decimal('30.00'), refund_of=purchase,
            effective_date=credit.accounting_date, fund_source=fund('sga_fr'),
            fr_line_target=purchase.fr_line_target, lnl_spend_category=category('consumables'))
        self.assertEqual(self.request.awaiting_sga, Decimal('70.00'))

    def test_reimbursement_and_money_taken_back_net(self):
        spend(self.request, '100.00', datetime.date(2025, 9, 1))
        reimburse(self.request, '100.00')
        reimburse(self.request, '100.00', date=datetime.date(2026, 6, 13))
        self.assertEqual(self.request.reimbursement_status, 'SGA overpaid by $100.00')
        take_back(self.request, '100.00', date=datetime.date(2026, 7, 1))
        self.assertEqual(self.request.total_received, Decimal('100.00'))
        self.assertEqual(self.request.reimbursement_status, 'Fully reimbursed')

    def test_what_was_owed_when_the_books_started_counts(self):
        """ The doubled F.25.33 payment: overpaid at the start, then taken back. """
        self.request.owed_at_books_start = Decimal('-15000.00')
        self.request.save()
        self.assertEqual(self.request.awaiting_sga, Decimal('-15000.00'))
        take_back(self.request, '15000.00')
        self.assertEqual(self.request.awaiting_sga, Decimal('0.00'))

    def test_the_listing_annotation_agrees_with_the_properties(self):
        spend(self.request, '100.00', datetime.date(2025, 9, 1))
        spend(self.request, '40.00', datetime.date(2025, 9, 2), encumbrance=True)
        reimburse(self.request, '60.00')
        annotated = FundingRequest.objects.with_totals().get(pk=self.request.pk)
        self.assertEqual((annotated.total_charged, annotated.total_received,
                          annotated.awaiting_sga),
                         (Decimal('100.00'), Decimal('60.00'), Decimal('40.00')))

    def test_the_oldest_unpaid_spending_is_what_ages(self):
        """ Payments settle the oldest charges first. """
        spend(self.request, '100.00', datetime.date(2025, 9, 1))
        spend(self.request, '50.00', datetime.date(2025, 10, 1))
        self.assertEqual(self.request.unreimbursed_since(), datetime.date(2025, 9, 1))
        reimburse(self.request, '120.00')
        self.assertEqual(self.request.unreimbursed_since(), datetime.date(2025, 10, 1))
        reimburse(self.request, '30.00', date=datetime.date(2026, 6, 20))
        self.assertIsNone(self.request.unreimbursed_since())

    def test_the_picker_says_what_is_owed(self):
        spend(self.request, '100.00', datetime.date(2025, 9, 1))
        self.assertEqual(self.request.picker_label,
                         'FY26 · F.26.86 Film Posters and Concessions — awaiting $100.00 from sga')


class ReceivableTests(CacheResetMixin, TestCase):
    """ Every request SGA owes on, checked against the fund that holds the money. """

    def test_requests_and_the_fund_agree(self):
        request = make_request()
        spend(request, '100.00', datetime.date(2025, 9, 1))
        reimburse(request, '60.00', date=datetime.date(2025, 12, 1))
        owed = sga_receivables()
        self.assertEqual([r['request'] for r in owed['rows']], [request])
        self.assertEqual(owed['owed'], Decimal('40.00'))
        self.assertEqual(owed['fund_owed'], Decimal('40.00'))
        self.assertEqual(owed['difference'], Decimal('0.00'))
        self.assertEqual(owed['rows'][0]['since'], datetime.date(2025, 9, 1))

    def test_an_opening_figure_on_one_side_only_shows_as_a_difference(self):
        request = make_request(owed_at_books_start=Decimal('25.00'))
        spend(request, '100.00', datetime.date(2025, 9, 1))
        owed = sga_receivables()
        self.assertEqual(owed['owed'], Decimal('125.00'))
        self.assertEqual(owed['difference'], Decimal('25.00'))

    def test_paid_up_requests_are_left_out(self):
        request = make_request()
        spend(request, '100.00', datetime.date(2025, 9, 1))
        reimburse(request, '100.00')
        self.assertEqual(sga_receivables()['rows'], [])


# ---------------------------------------------------------------------------
# The suggestions
# ---------------------------------------------------------------------------

class SGATransferTests(CacheResetMixin, TestCase):
    """ SGA moves money with a journal entry naming nobody, quoting the request. """

    def test_a_journal_entry_quoting_a_request_is_sga(self):
        self.assertTrue(is_sga_transfer(sga_line('F.26.86 Film Posters', '500.00')))

    def test_a_suppliers_credit_quoting_one_is_not(self):
        self.assertFalse(is_sga_transfer(
            supplier_line('Solder wick, Consumables, (A.27.16)', '8.78')))

    def test_a_journal_entry_quoting_nothing_is_not(self):
        self.assertFalse(is_sga_transfer(sga_line('308556: Alien Posters for LNL', '-90.54')))


class ReimbursementSuggestionTests(CacheResetMixin, TestCase):
    """ The number in SGA's memo fills the source, the request and the fund. """

    def setUp(self):
        super(ReimbursementSuggestionTests, self).setUp()
        self.request = make_request()

    def test_all_three_are_filled_in(self):
        txn = sga_line('F.26.86 Film Posters and Concessions', '10837.59')
        form = ReconcileForm(parent_transaction=txn, prefix='t')
        self.assertEqual(form.initial['non_event_revenue_type'],
                         revenue_source('sga_fr_reimbursement').pk)
        self.assertEqual(form.initial['funding_request'], self.request.pk)
        self.assertEqual(form.initial['fund_source'], fund('sga_fr').pk)
        self.assertEqual(form.autofilled['funding_request'].source, MEMO)

    def test_a_closed_request_is_still_found(self):
        self.request.closed = True
        self.request.save()
        txn = sga_line('F.26.86 Film Posters and Concessions', '10837.59')
        self.assertEqual(suggest_all(txn)['funding_request'].value, self.request.pk)

    def test_a_request_lnldb_lacks_is_offered_to_add(self):
        txn = sga_line('F.26.195 Campus Movies', '2873.08')
        found = suggest_all(txn)
        self.assertIsNone(found['funding_request'])
        self.assertIn('F.26.195', found['warning'])
        self.assertEqual(found['unknown_request'],
                         {'reference': 'F.26.195', 'name': 'Campus Movies',
                          'fiscal_year': 2026})

    def test_another_bodys_letter_is_a_chip_not_a_fill(self):
        txn = sga_line('A.26.86 Film Posters and Concessions', '500.00')
        found = suggest_all(txn)
        self.assertEqual(found['funding_request'].source, GUESS)
        self.assertEqual(found['near_miss'], self.request)
        form = ReconcileForm(parent_transaction=txn, prefix='t', suggestions=found)
        self.assertNotIn('funding_request', form.autofilled)

    def test_a_suppliers_credit_is_not_called_a_reimbursement(self):
        """ Tracked to the funding-request fund, and still a refund. """
        txn = supplier_line('Solder wick, Consumables, (A.27.16)', '8.78',
                            tracking='SGA Funding Request')
        found = suggest_all(txn)
        self.assertIsNone(found['revenue_source'])
        self.assertIsNone(found['funding_request'])
        self.assertEqual(found['warning'], '')

    def test_a_deposit_tracked_to_the_budget_is_the_budget_deposit(self):
        txn = sga_line('FY27 SGA budget allocation', '30000.00', tracking='SGA Budget')
        found = suggest_all(txn)
        self.assertEqual(found['revenue_source'].value, revenue_source('sga_baseline').pk)
        self.assertEqual(found['revenue_source'].source, EXPORT)

    def test_an_account_default_says_nothing_about_the_source(self):
        txn = sga_line('Something', '30.00')
        self.assertIsNone(suggest_all(txn)['revenue_source'])


class SGAReturnSuggestionTests(CacheResetMixin, TestCase):
    """ SGA taking back a payment it made twice. """

    def setUp(self):
        super(SGAReturnSuggestionTests, self).setUp()
        self.request = make_request(reference='F.25.33', name='Gear', fiscal_year=2025)
        self.txn = sga_line('SGA FR F.25.33 was doubled paid to 226-AG', '-15000.00',
                            date=datetime.date(2025, 7, 1))

    def test_the_request_and_fund_are_filled_and_nothing_else(self):
        found = suggest_all(self.txn)
        self.assertTrue(found['sga_return'])
        self.assertEqual(found['funding_request'].value, self.request.pk)
        self.assertEqual(found['fund_source'].value, fund('sga_fr').pk)
        self.assertIsNone(found['fr_line_target'])
        self.assertIsNone(found['spend_category'])

    def test_it_files_from_the_queue_form(self):
        form = ReconcileForm({'t-fund_source': str(fund('sga_fr').pk),
                              't-funding_request': str(self.request.pk)},
                             parent_transaction=self.txn, prefix='t')
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertTrue(entry.is_sga_return)
        self.assertIsNone(entry.lnl_spend_category)

    def test_the_entry_page_does_not_ask_for_a_category(self):
        entry = take_back(self.request, '15000.00')
        form = AllocationForm(instance=entry)
        self.assertFalse(form.fields['lnl_spend_category'].required)


class ReconcileFormTests(CacheResetMixin, TestCase):
    """ The queue's revenue row. """

    def setUp(self):
        super(ReconcileFormTests, self).setUp()
        self.request = make_request()
        self.txn = sga_line('F.26.86 Film Posters and Concessions', '500.00')

    def test_the_fund_is_taken_from_the_source_when_left_blank(self):
        form = ReconcileForm({'t-non_event_revenue_type': str(revenue_source('sga_baseline').pk)},
                             parent_transaction=self.txn, prefix='t')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().fund_source, fund('sga_budget'))

    def test_a_reimbursement_without_its_request_is_refused(self):
        form = ReconcileForm({
            't-non_event_revenue_type': str(revenue_source('sga_fr_reimbursement').pk),
            't-fund_source': str(fund('sga_fr').pk)}, parent_transaction=self.txn, prefix='t')
        self.assertFalse(form.is_valid())
        self.assertIn('funding_request', form.errors)

    def test_a_reimbursement_with_its_request_saves(self):
        form = ReconcileForm({
            't-non_event_revenue_type': str(revenue_source('sga_fr_reimbursement').pk),
            't-fund_source': str(fund('sga_fr').pk),
            't-funding_request': str(self.request.pk)}, parent_transaction=self.txn, prefix='t')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().funding_request, self.request)

    def test_a_filled_in_fund_may_give_way_to_the_source(self):
        """ routing.js only replaces a box it can tell nobody chose. """
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertIn('data-fin-inherited', str(form['fund_source']))

    def test_each_source_says_which_fund_it_goes_into(self):
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertIn('data-credits-fund="%s"' % fund('sga_budget').pk,
                      str(form['non_event_revenue_type']))


class SplitTests(CacheResetMixin, TestCase):
    """ The split page carries the request, so re-saving cannot wipe it. """

    def test_a_split_reimbursement_keeps_its_request(self):
        request = make_request()
        txn = sga_line('F.26.86 Film Posters and Concessions', '700.00')
        data = {'slices-TOTAL_FORMS': '2', 'slices-INITIAL_FORMS': '0',
                'slices-MIN_NUM_FORMS': '0', 'slices-MAX_NUM_FORMS': '1000'}
        for index, amount in enumerate(('400.00', '300.00')):
            data.update({
                'slices-%s-amount' % index: amount,
                'slices-%s-description' % index: 'Part %s' % index,
                'slices-%s-non_event_revenue_type' % index:
                    str(revenue_source('sga_fr_reimbursement').pk),
                'slices-%s-fund_source' % index: str(fund('sga_fr').pk),
                'slices-%s-funding_request' % index: str(request.pk),
            })
        formset = SplitFormSet(data, instance=txn, parent_transaction=txn)
        self.assertTrue(formset.is_valid(), formset.errors or formset.non_form_errors())
        for entry in formset.save():
            self.assertEqual(entry.funding_request, request)


class EventBillingSuggestionTests(CacheResetMixin, TestCase):
    """ An ISD is event billing whether or not lnldb knows the show. """

    def test_an_isd_naming_no_known_event_asks_which(self):
        txn = isd_line('Lens and Lights Services for Mystery Gala D26', '300.00')
        self.assertTrue(suggest_all(txn)['needs_event'])

    def test_one_naming_a_known_event_does_not(self):
        make_event('Pan Asian Festival', when(2026, 4, 25))
        txn = isd_line('Lens and Lights Services for Pan Asian Festival D26', '300.00')
        found = suggest_all(txn)
        self.assertFalse(found['needs_event'])
        self.assertIsNone(found['revenue_source'])


class MultiBillSuggestionTests(CacheResetMixin, TestCase):
    """ One payment for a bill covering several shows. """

    def setUp(self):
        super(MultiBillSuggestionTests, self).setUp()
        self.org = OrgFactory(name='Orientation', shortname='NSO')
        self.concert = make_event('NSO Concert', when(2025, 8, 20))
        self.social = make_event('NSO Social', when(2025, 8, 21))
        self.bill = MultiBilling.objects.create(
            org=self.org, date_billed=datetime.date(2025, 9, 1), amount=Decimal('900.00'))
        self.bill.events.set([self.concert, self.social])

    def test_the_event_the_memo_names_leads_to_its_bill(self):
        txn = isd_line('Lens and Lights Services for NSO Concert', '900.00',
                       date=datetime.date(2025, 10, 1))
        found = suggest_all(txn)
        self.assertEqual(found['multibill']['multibill'], self.bill)
        self.assertEqual(found['multibill']['source'], MEMO)

    def test_an_exact_amount_alone_is_a_guess(self):
        txn = isd_line('NSO A25', '900.00', date=datetime.date(2025, 10, 1))
        found = suggest_multibill(txn)
        self.assertEqual((found['multibill'], found['source']), (self.bill, GUESS))

    def test_two_bills_of_that_amount_are_a_question(self):
        other = MultiBilling.objects.create(
            org=self.org, date_billed=datetime.date(2025, 9, 2), amount=Decimal('900.00'))
        other.events.set([self.social])
        txn = isd_line('NSO A25', '900.00', date=datetime.date(2025, 10, 1))
        self.assertIsNone(suggest_multibill(txn))

    def test_a_different_amount_matches_nothing(self):
        txn = isd_line('NSO A25', '899.00', date=datetime.date(2025, 10, 1))
        self.assertIsNone(suggest_multibill(txn))


# ---------------------------------------------------------------------------
# The figures
# ---------------------------------------------------------------------------

class RevenueBySourceTests(CacheResetMixin, TestCase):
    """ Income by kind, with money SGA took back netted off reimbursements. """

    def test_event_billing_and_each_source(self):
        event = make_event('Pan Asian Festival', when(2026, 4, 25))
        event_income(event, '1000.00')
        request = make_request()
        reimburse(request, '400.00')
        take_back(request, '100.00', date=datetime.date(2026, 6, 20))
        rows = {row['label']: row for row in revenue_by_source(2026)}
        self.assertEqual(rows['Event billing']['amount'], Decimal('1000.00'))
        repaid = rows['SGA Funding Request Reimbursement']
        self.assertEqual((repaid['amount'], repaid['taken_back']),
                         (Decimal('300.00'), Decimal('100.00')))
        self.assertEqual(rows['Event billing']['percent'], Decimal('76.9'))


class BillingKeptTests(CacheResetMixin, TestCase):
    """ Hired-in gear billed to a client goes straight back out. """

    def test_passed_through_costs_come_off_the_billing(self):
        event = make_event('Pan Asian Festival', when(2026, 4, 25))
        event_income(event, '1000.00')
        rental = supplier_line('Video wall rental', '-600.00', date=datetime.date(2026, 4, 20))
        ParsedTransaction.objects.create(
            parent_transaction=rental, amount=Decimal('-600.00'),
            effective_date=rental.accounting_date, fund_source=fund('legacy'),
            lnl_spend_category=category('event_subrental'), linked_event=event)
        kept = event_billing_kept(2026)
        self.assertEqual((kept['gross'], kept['passthrough'], kept['kept'], kept['kept_percent']),
                         (Decimal('1000.00'), Decimal('600.00'), Decimal('400.00'),
                          Decimal('40.0')))


class ClientRetentionTests(CacheResetMixin, TestCase):
    """ A client LNL worked for in an earlier year is returning. """

    def test_new_and_returning(self):
        old_friend = OrgFactory(name='Student Activities Board', shortname='SAB')
        stranger = OrgFactory(name='Robotics Club', shortname='RBC')
        make_event('SAB Fall Concert', when(2024, 10, 1), billing_org=old_friend)
        this_year = make_event('SAB Spring Concert', when(2026, 4, 1), billing_org=old_friend)
        first_time = make_event('Robot Gala', when(2026, 4, 2), billing_org=stranger)
        event_income(this_year, '700.00')
        event_income(first_time, '300.00', date=datetime.date(2026, 5, 16))
        split = client_retention(2026)
        self.assertEqual((split['returning']['count'], split['returning']['amount']),
                         (1, Decimal('700.00')))
        self.assertEqual((split['new']['count'], split['new']['amount']),
                         (1, Decimal('300.00')))
        self.assertEqual([c['name'] for c in split['new_clients']], [stranger.retname])

    def test_every_year_at_once_has_no_new(self):
        self.assertIsNone(client_retention(None))


class EventPaymentStateTests(CacheResetMixin, TestCase):
    """ What lnldb says was billed and paid, against what the ledger received. """

    def setUp(self):
        super(EventPaymentStateTests, self).setUp()
        self.event = make_event('Spring Gala', when(2026, 4, 25))
        self.bill = Billing.objects.create(event=self.event, date_billed=datetime.date(2026, 4, 30),
                                           amount=Decimal('500.00'))

    def test_billed_and_nothing_received(self):
        figures = event_financials(self.event)
        self.assertEqual(figures['payment_state'], 'awaiting')
        self.assertEqual(figures['owed'], Decimal('500.00'))
        self.assertFalse(figures['can_mark_paid'])

    def test_part_received(self):
        event_income(self.event, '200.00')
        figures = event_financials(self.event)
        self.assertEqual((figures['payment_state'], figures['owed']), ('part', Decimal('300.00')))

    def test_received_in_full_and_not_marked_paid(self):
        event_income(self.event, '500.00')
        figures = event_financials(self.event)
        self.assertEqual(figures['payment_state'], 'paid')
        self.assertIn('not_marked_paid', figures['flag_keys'])
        self.assertTrue(figures['can_mark_paid'])

    def test_marked_paid_with_nothing_filed(self):
        # Some other line has to exist for the books to start before the show.
        supplier_line('Tape', '-5.00', date=datetime.date(2025, 7, 15))
        self.bill.date_paid = datetime.date(2026, 5, 2)
        self.bill.save()
        self.assertIn('paid_not_received', event_financials(self.event)['flag_keys'])

    def test_a_show_before_the_books_is_not_expected_to_have_its_payment(self):
        supplier_line('Tape', '-5.00', date=datetime.date(2026, 8, 15))
        self.bill.date_paid = datetime.date(2026, 5, 2)
        self.bill.save()
        self.assertNotIn('paid_not_received', event_financials(self.event)['flag_keys'])

    def test_receivables_list_what_is_still_owed(self):
        supplier_line('Tape', '-5.00', date=datetime.date(2025, 7, 15))
        event_income(self.event, '200.00')
        rows = billing_receivables()
        self.assertEqual([(r['event'], r['owed']) for r in rows],
                         [(self.event, Decimal('300.00'))])

    def test_the_pnl_totals_what_is_owed(self):
        from finance.calculators import event_pnl_totals
        event_income(self.event, '200.00')
        rows = event_pnl_rows(2026)
        self.assertEqual(event_pnl_totals(rows)['owed'], Decimal('300.00'))


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class MarkBillPaidTests(CacheResetMixin, FinanceViewTestCase):
    """ Copying the day the money arrived onto lnldb's bill, when asked. """

    def setUp(self):
        super(MarkBillPaidTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'bill_event')
        self.event = make_event('Spring Gala', when(2026, 4, 25))
        self.bill = Billing.objects.create(event=self.event, date_billed=datetime.date(2026, 4, 30),
                                           amount=Decimal('500.00'))

    def _post(self, event=None):
        return self.client.post(reverse('finance:event-mark-paid', args=[(event or self.event).pk]),
                                {'next': reverse('finance:events')}, follow=True)

    def test_a_paid_bill_is_dated_by_its_last_payment(self):
        event_income(self.event, '300.00', date=datetime.date(2026, 5, 10))
        event_income(self.event, '200.00', date=datetime.date(2026, 5, 20))
        response = self._post()
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.date_paid, datetime.date(2026, 5, 20))
        self.assertContains(response, 'paid on May 20, 2026')

    def test_a_bill_not_yet_covered_is_left_alone(self):
        event_income(self.event, '300.00')
        response = self._post()
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)
        self.assertContains(response, 'File the rest of the payment first')

    def test_the_events_apps_permission_is_needed_too(self):
        self.user.user_permissions.remove(
            self.user.user_permissions.get(codename='bill_event'))
        self.grant()
        event_income(self.event, '500.00')
        response = self.client.post(reverse('finance:event-mark-paid', args=[self.event.pk]))
        self.assertEqual(response.status_code, 403)

    def test_a_multibill_counts_every_show_on_it(self):
        org = OrgFactory(name='Orientation', shortname='NSO')
        concert = make_event('NSO Concert', when(2025, 8, 20))
        social = make_event('NSO Social', when(2025, 8, 21))
        bill = MultiBilling.objects.create(org=org, date_billed=datetime.date(2025, 9, 1),
                                           amount=Decimal('900.00'))
        bill.events.set([concert, social])
        event_income(concert, '450.00', date=datetime.date(2025, 10, 1))
        self._post(concert)
        bill.refresh_from_db()
        self.assertIsNone(bill.date_paid)
        event_income(social, '450.00', date=datetime.date(2025, 10, 2))
        self._post(concert)
        bill.refresh_from_db()
        self.assertEqual(bill.date_paid, datetime.date(2025, 10, 2))

    def test_the_pnl_offers_the_button(self):
        event_income(self.event, '500.00')
        response = self.client.get(reverse('finance:events'), {'fy': 2026})
        self.assertContains(response, 'Mark bill paid')
        self.assertContains(response, 'Paid in full, bill not marked paid')


class FundingPageTests(CacheResetMixin, FinanceViewTestCase):
    """ What SGA owes, on the funding request pages. """

    def setUp(self):
        super(FundingPageTests, self).setUp()
        self.grant('view_subledger', 'view_fundingrequest', 'manage_fundingrequest')
        self.request = make_request()
        spend(self.request, '100.00', datetime.date(2025, 9, 1))
        reimburse(self.request, '60.00', date=datetime.date(2025, 12, 1))

    def test_the_list_says_what_sga_owes(self):
        response = self.client.get(reverse('finance:fr-list'), {'fy': 'all'})
        self.assertContains(response, 'Owed by SGA')
        self.assertContains(response, '$40.00')
        self.assertContains(response, 'Awaiting $40.00 from SGA')

    def test_the_request_lists_sgas_payments(self):
        response = self.client.get(reverse('finance:fr-detail', args=[self.request.pk]))
        self.assertContains(response, 'Reimbursed by SGA')
        self.assertContains(response, 'Sep 1, 2025')
        self.assertContains(response, '$60.00')

    def test_a_new_request_is_filled_from_the_memo_that_quoted_it(self):
        response = self.client.get(reverse('finance:fr-new'), {
            'reference': 'F.26.195', 'name': 'Campus Movies', 'fiscal_year': '2026'})
        self.assertContains(response, 'value="F.26.195"')
        self.assertContains(response, 'value="Campus Movies"')

    def test_saving_it_returns_to_the_queue_row(self):
        url = '%s?next=%s' % (reverse('finance:fr-new'),
                              reverse('finance:queue') + '%23txn-5')
        response = self.client.post(url, {
            'name': 'Campus Movies', 'reference': 'F.26.195', 'fiscal_year': '2026',
            'line_items-TOTAL_FORMS': '0', 'line_items-INITIAL_FORMS': '0',
            'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000'})
        self.assertRedirects(response, reverse('finance:queue') + '#txn-5',
                             fetch_redirect_response=False)
        self.assertEqual(FundingRequest.objects.get(reference='F.26.195').owed_at_books_start,
                         Decimal('0.00'))

    def test_another_sites_next_is_ignored(self):
        url = '%s?next=https://example.com/' % reverse('finance:fr-new')
        response = self.client.post(url, {
            'name': 'Campus Movies', 'reference': 'F.26.195', 'fiscal_year': '2026',
            'line_items-TOTAL_FORMS': '0', 'line_items-INITIAL_FORMS': '0',
            'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000'})
        self.assertNotIn('example.com', response['Location'])


class QueuePageTests(CacheResetMixin, FinanceViewTestCase):
    """ The queue row for SGA's money. """

    def setUp(self):
        super(QueuePageTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'manage_fundingrequest')

    def test_an_unknown_request_can_be_added_from_the_row(self):
        txn = sga_line('F.26.195 Campus Movies', '2873.08')
        response = self.client.get(reverse('finance:queue'), {'fy': 'all'})
        self.assertContains(response, 'Add F.26.195')
        self.assertContains(response, 'reference=F.26.195')
        self.assertContains(response, 'txn-%s' % txn.pk)

    def test_a_known_request_is_filled_in(self):
        request = make_request()
        sga_line('F.26.86 Film Posters and Concessions', '10837.59')
        response = self.client.get(reverse('finance:queue'), {'fy': 'all'})
        self.assertContains(response, 'Reimburses request')
        self.assertContains(response, 'Memo quotes %s' % request.reference)

    def test_a_multibill_payment_links_to_the_split(self):
        org = OrgFactory(name='Orientation', shortname='NSO')
        concert = make_event('NSO Concert', when(2025, 8, 20))
        social = make_event('NSO Social', when(2025, 8, 21))
        bill = MultiBilling.objects.create(org=org, date_billed=datetime.date(2025, 9, 1),
                                           amount=Decimal('900.00'))
        bill.events.set([concert, social])
        txn = isd_line('NSO A25', '900.00', date=datetime.date(2025, 10, 1))
        response = self.client.get(reverse('finance:queue'), {'fy': 'all'})
        self.assertContains(response, 'split across 2 events')
        self.assertContains(response, '%s?multibill=%s' % (
            reverse('finance:txn-detail', args=[txn.pk]), bill.pk))

    def test_the_split_page_lays_out_each_shows_share(self):
        org = OrgFactory(name='Orientation', shortname='NSO')
        concert = make_event('NSO Concert', when(2025, 8, 20))
        social = make_event('NSO Social', when(2025, 8, 21))
        bill = MultiBilling.objects.create(org=org, date_billed=datetime.date(2025, 9, 1),
                                           amount=Decimal('900.00'))
        bill.events.set([concert, social])
        txn = isd_line('NSO A25', '900.00', date=datetime.date(2025, 10, 1))
        response = self.client.get(reverse('finance:txn-detail', args=[txn.pk]),
                                   {'multibill': bill.pk})
        forms = response.context['formset'].forms
        self.assertEqual([form.initial['amount'] for form in forms],
                         [Decimal('450.00'), Decimal('450.00')])
        self.assertEqual([form.initial['linked_event'] for form in forms],
                         [concert.pk, social.pk])
        self.assertContains(response, 'Laid out across the 2 events')


class DashboardTests(CacheResetMixin, FinanceViewTestCase):
    """ Where the money comes from, and what LNL is owed. """

    def test_the_new_panels(self):
        self.grant('view_subledger')
        request = make_request()
        spend(request, '100.00', datetime.date(2025, 9, 1))
        reimburse(request, '60.00', date=datetime.date(2025, 12, 1))
        response = self.client.get(reverse('finance:dashboard'), {'fy': 2026})
        self.assertContains(response, 'Revenue by Source')
        self.assertContains(response, 'SGA Funding Request Reimbursement')
        self.assertContains(response, 'LNL kept')
        self.assertContains(response, 'Owed to LNL')
        self.assertEqual(response.context['owed_by_sga'], Decimal('40.00'))

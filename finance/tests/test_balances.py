"""
Fund balances, the year-end close, and the SGA reference rules behind them.

Four layers, tested from the bottom up:

* **The rules.** Money coming in names the fund it adds to; an SGA request
  number is a letter for the body that approved it, the fiscal year, and a
  sequence number, and nothing else.
* **The suggestions.** Workday's Tracking worktag names the fund, an account's
  own money fills in when nothing else does, a reimbursement memo files into
  the funding-request fund, and a memo quoting A.27.16 when lnldb holds F.27.16
  offers that request as a question rather than an answer.
* **The arithmetic.** Each account's cash from a Workday balance, split between
  its funds, with the unfiled remainder as its own row so the funds always add
  back up to the cash.
* **The pages**: the balance page, the inputs behind it, closing a year and
  reopening it.
"""
import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from finance import balances
from finance.forms import ReconcileForm
from finance.models import (BalanceCheckpoint, FiscalYearClose, FRLineItem, FundBehaviour,
                            FundingRequest, FundTransfer, ParsedTransaction, PartitionCode,
                            TransactionStatus, WorkdayTransaction, account_own_funds,
                            books_start_date, own_fund_for_account, reset_finance_cache)
from finance.suggestions import (DEFAULT, EXPORT, GUESS, MEMO, funding_request_references,
                                 near_miss_funding_request, suggest_all, suggest_fund_source)
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund, revenue_source

MAIN = '226-AG Lens & Light Club'
PROJECTION = '315-AG Projection'
FY26 = 2026


def account(code):
    return PartitionCode.objects.get(code=code)


def line(date, amount, memo='', org=MAIN, **worktags):
    """ A saved bank line on an account. """
    tags = {'student_organization': org} if org else {}
    tags.update(worktags)
    return WorkdayTransaction.objects.create(
        operational_transaction='OT-%s-%s' % (date.isoformat(), amount),
        accounting_date=date, net_amount=Decimal(amount), memo=memo, worktags_json=tags)


def filed(txn, fund_slug=None, amount=None, **extra):
    """ One slice covering ``txn`` (or ``amount`` of it), written straight to the table. """
    return ParsedTransaction.objects.create(
        parent_transaction=txn, amount=Decimal(amount or txn.net_amount),
        effective_date=txn.accounting_date, status=TransactionStatus.SETTLED,
        fund_source=fund(fund_slug) if fund_slug else None, **extra)


def checkpoint(code, as_of, balance):
    return BalanceCheckpoint.objects.create(account=account(code), as_of=as_of,
                                            balance=Decimal(balance))


def row_for(statement, code, slug):
    """ One fund's row on one account's statement. """
    for row in statement.account(code).rows:
        if row.fund is not None and row.fund.slug == slug:
            return row
    raise AssertionError("%s has no %s row" % (code, slug))


class LedgerFixture(object):
    """
    A year of 226-AG, small enough to add up by hand.

    The account held $10,000 the night the books started. Then:

    ===========  =========  ====================  ======================
    Jul 10       +1,000     event billing         Legacy
    Aug 1        +5,000     the SGA budget lands  SGA Budget
    Sep 1        -6,000     budget spending       SGA Budget (overspent)
    Oct 1          -800     funding request       SGA Funding Request
    Feb 1          +500     SGA reimburses part   SGA Funding Request
    Mar 1          -200     still in the queue    (unfiled)
    ===========  =========  ====================  ======================

    so on June 30 it holds $9,500: Legacy $11,000, the budget $1,000 overspent,
    $300 still owed by SGA, and $200 not filed.
    """

    def build_year(self):
        self.billing = line(datetime.date(2025, 7, 10), '1000.00', 'ISD billing')
        filed(self.billing, 'legacy', non_event_revenue_type=revenue_source('alumni'))
        self.deposit = line(datetime.date(2025, 8, 1), '5000.00', 'SGA budget allocation')
        filed(self.deposit, 'sga_budget', non_event_revenue_type=revenue_source('sga_baseline'))
        self.budget_spend = line(datetime.date(2025, 9, 1), '-6000.00', 'Console')
        filed(self.budget_spend, 'sga_budget', lnl_spend_category=category('consumables'))
        self.fr_spend = line(datetime.date(2025, 10, 1), '-800.00', 'Rights (F.26.6)')
        filed(self.fr_spend, 'sga_fr', lnl_spend_category=category('consumables'))
        self.reimbursement = line(datetime.date(2026, 2, 1), '500.00', 'F.26.6 Film Rights')
        filed(self.reimbursement, 'sga_fr',
              non_event_revenue_type=revenue_source('sga_fr_reimbursement'))
        self.unfiled = line(datetime.date(2026, 3, 1), '-200.00', 'Not yet')
        self.year_end = checkpoint('226-AG', datetime.date(2026, 6, 30), '9500.00')


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

class SeededFundTests(TestCase):
    """ What 0005_fund_balances says about the funds every install starts with. """

    def test_each_seeded_fund_says_how_it_behaves_and_where_it_is_held(self):
        expected = {
            'legacy': (FundBehaviour.CARRIES, '226-AG', 'Student Org Legacy Funds'),
            'sga_budget': (FundBehaviour.RETURNS, '226-AG', 'SGA Budget'),
            'sga_fr': (FundBehaviour.REIMBURSED, '226-AG', 'SGA Funding Request'),
            'sga_mandatory': (FundBehaviour.CARRIES, '315-AG', ''),
        }
        for slug, (behaviour, code, tracking) in expected.items():
            row = fund(slug)
            self.assertEqual((row.behaviour, row.account.code, row.workday_tracking_values),
                             (behaviour, code, tracking), slug)

    def test_each_account_has_money_of_its_own(self):
        """ The carry-forward fund held in an account is what is left of it. """
        self.assertEqual(own_fund_for_account('226-AG'), fund('legacy'))
        self.assertEqual(own_fund_for_account('315-AG'), fund('sga_mandatory'))
        self.assertIsNone(own_fund_for_account('999-XX'))

    def test_a_fund_that_stops_carrying_forward_stops_being_an_accounts_own(self):
        reset_finance_cache('own_funds')
        self.addCleanup(reset_finance_cache, 'own_funds')
        legacy = fund('legacy')
        legacy.behaviour = FundBehaviour.RETURNS
        legacy.save()
        self.assertNotIn('226-AG', account_own_funds())


class RevenueFundRuleTests(TestCase):
    """ Money coming in names the fund it adds to; it still has no spend category. """

    def test_revenue_may_name_a_fund(self):
        txn = line(datetime.date(2025, 9, 1), '500.00', 'Fall Concert')
        entry = ParsedTransaction(parent_transaction=txn, amount=Decimal('500.00'),
                                  non_event_revenue_type=revenue_source('alumni'),
                                  fund_source=fund('legacy'))
        entry.full_clean()
        entry.save()
        self.assertEqual(entry.fund_source, fund('legacy'))

    def test_the_database_still_refuses_a_spend_category_on_revenue(self):
        txn = line(datetime.date(2025, 9, 1), '500.00')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParsedTransaction.objects.create(
                    parent_transaction=txn, amount=Decimal('500.00'),
                    fund_source=fund('legacy'), lnl_spend_category=category('consumables'))

    def test_a_reimbursement_need_not_name_a_funding_request_line(self):
        """
        Only spending burns down a line; money coming back names the request
        it repays instead.
        """
        txn = line(datetime.date(2025, 9, 1), '500.00')
        request = FundingRequest.objects.create(name='Film Rights', reference='F.26.6',
                                                fiscal_year=2026)
        entry = ParsedTransaction(parent_transaction=txn, amount=Decimal('500.00'),
                                  non_event_revenue_type=revenue_source('sga_fr_reimbursement'),
                                  fund_source=fund('sga_fr'), funding_request=request)
        entry.full_clean()


class SGAReferenceTests(TestCase):
    """ A, F or S for the body; the fiscal year; the number within that body's year. """

    def _request(self, reference, fiscal_year=2027):
        return FundingRequest(name='Summer OpEx', reference=reference, fiscal_year=fiscal_year)

    def test_each_body_letter_is_accepted(self):
        for reference in ('A.27.16', 'F.27.16', 'S.27.2'):
            self._request(reference).full_clean()

    def test_the_reference_is_tidied_up(self):
        request = self._request('f. 27. 16')
        request.full_clean()
        self.assertEqual(request.reference, 'F.27.16')

    def test_another_letter_is_refused(self):
        with self.assertRaises(ValidationError) as ctx:
            self._request('B.27.16').full_clean()
        self.assertIn('reference', ctx.exception.error_dict)

    def test_the_year_in_the_number_has_to_be_the_requests_year(self):
        with self.assertRaises(ValidationError) as ctx:
            self._request('A.26.4', fiscal_year=2027).full_clean()
        self.assertIn('FY26', str(ctx.exception))

    def test_no_reference_is_fine(self):
        self._request('').full_clean()

    def test_the_letter_names_who_approved_it(self):
        self.assertEqual(self._request('A.27.16').approving_body, 'Appropriations Committee')
        self.assertEqual(self._request('F.27.16').approving_body, 'Financial Board')
        self.assertEqual(self._request('S.27.2').approving_body, 'Senate')
        self.assertEqual(self._request('').approving_body, '')

    def test_a_memo_is_only_read_for_those_three_letters(self):
        self.assertEqual(funding_request_references('Velcro, consumables, (a.27.16)'),
                         ['A.27.16'])
        self.assertEqual(funding_request_references('Invoice B.25.12 for cable'), [])


# ---------------------------------------------------------------------------
# The suggestions
# ---------------------------------------------------------------------------

class NearMissReferenceTests(TestCase):
    """
    A memo quoting A.27.16 while lnldb holds F.27.16.

    Two different requests by SGA's numbering, and the queue may not treat them
    as one. But LNL's memos did exactly this for a whole summer, so the request
    with the same number is offered -- as a chip, with the question spelt out.
    """

    def setUp(self):
        self.request = FundingRequest.objects.create(name='Summer OpEx', reference='F.27.16',
                                                     fiscal_year=2027)
        self.consumables = FRLineItem.objects.create(
            funding_request=self.request, name='Consumables', amount_awarded=Decimal('500.00'),
            lnl_spend_category=category('consumables'))
        FRLineItem.objects.create(funding_request=self.request, name='Maintenance and Repair',
                                  amount_awarded=Decimal('900.00'))
        self.txn = line(datetime.date(2026, 7, 22), '-15.45',
                        'Velcro restock, consumables, (A.27.16)')

    def test_the_request_with_the_same_number_is_found(self):
        self.assertEqual(near_miss_funding_request('A.27.16'), self.request)

    def test_a_different_number_or_year_is_not_a_near_miss(self):
        self.assertIsNone(near_miss_funding_request('A.27.17'))
        self.assertIsNone(near_miss_funding_request('A.26.16'))

    def test_two_candidates_is_a_question_this_cannot_answer(self):
        FundingRequest.objects.create(name='Big ask', reference='S.27.16', fiscal_year=2027)
        self.assertIsNone(near_miss_funding_request('A.27.16'))

    def test_the_line_is_offered_as_a_chip_and_never_filled_in(self):
        found = suggest_all(self.txn)
        self.assertEqual(found['near_miss'], self.request)
        self.assertEqual(found['fr_line_target'].value, self.consumables.pk)
        self.assertEqual(found['fr_line_target'].source, GUESS)
        self.assertIn('F.27.16', found['fr_line_target'].reason)

        form = ReconcileForm(parent_transaction=self.txn, prefix='t%s' % self.txn.pk)
        self.assertNotIn('fr_line_target', form.autofilled)

    def test_the_fund_is_still_filled_in(self):
        """ Every SGA number is a funding request, whichever one it turns out to be. """
        found = suggest_all(self.txn)
        self.assertEqual(found['fund_source'].value, fund('sga_fr').pk)
        self.assertEqual(found['fund_source'].source, MEMO)

    def test_the_warning_names_both_requests(self):
        warning = suggest_all(self.txn)['warning']
        self.assertIn('A.27.16', warning)
        self.assertIn('F.27.16', warning)

    def test_an_exact_match_is_not_a_near_miss(self):
        txn = line(datetime.date(2026, 7, 22), '-15.45', 'Velcro, consumables, (F.27.16)')
        found = suggest_all(txn)
        self.assertIsNone(found['near_miss'])
        self.assertEqual(found['fr_line_target'].source, MEMO)
        self.assertEqual(found['warning'], '')


class FundSuggestionTests(TestCase):
    """ Which fund a line names, most specific evidence first. """

    def test_the_tracking_worktag_names_the_fund(self):
        reset_finance_cache('fund_tracking')
        txn = line(datetime.date(2026, 8, 19), '-311.04', 'CTX#71443', tracking='SGA Budget')
        suggestion = suggest_fund_source(txn)
        self.assertEqual(suggestion.value, fund('sga_budget').pk)
        self.assertEqual(suggestion.source, EXPORT)
        self.assertIn('Tracking', suggestion.reason)

    def test_a_memo_reference_beats_the_tracking_worktag(self):
        txn = line(datetime.date(2026, 8, 19), '-20.00', 'Rights (A.27.18)',
                   tracking='Student Org Legacy Funds')
        suggestion = suggest_fund_source(txn, reference='A.27.18')
        self.assertEqual(suggestion.value, fund('sga_fr').pk)

    def test_a_projection_line_is_projection_money(self):
        txn = line(datetime.date(2026, 8, 19), '-40.00', 'Popcorn', org=PROJECTION)
        suggestion = suggest_fund_source(txn)
        self.assertEqual(suggestion.value, fund('sga_mandatory').pk)
        self.assertEqual(suggestion.source, DEFAULT)
        self.assertIn("315-AG's own money", suggestion.reason)

    def test_a_reimbursement_lands_in_the_funding_request_fund(self):
        # SGA pays with a journal entry naming nobody; see is_sga_transfer.
        txn = WorkdayTransaction.objects.create(
            accounting_date=datetime.date(2026, 6, 12), net_amount=Decimal('10837.59'),
            memo='F.26.86 Film Posters and Concessions',
            worktags_json={'student_organization': MAIN,
                           'journal': '26060012-JE - Worcester Polytechnic Institute'})
        suggestion = suggest_all(txn)['fund_source']
        self.assertEqual(suggestion.value, fund('sga_fr').pk)
        self.assertEqual(suggestion.source, MEMO)

    def test_event_billing_is_the_accounts_own_money(self):
        txn = line(datetime.date(2025, 9, 2), '400.00', 'Fall Concert')
        suggestion = suggest_all(txn)['fund_source']
        self.assertEqual(suggestion.value, fund('legacy').pk)
        self.assertEqual(suggestion.source, DEFAULT)


class RevenueFundFormTests(TestCase):
    """ The queue asks money coming in which fund it goes into. """

    def setUp(self):
        self.txn = line(datetime.date(2025, 9, 2), '400.00', 'Fall Concert')

    def _form(self, data=None):
        return ReconcileForm(data, parent_transaction=self.txn, prefix='t')

    def test_the_fund_is_on_a_revenue_row_and_filled_in(self):
        form = self._form()
        self.assertEqual(form.fields['fund_source'].label, "Into fund")
        self.assertEqual(form.initial['fund_source'], fund('legacy').pk)
        self.assertNotIn('lnl_spend_category', form.fields)

    def test_the_fund_is_required(self):
        form = self._form({'t-non_event_revenue_type': revenue_source('alumni').pk})
        self.assertFalse(form.is_valid())
        self.assertIn('fund_source', form.errors)

    def test_a_revenue_row_saves_with_its_fund(self):
        form = self._form({'t-non_event_revenue_type': revenue_source('alumni').pk,
                           't-fund_source': fund('legacy').pk})
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.fund_source, fund('legacy'))

    def test_a_refund_takes_its_fund_from_the_purchase(self):
        purchase_line = line(datetime.date(2025, 9, 1), '-90.00', 'Cable')
        purchase = filed(purchase_line, 'sga_budget', lnl_spend_category=category('consumables'))
        credit = line(datetime.date(2025, 9, 5), '90.00', 'Cable return')
        form = ReconcileForm({'t-refund_of': purchase.pk}, parent_transaction=credit, prefix='t')
        self.assertNotIn('fund_source', form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().fund_source, fund('sga_budget'))


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------

class BooksStartTests(TestCase):

    def test_the_books_start_with_the_fiscal_year_of_the_first_line(self):
        self.assertIsNone(books_start_date())
        line(datetime.date(2025, 9, 12), '-10.00')
        self.assertEqual(books_start_date(), datetime.date(2025, 7, 1))

    def test_a_date_the_treasurer_set_wins(self):
        from finance.models import FinanceSettings
        line(datetime.date(2025, 9, 12), '-10.00')
        config = FinanceSettings.load()
        config.ledger_start_date = datetime.date(2025, 9, 1)
        config.save()
        reset_finance_cache('config')
        self.addCleanup(reset_finance_cache, 'config')
        self.assertEqual(books_start_date(), datetime.date(2025, 9, 1))


class StatementTests(LedgerFixture, TestCase):
    """ One year of 226-AG, split between its funds and added back up. """

    def setUp(self):
        self.build_year()
        self.year = balances.statement(FY26)
        self.main = self.year.account('226-AG')

    def test_the_cash_is_counted_from_the_workday_balance(self):
        """ Entered on June 30, and worked backwards to the night the books opened. """
        self.assertEqual(self.main.closing_cash, Decimal('9500.00'))
        self.assertEqual(self.main.opening_cash, Decimal('10000.00'))

    def test_the_accounts_own_money_holds_the_opening_and_what_it_earned(self):
        legacy = row_for(self.year, '226-AG', 'legacy')
        self.assertTrue(legacy.is_own)
        self.assertEqual((legacy.opening, legacy.received, legacy.spent, legacy.closing),
                         (Decimal('10000.00'), Decimal('1000.00'), Decimal('0.00'),
                          Decimal('11000.00')))
        self.assertEqual(legacy.status, "Carries forward")

    def test_an_overspent_budget_says_so(self):
        budget = row_for(self.year, '226-AG', 'sga_budget')
        self.assertEqual((budget.received, budget.spent, budget.closing),
                         (Decimal('5000.00'), Decimal('6000.00'), Decimal('-1000.00')))
        self.assertIn("Overspent", budget.status)

    def test_a_funding_request_balance_is_what_sga_still_owes(self):
        requests = row_for(self.year, '226-AG', 'sga_fr')
        self.assertEqual(requests.closing, Decimal('-300.00'))
        self.assertEqual(requests.status, "Awaiting reimbursement from SGA")

    def test_unfiled_lines_are_a_row_of_their_own_and_everything_adds_up(self):
        self.assertEqual(self.main.unfiled_closing, Decimal('-200.00'))
        self.assertEqual(self.main.funds_total, self.main.closing_cash)
        self.assertEqual(self.main.out_of_balance, Decimal('0.00'))

    def test_a_later_workday_balance_checks_the_arithmetic(self):
        checkpoint('226-AG', datetime.date(2026, 3, 31), '9400.00')
        year = balances.statement(FY26)
        rows = {row.checkpoint.as_of: row for row in year.account('226-AG').checkpoints}
        # The earliest balance anchors now, so March 31 is taken as given...
        self.assertTrue(rows[datetime.date(2026, 3, 31)].is_anchor)
        self.assertEqual(rows[datetime.date(2026, 3, 31)].computed, Decimal('9400.00'))
        # ...and June 30, with no lines in between, is $100 more than it can be.
        self.assertEqual(rows[datetime.date(2026, 6, 30)].computed, Decimal('9400.00'))
        self.assertEqual(rows[datetime.date(2026, 6, 30)].difference, Decimal('100.00'))

    def test_a_slice_naming_no_fund_is_the_accounts_own_money(self):
        gift = line(datetime.date(2025, 11, 1), '50.00', 'Alumni gift')
        filed(gift, None, non_event_revenue_type=revenue_source('alumni'))
        year = balances.statement(FY26)
        self.assertEqual(row_for(year, '226-AG', 'legacy').received, Decimal('1050.00'))

    def test_a_refund_counts_against_spending_not_as_income(self):
        credit = line(datetime.date(2025, 9, 20), '100.00', 'Console part returned')
        purchase = ParsedTransaction.objects.get(parent_transaction=self.budget_spend)
        filed(credit, 'sga_budget', refund_of=purchase,
              lnl_spend_category=category('consumables'))
        budget = row_for(balances.statement(FY26), '226-AG', 'sga_budget')
        self.assertEqual((budget.received, budget.spent),
                         (Decimal('5000.00'), Decimal('5900.00')))

    def test_an_encumbrance_is_reserved_not_spent(self):
        ParsedTransaction.objects.create(
            amount=Decimal('-250.00'), effective_date=datetime.date(2026, 5, 1),
            fund_source=fund('legacy'), lnl_spend_category=category('consumables'),
            description='Hazer fluid')
        legacy = row_for(balances.statement(FY26), '226-AG', 'legacy')
        self.assertEqual(legacy.closing, Decimal('11000.00'))
        self.assertEqual(legacy.encumbered, Decimal('250.00'))
        self.assertEqual(legacy.available, Decimal('10750.00'))

    def test_a_transfer_moves_money_without_changing_the_total(self):
        FundTransfer.objects.create(
            account=account('226-AG'), date=datetime.date(2026, 6, 1),
            amount=Decimal('1000.00'), from_fund=fund('legacy'), to_fund=fund('sga_budget'),
            description='Cover the console')
        year = balances.statement(FY26)
        self.assertEqual(row_for(year, '226-AG', 'sga_budget').closing, Decimal('0.00'))
        self.assertEqual(row_for(year, '226-AG', 'legacy').closing, Decimal('10000.00'))
        self.assertEqual(row_for(year, '226-AG', 'legacy').transferred, Decimal('-1000.00'))
        self.assertEqual(year.account('226-AG').out_of_balance, Decimal('0.00'))

    def test_an_opening_split_is_the_opening_not_a_movement(self):
        """ SGA owed $300 for spending before the books started. """
        FundTransfer.objects.create(
            account=account('226-AG'), date=datetime.date(2025, 7, 1),
            amount=Decimal('300.00'), from_fund=fund('sga_fr'), to_fund=fund('legacy'),
            kind=FundTransfer.OPENING, description='Opening')
        year = balances.statement(FY26)
        requests = row_for(year, '226-AG', 'sga_fr')
        self.assertEqual((requests.opening, requests.transferred, requests.closing),
                         (Decimal('-300.00'), Decimal('0.00'), Decimal('-600.00')))
        self.assertEqual(row_for(year, '226-AG', 'legacy').opening, Decimal('10300.00'))

    def test_the_next_year_opens_where_this_one_closed(self):
        year = balances.statement(2027)
        self.assertEqual(row_for(year, '226-AG', 'legacy').opening, Decimal('11000.00'))
        self.assertEqual(row_for(year, '226-AG', 'sga_fr').opening, Decimal('-300.00'))
        self.assertEqual(year.account('226-AG').unfiled_opening, Decimal('-200.00'))

    def test_a_late_import_corrects_both_years_at_once(self):
        """
        Nothing is copied from one year to the next, so nothing goes stale.

        Anchored at the opening here. Anchored on June 30 instead, the same
        line would move the opening: Workday's June 30 figure already counted
        it, so the ledger had been short of it at the start, not the end.
        """
        BalanceCheckpoint.objects.all().delete()
        checkpoint('226-AG', datetime.date(2025, 6, 30), '10000.00')
        late = line(datetime.date(2026, 6, 20), '-75.00', 'June invoice, imported in August')
        filed(late, 'legacy', lnl_spend_category=category('consumables'))
        self.assertEqual(row_for(balances.statement(FY26), '226-AG', 'legacy').closing,
                         Decimal('10925.00'))
        self.assertEqual(row_for(balances.statement(2027), '226-AG', 'legacy').opening,
                         Decimal('10925.00'))

    def test_a_year_before_the_books_has_nothing_to_show(self):
        year = balances.statement(2025)
        self.assertTrue(year.before_books)
        self.assertEqual(year.accounts, [])

    def test_the_projection_account_is_its_own_statement(self):
        deposit = line(datetime.date(2025, 7, 15), '20000.00', 'SGA mandatory transfer',
                       org=PROJECTION)
        filed(deposit, None, non_event_revenue_type=revenue_source('sga_baseline'))
        checkpoint('315-AG', datetime.date(2025, 7, 31), '20000.00')
        year = balances.statement(FY26)
        projection = row_for(year, '315-AG', 'sga_mandatory')
        self.assertEqual((projection.opening, projection.received, projection.closing),
                         (Decimal('0.00'), Decimal('20000.00'), Decimal('20000.00')))
        self.assertEqual(year.account('226-AG').closing_cash, Decimal('9500.00'))


class UnknownCashTests(TestCase):
    """ No Workday balance yet: the account's own money cannot be worked out. """

    def setUp(self):
        spend = line(datetime.date(2025, 9, 1), '-100.00', 'Gaff')
        filed(spend, 'sga_budget', lnl_spend_category=category('consumables'))
        own = line(datetime.date(2025, 9, 2), '40.00', 'Gift')
        filed(own, 'legacy', non_event_revenue_type=revenue_source('alumni'))
        self.year = balances.statement(FY26)

    def test_the_own_fund_shows_only_what_moved(self):
        legacy = row_for(self.year, '226-AG', 'legacy')
        self.assertIsNone(legacy.closing)
        self.assertEqual(legacy.received, Decimal('40.00'))
        self.assertIn("Workday balance", legacy.status)

    def test_every_other_fund_is_still_known(self):
        self.assertEqual(row_for(self.year, '226-AG', 'sga_budget').closing,
                         Decimal('-100.00'))
        self.assertFalse(self.year.account('226-AG').cash_known)


class YearEndProposalTests(LedgerFixture, TestCase):

    def setUp(self):
        self.build_year()

    def test_an_overspend_is_covered_and_an_unpaid_reimbursement_may_be_written_off(self):
        proposals = balances.year_end_proposals(balances.statement(FY26))
        found = {(p['row'].fund.slug, p['kind']): p['amount'] for p in proposals}
        self.assertEqual(found, {('sga_budget', 'cover'): Decimal('1000.00'),
                                 ('sga_fr', 'write_off'): Decimal('300.00')})

    def test_an_unspent_budget_needs_no_transfer(self):
        """ SGA takes it back with a Workday line of its own. """
        refund = line(datetime.date(2026, 6, 15), '1500.00', 'Supplemental budget')
        filed(refund, 'sga_budget', non_event_revenue_type=revenue_source('sga_baseline'))
        year = balances.statement(FY26)
        self.assertEqual(row_for(year, '226-AG', 'sga_budget').status, "Goes back to SGA")
        kinds = {p['row'].fund.slug for p in balances.year_end_proposals(year)}
        self.assertNotIn('sga_budget', kinds)


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class BalancePageTests(LedgerFixture, FinanceViewTestCase):

    def setUp(self):
        super(BalancePageTests, self).setUp()
        self.build_year()

    def test_it_needs_the_ledger_permission(self):
        response = self.client.get(reverse('finance:balances'), {'fy': FY26})
        self.assertEqual(response.status_code, 403)

    def test_it_shows_every_fund_and_the_unfiled_row(self):
        self.grant('view_subledger')
        response = self.client.get(reverse('finance:balances'), {'fy': FY26})
        self.assertContains(response, 'Legacy')
        self.assertContains(response, '$11,000.00')
        self.assertContains(response, 'Awaiting reimbursement from SGA')
        self.assertContains(response, 'Not filed yet')
        self.assertNotContains(response, 'miss the cash')

    def test_a_finished_year_offers_to_close_only_with_the_permission(self):
        self.grant('view_subledger')
        url = reverse('finance:close-year', args=[FY26])
        self.assertNotContains(self.client.get(reverse('finance:balances'), {'fy': FY26}), url)
        self.grant('close_fiscalyear')
        self.assertContains(self.client.get(reverse('finance:balances'), {'fy': FY26}), url)

    def test_the_dashboard_shows_todays_balances(self):
        self.grant('view_subledger')
        response = self.client.get(reverse('finance:dashboard'), {'fy': FY26})
        self.assertContains(response, 'What Each Fund Holds Today')


class BalanceInputTests(LedgerFixture, FinanceViewTestCase):

    def setUp(self):
        super(BalanceInputTests, self).setUp()
        self.build_year()
        self.grant('view_subledger', 'edit_subledger')

    def test_a_workday_balance_is_recorded(self):
        response = self.client.post(reverse('finance:checkpoint-new'), {
            'account': account('226-AG').pk, 'as_of': '2026-09-30', 'balance': '9100.00'})
        self.assertEqual(response.status_code, 302)
        point = BalanceCheckpoint.objects.get(as_of=datetime.date(2026, 9, 30))
        self.assertEqual(point.entered_by, self.user)

    def test_one_balance_per_account_per_day(self):
        response = self.client.post(reverse('finance:checkpoint-new'), {
            'account': account('226-AG').pk, 'as_of': '2026-06-30', 'balance': '1.00'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BalanceCheckpoint.objects.count(), 1)

    def test_a_transfer_is_recorded(self):
        response = self.client.post(reverse('finance:transfer-new'), {
            'account': account('226-AG').pk, 'date': '2026-06-01', 'amount': '1000.00',
            'from_fund': fund('legacy').pk, 'to_fund': fund('sga_budget').pk,
            'description': 'Cover the console'})
        self.assertEqual(response.status_code, 302)
        transfer = FundTransfer.objects.get()
        self.assertEqual((transfer.kind, transfer.created_by),
                         (FundTransfer.TRANSFER, self.user))

    def test_a_transfer_to_the_same_fund_is_refused(self):
        response = self.client.post(reverse('finance:transfer-new'), {
            'account': account('226-AG').pk, 'date': '2026-06-01', 'amount': '10.00',
            'from_fund': fund('legacy').pk, 'to_fund': fund('legacy').pk,
            'description': 'Nothing'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FundTransfer.objects.exists())

    def test_a_transfer_before_the_books_start_is_refused(self):
        response = self.client.post(reverse('finance:transfer-new'), {
            'account': account('226-AG').pk, 'date': '2025-06-01', 'amount': '10.00',
            'from_fund': fund('legacy').pk, 'to_fund': fund('sga_fr').pk,
            'description': 'Too early'})
        self.assertContains(response, 'Opening balances')
        self.assertFalse(FundTransfer.objects.exists())

    def test_an_opening_or_year_end_transfer_is_not_deleted_from_the_list(self):
        transfer = FundTransfer.objects.create(
            account=account('226-AG'), date=datetime.date(2025, 7, 1), amount=Decimal('5.00'),
            from_fund=fund('sga_fr'), to_fund=fund('legacy'), kind=FundTransfer.OPENING,
            description='Opening')
        self.client.post(reverse('finance:transfer-delete', args=[transfer.pk]))
        self.assertTrue(FundTransfer.objects.filter(pk=transfer.pk).exists())

    def test_the_opening_split_replaces_itself(self):
        url = reverse('finance:opening-balances')
        main = account('226-AG')
        field = 'fund_%s_%s' % (main.pk, fund('sga_fr').pk)
        self.client.post(url, {field: '-300.00'})
        self.client.post(url, {field: '-250.00'})
        opening = FundTransfer.objects.get(kind=FundTransfer.OPENING)
        self.assertEqual((opening.from_fund, opening.to_fund, opening.amount),
                         (fund('sga_fr'), fund('legacy'), Decimal('250.00')))
        self.assertEqual(row_for(balances.statement(FY26), '226-AG', 'sga_fr').opening,
                         Decimal('-250.00'))

    def test_the_opening_cash_can_be_entered_there_too(self):
        main = account('226-AG')
        self.client.post(reverse('finance:opening-balances'),
                         {'cash_%s' % main.pk: '10000.00'})
        self.assertTrue(BalanceCheckpoint.objects.filter(
            account=main, as_of=datetime.date(2025, 6, 30), balance=Decimal('10000.00')).exists())


class CloseYearTests(LedgerFixture, FinanceViewTestCase):

    def setUp(self):
        super(CloseYearTests, self).setUp()
        self.build_year()
        self.grant('view_subledger', 'edit_subledger', 'close_fiscalyear')
        self.main = account('226-AG')
        self.url = reverse('finance:close-year', args=[FY26])

    def _close(self, **extra):
        data = {'workday_%s' % self.main.pk: '9500.00',
                'cover_%s_%s' % (self.main.pk, fund('sga_budget').pk): 'on',
                'write_off_%s_%s' % (self.main.pk, fund('sga_fr').pk): '100.00',
                'notes': 'First year on the books'}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_it_needs_the_close_permission(self):
        self.user.user_permissions.clear()
        self.grant('view_subledger')
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_the_page_lists_what_is_open_and_what_needs_squaring(self):
        response = self.client.get(self.url)
        self.assertContains(response, '1 line still in the queue')
        self.assertContains(response, 'overspent by')
        self.assertContains(response, 'still awaiting')

    def test_closing_squares_the_balances_and_records_them(self):
        self._close()
        close = FiscalYearClose.objects.get(fiscal_year=FY26)
        self.assertEqual(close.closed_by, self.user)
        self.assertEqual(close.transfers.count(), 2)

        year = balances.statement(FY26)
        self.assertEqual(row_for(year, '226-AG', 'sga_budget').closing, Decimal('0.00'))
        self.assertEqual(row_for(year, '226-AG', 'sga_fr').closing, Decimal('-200.00'))
        self.assertEqual(row_for(year, '226-AG', 'legacy').closing, Decimal('9900.00'))
        self.assertEqual(close.snapshot['accounts']['226-AG']['funds']['Legacy'], '9900.00')
        self.assertEqual(balances.drift(close, year), [])

    def test_a_line_filed_after_the_close_is_reported(self):
        self._close()
        late = line(datetime.date(2026, 6, 25), '-60.00', 'Late invoice')
        filed(late, 'legacy', lnl_spend_category=category('consumables'))
        response = self.client.get(reverse('finance:balances'), {'fy': FY26})
        self.assertContains(response, 'It has changed since')
        # Workday's June 30 balance already counted the line, so it is the
        # opening the ledger had wrong, and that is what is reported.
        self.assertContains(response, '226-AG Legacy at the start')
        self.assertContains(response, '226-AG Opening cash')

    def test_reopening_takes_the_year_end_transfers_back(self):
        self._close()
        self.client.post(reverse('finance:reopen-year', args=[FY26]))
        self.assertFalse(FiscalYearClose.objects.exists())
        self.assertFalse(FundTransfer.objects.exists())
        # What Workday said stays true.
        self.assertTrue(BalanceCheckpoint.objects.filter(as_of=datetime.date(2026, 6, 30))
                        .exists())

    def test_a_write_off_cannot_exceed_what_is_owed(self):
        response = self._close(**{'write_off_%s_%s' % (self.main.pk, fund('sga_fr').pk):
                                  '301.00'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FiscalYearClose.objects.exists())

    def test_a_year_that_has_not_ended_cannot_be_closed(self):
        response = self.client.get(reverse('finance:close-year', args=[2099]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FiscalYearClose.objects.exists())


class QueueNearMissTagTests(FinanceViewTestCase):
    """ The queue row names both numbers when the memo's letter disagrees with lnldb's. """

    def test_the_tag_asks_which_letter_is_right(self):
        self.grant('view_subledger', 'edit_subledger')
        FundingRequest.objects.create(name='Summer OpEx', reference='F.27.16', fiscal_year=2027)
        line(datetime.date(2026, 7, 22), '-15.45', 'Velcro restock, consumables, (A.27.16)')
        response = self.client.get(reverse('finance:queue'), {'fy': 2027})
        self.assertContains(response, 'A.27.16 or F.27.16?')

"""
History: lines from before the books start, kept so the forecast can learn
what a year looks like, and never filed.

Four layers, tested from the bottom up:

* **Keeping them out of the books.** The books start is written down before
  older lines arrive, and lines before it stay out of the queue, the balances,
  the reports and the dashboard, and cannot be filed.
* **Reading a line.** What a line nobody filed was taken to be -- SGA's
  money, client billing, a transfer, or spending in the category the queue's
  lookups give -- and the Treasurer's correction to it.
* **Every line as flows.** Filed slices as filed, the rest read; the years
  side by side, the cash each ended on, and how much of past billing
  departments paid.
* **The pages**: the History page, a year's lines, correcting one, a history
  line's own page, and the import's confirmation.
"""
import datetime
import io
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from events.tests.generators import Event2019Factory, OrgFactory
from finance import balances, history
from finance.importers import import_workday_export
from finance.models import (ClientType, FinanceSettings, HistoryKind, HistoryOverride,
                            ParsedTransaction, TransactionStatus, WorkdayTransaction,
                            books_start_date, reset_finance_cache)
from finance.reports import Period, _unfiled
from finance.tests.test_balances import MAIN, checkpoint, filed, line
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund, revenue_source

BOOKS_START = datetime.date(2025, 7, 1)


def start_books(day=BOOKS_START):
    """ Write the books start down, as migration 0008 does on a working install. """
    config = FinanceSettings.load()
    config.ledger_start_date = day
    config.save()
    reset_finance_cache()


def old(day, amount, memo='', supplier='', employee='', document='', **worktags):
    """ A line on 226-AG with whatever Workday said about it. """
    tags = {'student_organization': MAIN}
    tags.update(worktags)
    return WorkdayTransaction.objects.create(
        operational_transaction=document, accounting_date=day, net_amount=Decimal(amount),
        memo=memo, supplier=supplier, employee=employee, worktags_json=tags)


def show(name, day, student):
    """ An event billed to a client paying from fund 810 (a student org) or 110. """
    org = OrgFactory.create(name=name + ' client', workday_fund=810 if student else 110)
    event = Event2019Factory.create(event_name=name, billing_org=org)
    event.datetime_start = datetime.datetime(day.year, day.month, day.day, 19,
                                             tzinfo=datetime.timezone.utc)
    event.datetime_end = event.datetime_start + datetime.timedelta(hours=3)
    event.save()
    return event


class HistoryTestCase(TestCase):
    """ Starts every test with clean caches, and cleans up after it. """

    def setUp(self):
        super(HistoryTestCase, self).setUp()
        reset_finance_cache()
        self.addCleanup(reset_finance_cache)


# ---------------------------------------------------------------------------
# Keeping history out of the books
# ---------------------------------------------------------------------------

class InTheBooksTests(HistoryTestCase):
    """ What is history, and what it is kept out of. """

    def setUp(self):
        super(InTheBooksTests, self).setUp()
        start_books()
        self.history = old(datetime.date(2024, 9, 1), '-300.00', 'Old cable order')
        self.books = old(datetime.date(2025, 9, 1), '-200.00', 'New cable order')

    def test_lines_before_the_books_start_are_history(self):
        self.assertTrue(self.history.is_history)
        self.assertFalse(self.books.is_history)
        self.assertEqual(list(WorkdayTransaction.objects.in_ledger()), [self.books])
        self.assertEqual(list(WorkdayTransaction.objects.before_books()), [self.history])

    def test_with_no_start_written_down_every_line_is_in_the_books(self):
        config = FinanceSettings.load()
        config.ledger_start_date = None
        config.save()
        reset_finance_cache()
        # The books then start with the fiscal year of the earliest line.
        self.assertEqual(books_start_date(), datetime.date(2024, 7, 1))
        self.assertEqual(WorkdayTransaction.objects.before_books().count(), 0)
        self.assertFalse(self.history.is_history)

    def test_history_cannot_be_filed(self):
        entry = ParsedTransaction(parent_transaction=self.history, amount=Decimal('-300.00'),
                                  effective_date=self.history.accounting_date,
                                  fund_source=fund('legacy'),
                                  lnl_spend_category=category('consumables'))
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        self.assertIn('before the books start', str(caught.exception))

    def test_a_line_in_the_books_still_files(self):
        entry = ParsedTransaction(parent_transaction=self.books, amount=Decimal('-200.00'),
                                  effective_date=self.books.accounting_date,
                                  fund_source=fund('legacy'),
                                  lnl_spend_category=category('consumables'))
        entry.full_clean()

    def test_history_is_not_unfiled_money_in_a_report(self):
        count, amount = _unfiled(Period())
        self.assertEqual((count, amount), (1, Decimal('-200.00')))

    def test_history_is_not_a_line_on_no_account(self):
        old(datetime.date(2024, 10, 1), '-50.00', student_organization='999-XX Somebody')
        self.assertEqual(balances.Books().unassigned_lines, 0)

    def test_cash_still_counts_history_back_from_a_balance(self):
        """ A Workday balance before the books start is worked forward through history. """
        checkpoint('226-AG', datetime.date(2024, 6, 30), '1000.00')
        books = balances.Books()
        self.assertEqual(books.cash_on('226-AG', datetime.date(2025, 6, 30)), Decimal('700.00'))


class ImportPinsTheBooksTests(HistoryTestCase):
    """ An older export becomes history rather than dragging the books back. """

    HEADER = ('Accounting Date,Credit Minus Debit,Operational Transaction,Supplier,'
              'Journal Line Memo,Student Organization,Ledger Account,Spend Category')

    def export(self, *rows):
        body = '\n'.join((self.HEADER,) + rows) + '\n'
        return io.BytesIO(body.encode('utf-8'))

    def row(self, day, amount, memo):
        return '%s,%s,,B&H Photo,%s,%s,71100:Supplies,Supplies' % (day, amount, memo, MAIN)

    def test_older_lines_are_counted_as_history_and_the_start_is_written_down(self):
        old(datetime.date(2025, 8, 1), '-10.00', 'Already here')
        self.assertIsNone(FinanceSettings.load().ledger_start_date)
        result = import_workday_export(self.export(
            self.row('2024-08-01', '-25.00', 'Old tape'),
            self.row('2025-09-01', '-30.00', 'New tape')), filename='mixed.csv')
        self.assertEqual((result.created_count, result.history_count, result.queue_count),
                         (2, 1, 1))
        self.assertIn('1 of them history', result.summary())
        reset_finance_cache()
        self.assertEqual(FinanceSettings.load().ledger_start_date, BOOKS_START)
        self.assertEqual(WorkdayTransaction.objects.before_books().count(), 1)

    def test_a_dry_run_writes_nothing_down(self):
        old(datetime.date(2025, 8, 1), '-10.00', 'Already here')
        result = import_workday_export(self.export(self.row('2024-08-01', '-25.00', 'Old')),
                                       filename='old.csv', dry_run=True)
        self.assertEqual(result.history_count, 1)
        self.assertIsNone(FinanceSettings.load().ledger_start_date)

    def test_the_first_import_starts_the_books_where_it_does(self):
        result = import_workday_export(self.export(self.row('2024-08-01', '-25.00', 'Old')),
                                       filename='first.csv')
        self.assertEqual(result.history_count, 0)
        self.assertIsNone(FinanceSettings.load().ledger_start_date)

    def test_a_start_already_written_down_is_kept(self):
        start_books(datetime.date(2025, 9, 1))
        old(datetime.date(2025, 9, 2), '-10.00', 'Already here')
        import_workday_export(self.export(self.row('2024-08-01', '-25.00', 'Old')),
                              filename='old.csv')
        reset_finance_cache()
        self.assertEqual(FinanceSettings.load().ledger_start_date, datetime.date(2025, 9, 1))


class HistoryOutOfThePagesTests(FinanceViewTestCase):
    """ History is never work: the queue and the dashboard do not count it. """

    def setUp(self):
        super(HistoryOutOfThePagesTests, self).setUp()
        reset_finance_cache()
        self.addCleanup(reset_finance_cache)
        start_books()
        self.grant('view_subledger', 'edit_subledger')
        self.history = self.make_txn(op='OT-OLD', date=datetime.date(2024, 9, 1),
                                     memo='Old cable order', org=MAIN)
        self.books = self.make_txn(op='OT-NEW', date=datetime.date(2025, 9, 1),
                                   memo='New cable order', org=MAIN)

    def test_the_queue_leaves_history_out(self):
        response = self.client.get(reverse('finance:queue') + '?fy=all&partition=all')
        self.assertEqual(response.context['queue_count'], 1)
        self.assertContains(response, 'OT-NEW')
        self.assertNotContains(response, 'OT-OLD')

    def test_the_dashboard_does_not_count_history_as_unreconciled(self):
        response = self.client.get(reverse('finance:dashboard') + '?fy=all&partition=all')
        self.assertEqual(response.context['unreconciled_count'], 1)

    def test_a_history_line_shows_how_it_is_read_and_no_split(self):
        response = self.client.get(reverse('finance:txn-detail', args=[self.history.pk]))
        self.assertContains(response, 'before the books start')
        self.assertContains(response, 'Consumables')
        self.assertNotContains(response, 'fin-split-save')
        self.assertContains(response, reverse('finance:history-line', args=[self.history.pk]))

    def test_a_line_in_the_books_still_splits(self):
        response = self.client.get(reverse('finance:txn-detail', args=[self.books.pk]))
        self.assertContains(response, 'fin-split-save')

    def test_the_import_confirmation_says_which_lines_are_history(self):
        self.grant('import_workdaytransaction')
        body = ('Accounting Date,Credit Minus Debit,Operational Transaction,Supplier,'
                'Journal Line Memo,Student Organization\n'
                '2024-10-01,-25.00,OT-A,B&H,Old tape,%s\n'
                '2025-10-01,-30.00,OT-B,B&H,New tape,%s\n' % (MAIN, MAIN))
        upload = SimpleUploadedFile('journal.csv', body.encode('utf-8'), content_type='text/csv')
        response = self.client.post(reverse('finance:upload'), {'csv_file': upload})
        self.assertContains(response, '1 unreconciled line')
        self.assertContains(response, '1 line of history')
        self.assertContains(response, 'kept for the forecast')


# ---------------------------------------------------------------------------
# Reading a line
# ---------------------------------------------------------------------------

class ReadingTests(HistoryTestCase):
    """ What a line nobody filed is taken to be, from the line alone. """

    def setUp(self):
        super(ReadingTests, self).setUp()
        start_books()
        self.day = datetime.date(2024, 10, 1)

    def read(self, *args, **kwargs):
        return history.read_line(old(self.day, *args, **kwargs))

    def test_the_sga_account_is_sga_both_ways(self):
        paid = self.read('8800.00', 'F.25 New IMB', ledger_account='74600:Event Sponsorship')
        taken = self.read('-1500.00', 'Doubled', ledger_account='74600:Event Sponsorship')
        self.assertEqual((paid.kind, taken.kind), (HistoryKind.SGA, HistoryKind.SGA))
        self.assertIn('74600', paid.reason)

    def test_an_sga_journal_entry_quoting_a_request_is_sga(self):
        reading = self.read('400.00', 'F.25.33 Film Rights', journal='25010001-JE - WPI',
                            ledger_account='79999:Somewhere Else')
        self.assertEqual(reading.kind, HistoryKind.SGA)

    def test_money_in_on_a_billing_account_is_client_billing(self):
        for account in ('70050:Internal Service Provider Revenue',
                        '70000:Interdepartmental Transfers - IDT'):
            reading = self.read('500.00', 'LNL Services for NSO', ledger_account=account)
            self.assertEqual(reading.kind, HistoryKind.BILLING, account)

    def test_an_internal_service_delivery_paying_in_is_client_billing(self):
        reading = self.read('300.00', 'Lens and Lights services for Gala',
                            document='Internal Service Delivery: 24100001-ISD')
        self.assertEqual(reading.kind, HistoryKind.BILLING)

    def test_money_in_from_nobody_is_other(self):
        reading = self.read('3746.12', 'transfer from our projection account',
                            ledger_account='74800:Other Expenses')
        self.assertEqual(reading.kind, HistoryKind.OTHER)

    def test_spending_takes_the_category_the_lookups_give(self):
        reading = self.read('-45.00', 'Gaff tape', supplier='B&H',
                            spend_category='Supplies', ledger_account='71100:Supplies')
        self.assertEqual((reading.kind, reading.category),
                         (HistoryKind.SPENDING, category('consumables').pk))
        self.assertIn('Supplies', reading.reason)

    def test_money_back_from_a_supplier_is_a_refund_in_its_category(self):
        reading = self.read('45.00', 'Return', supplier='B&H', spend_category='Supplies')
        self.assertEqual((reading.kind, reading.category),
                         (HistoryKind.SPENDING, category('consumables').pk))
        self.assertIn('Money back', reading.reason)

    def test_a_wording_rule_does_not_decide_a_category(self):
        """ "Contains supplies" is a guess; with nothing else, the line is not worked out. """
        reading = self.read('-45.00', 'more supplies', supplier='B&H')
        self.assertEqual((reading.kind, reading.category), (HistoryKind.SPENDING, None))

    def test_a_memo_quoting_a_request_is_spending_sga_pays_back(self):
        reading = self.read('-946.00', 'Rights for WALL-E (F.26.86)', supplier='Swank',
                            spend_category='Supplies')
        self.assertEqual(reading.reference, 'F.26.86')
        self.assertIn('SGA pays it back', reading.reason)


class CorrectionTests(HistoryTestCase):
    """ The Treasurer's correction wins, and says so. """

    def setUp(self):
        super(CorrectionTests, self).setUp()
        start_books()
        self.txn = old(datetime.date(2024, 10, 1), '-3050.00', 'Contract for rentals',
                       supplier='Somebody', spend_category='Supplies')

    def correct(self, **fields):
        override = HistoryOverride.objects.create(line=self.txn, **fields)
        return history.reading_for(self.txn, override)

    def test_a_new_category(self):
        reading = self.correct(spend_category=category('event_subrental'))
        self.assertEqual(reading.category, category('event_subrental').pk)
        self.assertTrue(reading.corrected)
        self.assertEqual(reading.estimate.category, category('consumables').pk)

    def test_a_new_kind_drops_the_category(self):
        reading = self.correct(kind=HistoryKind.OTHER)
        self.assertEqual((reading.kind, reading.category), (HistoryKind.OTHER, None))

    def test_leaving_it_out_keeps_the_reading(self):
        reading = self.correct(leave_out=True, note='One-off')
        self.assertTrue(reading.left_out)
        self.assertFalse(reading.corrected)
        self.assertEqual(reading.category, category('consumables').pk)
        self.assertEqual(reading.note, 'One-off')


# ---------------------------------------------------------------------------
# Every line as flows
# ---------------------------------------------------------------------------

class LedgerFlowTests(HistoryTestCase):
    """ Filed slices as filed, the rest read, all as one list. """

    def setUp(self):
        super(LedgerFlowTests, self).setUp()
        start_books()

    def flows_for(self, txn):
        return [flow for flow in history.Ledger().flows if flow.line == txn.pk]

    def test_a_history_line_is_read_and_its_reading_kept(self):
        txn = old(datetime.date(2024, 10, 1), '-45.00', 'Tape', supplier='B&H',
                  spend_category='Supplies')
        ledger = history.Ledger()
        (flow,) = [f for f in ledger.flows if f.line == txn.pk]
        self.assertEqual((flow.kind, flow.category, flow.amount, flow.account, flow.estimated),
                         (HistoryKind.SPENDING, category('consumables').pk, Decimal('-45.00'),
                          '226-AG', True))
        self.assertIn(txn.pk, ledger.readings)

    def test_a_filed_line_is_its_slices(self):
        txn = line(datetime.date(2025, 9, 1), '-500.00', 'Console')
        filed(txn, 'sga_fr', lnl_spend_category=category('consumables'),
              fr_line_target=self.request_line())
        (flow,) = self.flows_for(txn)
        self.assertEqual((flow.kind, flow.estimated, flow.sga_paid),
                         (HistoryKind.SPENDING, False, True))

    def test_what_is_left_of_a_half_filed_line_is_read(self):
        txn = old(datetime.date(2025, 9, 1), '-500.00', 'Two things', supplier='B&H',
                  spend_category='Supplies')
        ParsedTransaction.objects.create(
            parent_transaction=txn, amount=Decimal('-200.00'), effective_date=txn.accounting_date,
            status=TransactionStatus.PENDING, fund_source=fund('legacy'),
            lnl_spend_category=category('food'))
        flows = sorted(self.flows_for(txn), key=lambda f: f.amount)
        self.assertEqual([(f.amount, f.category, f.estimated) for f in flows],
                         [(Decimal('-300.00'), category('consumables').pk, True),
                          (Decimal('-200.00'), category('food').pk, False)])

    def test_sga_money_filed_either_way_is_sga(self):
        request = self.request_line().funding_request
        paid = line(datetime.date(2025, 10, 1), '800.00', 'F.27.4 Rentals')
        filed(paid, 'sga_fr', non_event_revenue_type=revenue_source('sga_fr_reimbursement'),
              funding_request=request)
        taken = line(datetime.date(2025, 11, 1), '-100.00', 'SGA took back F.27.4')
        filed(taken, 'sga_fr', funding_request=request)
        self.assertEqual([f.kind for f in self.flows_for(paid) + self.flows_for(taken)],
                         [HistoryKind.SGA, HistoryKind.SGA])

    def test_billing_filed_against_an_event_knows_who_paid(self):
        event = show('Orientation', datetime.date(2025, 8, 20), student=False)
        txn = line(datetime.date(2025, 9, 1), '1000.00', 'LNL Services for Orientation')
        filed(txn, 'legacy', linked_event=event)
        (flow,) = self.flows_for(txn)
        self.assertEqual((flow.kind, flow.client_type),
                         (HistoryKind.BILLING, ClientType.DEPARTMENT))

    def test_a_left_out_line_is_marked(self):
        txn = old(datetime.date(2024, 10, 1), '-39310.55', 'Conversion',
                  ledger_account='74800:Other Expenses')
        HistoryOverride.objects.create(line=txn, leave_out=True)
        (flow,) = self.flows_for(txn)
        self.assertTrue(flow.left_out)

    def test_a_whole_year_needs_nine_months_of_lines(self):
        for month in range(1, 10):
            old(datetime.date(2024, month, 15), '-10.00', 'Tape')    # FY24 Jan-Jun, FY25 Jul-Sep
        for month in (7, 8, 9, 10, 11, 12):
            old(datetime.date(2022, month, 15), '-10.00', 'Tape')    # FY23: six months
        for month in (1, 2, 3):
            old(datetime.date(2023, month, 15), '-10.00', 'Tape')    # FY23: nine in all
        ledger = history.Ledger()
        self.assertEqual(ledger.months_covered('226-AG'), {2023: 9, 2024: 6, 2025: 3})
        self.assertEqual(ledger.whole_years('226-AG', before=2027), [2023])

    def request_line(self):
        from finance.models import FRLineItem, FundingRequest

        request = FundingRequest.objects.create(name='Shows', reference='F.27.4',
                                                fiscal_year=2027)
        return FRLineItem.objects.create(funding_request=request, name='Rentals',
                                         amount_awarded=Decimal('5000.00'))


class YearSummaryTests(HistoryTestCase):
    """ Each year side by side, and the cash it ended on. """

    def setUp(self):
        super(YearSummaryTests, self).setUp()
        start_books()
        old(datetime.date(2024, 8, 1), '1000.00', 'LNL Services',
            ledger_account='70050:Internal Service Provider Revenue')
        old(datetime.date(2024, 9, 1), '-300.00', 'Tape', supplier='B&H',
            spend_category='Supplies')
        old(datetime.date(2024, 10, 1), '50.00', 'Return', supplier='B&H',
            spend_category='Supplies')
        old(datetime.date(2024, 11, 1), '200.00', 'F.25 Lamp',
            ledger_account='74600:Event Sponsorship')
        left = old(datetime.date(2024, 12, 1), '-5000.00', 'Conversion',
                   ledger_account='74800:Other Expenses')
        HistoryOverride.objects.create(line=left, leave_out=True)

    def test_a_year_adds_up_by_kind_and_category(self):
        (row,) = history.year_summary(history.Ledger(), '226-AG')
        self.assertEqual(row['year'], 2025)
        self.assertEqual((row['billing'], row['sga'], row['other']),
                         (Decimal('1000.00'), Decimal('200.00'), Decimal('0.00')))
        self.assertEqual(row['spending'][category('consumables').pk], Decimal('-250.00'))
        self.assertEqual(row['spent'], Decimal('-250.00'))
        self.assertEqual(row['net'], Decimal('950.00'))
        self.assertEqual(row['left_out'], Decimal('-5000.00'))
        self.assertEqual((row['lines'], row['estimated'], row['months']), (5, 5, 5))

    def test_cash_works_back_from_a_workday_balance(self):
        checkpoint('226-AG', datetime.date(2025, 6, 30), '10000.00')
        self.assertEqual(history.june_cash('226-AG', [2024, 2025]),
                         {2024: Decimal('14050.00'), 2025: Decimal('10000.00')})

    def test_no_balance_no_cash(self):
        self.assertEqual(history.june_cash('226-AG', [2025]), {})


class DepartmentShareTests(HistoryTestCase):
    """ How much of the billing before FY27 departments paid. """

    def setUp(self):
        super(DepartmentShareTests, self).setUp()
        start_books()

    def bill(self, name, amount, student):
        event = show(name, datetime.date(2025, 9, 1), student)
        txn = line(datetime.date(2025, 10, 1), amount, 'LNL Services for %s' % name)
        filed(txn, 'legacy', linked_event=event)

    def test_a_share_set_by_hand_wins(self):
        config = FinanceSettings.load()
        config.department_billing_share = 40
        config.save()
        reset_finance_cache()
        share = history.department_share([])
        self.assertEqual((share.share, share.percent, share.source), (Decimal('0.4'), 40, 'set'))

    def test_worked_out_from_billing_filed_against_events(self):
        self.bill('Orientation', '600.00', student=False)
        self.bill('Spring Musical', '400.00', student=True)
        share = history.department_share(history.Ledger().flows)
        self.assertEqual((share.share, share.source), (Decimal('0.6'), 'measured'))

    def test_unknown_until_half_the_billing_is_filed_against_events(self):
        self.bill('Orientation', '600.00', student=False)
        old(datetime.date(2025, 11, 1), '1000.00', 'LNL Services for something',
            ledger_account='70050:Internal Service Provider Revenue')
        share = history.department_share(history.Ledger().flows)
        self.assertFalse(share.known)
        self.assertIn('$600 of $1,600', share.detail)

    def test_history_cannot_say_who_paid(self):
        old(datetime.date(2024, 11, 1), '1000.00', 'LNL Services for something',
            ledger_account='70050:Internal Service Provider Revenue')
        share = history.department_share(history.Ledger().flows)
        self.assertFalse(share.known)
        self.assertIn('no billing from before FY27 is in the books', share.detail)


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class HistoryPageTests(FinanceViewTestCase):
    """ The History page, a year's lines, and correcting one. """

    def setUp(self):
        super(HistoryPageTests, self).setUp()
        reset_finance_cache()
        self.addCleanup(reset_finance_cache)
        start_books()
        self.grant('view_subledger')
        self.tape = old(datetime.date(2024, 9, 1), '-45.00', 'Gaff tape', supplier='B&H',
                        spend_category='Supplies')
        self.show = old(datetime.date(2024, 9, 5), '500.00', 'LNL Services for NSO',
                        ledger_account='70050:Internal Service Provider Revenue')
        old(datetime.date(2024, 9, 9), '-20.00', 'Licence', supplier='FCC',
            spend_category='Licenses & Fees')

    def test_the_history_page_shows_each_year(self):
        response = self.client.get(reverse('finance:history'))
        self.assertContains(response, 'FY25')
        self.assertContains(response, 'Client billing')
        self.assertContains(response, '$500.00')
        self.assertContains(response, 'Consumables')
        # A Workday category nothing reads is pointed out.
        self.assertContains(response, 'Licenses &amp; Fees')
        self.assertContains(response, 'departments')

    def test_a_years_lines_with_how_each_is_read(self):
        response = self.client.get(reverse('finance:history-year', args=[2025]))
        self.assertContains(response, 'Gaff tape')
        self.assertContains(response, 'Workday spend category')
        narrowed = self.client.get(reverse('finance:history-year', args=[2025])
                                   + '?kind=billing')
        self.assertContains(narrowed, 'LNL Services for NSO')
        self.assertNotContains(narrowed, 'Gaff tape')
        by_category = self.client.get(reverse('finance:history-year', args=[2025])
                                      + '?category=%s' % category('consumables').pk)
        self.assertContains(by_category, 'Gaff tape')
        self.assertNotContains(by_category, 'LNL Services for NSO')

    def test_a_year_in_the_books_is_the_ledger(self):
        response = self.client.get(reverse('finance:history-year', args=[2026]))
        self.assertRedirects(response, reverse('finance:ledger') + '?fy=2026',
                             fetch_redirect_response=False)

    def test_correcting_a_line(self):
        self.grant('edit_subledger')
        url = reverse('finance:history-line', args=[self.tape.pk])
        self.assertContains(self.client.get(url), 'What the line itself says')
        response = self.client.post(url, {'kind': '', 'spend_category': category('food').pk,
                                          'leave_out': 'on', 'note': 'Pizza, really'})
        self.assertEqual(response.status_code, 302)
        override = HistoryOverride.objects.get(line=self.tape)
        self.assertEqual((override.spend_category, override.leave_out, override.updated_by),
                         (category('food'), True, self.user))
        self.client.post(url, {'clear': '1'})
        self.assertFalse(HistoryOverride.objects.filter(line=self.tape).exists())

    def test_saving_an_empty_correction_removes_it(self):
        self.grant('edit_subledger')
        HistoryOverride.objects.create(line=self.tape, leave_out=True)
        self.client.post(reverse('finance:history-line', args=[self.tape.pk]),
                         {'kind': '', 'spend_category': '', 'note': ''})
        self.assertFalse(HistoryOverride.objects.filter(line=self.tape).exists())

    def test_reading_without_editing(self):
        url = reverse('finance:history-line', args=[self.tape.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {'leave_out': 'on'}).status_code, 404)
        self.assertFalse(HistoryOverride.objects.exists())

    def test_a_line_in_the_books_has_no_correction(self):
        books = old(datetime.date(2025, 9, 1), '-45.00', 'Tape')
        response = self.client.get(reverse('finance:history-line', args=[books.pk]))
        self.assertEqual(response.status_code, 404)

    def test_needs_the_view_permission(self):
        self.user.user_permissions.clear()
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('finance:history')).status_code, 403)

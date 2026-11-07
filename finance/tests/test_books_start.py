"""
The books start: always the first day of the fiscal year of the earliest
line on file, and never set by hand.

Every line imported is in the books and is settled, however old. Nothing is
kept aside: the queue, the dashboard, the balances and the reports count every
line, and an export older than anything on file moves the books back to meet
it. The import's confirmation says so before anything is saved, and names
what was entered for the old start -- the opening split, and what SGA owed on
each request then -- without changing it.
"""
import datetime
import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from finance import balances
from finance.importers import import_workday_export
from finance.models import (FundTransfer, ParsedTransaction, WorkdayTransaction,
                            books_start_date, reset_finance_cache)
from finance.reports import Period, _unfiled
from finance.tests.test_balances import MAIN, account, checkpoint
from finance.tests.test_revenue_sources import make_request
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund


def old(day, amount, memo='', **worktags):
    """ A line on 226-AG with whatever Workday said about it. """
    tags = {'student_organization': MAIN}
    tags.update(worktags)
    return WorkdayTransaction.objects.create(
        operational_transaction='OT-%s-%s' % (day.isoformat(), amount), accounting_date=day,
        net_amount=Decimal(amount), memo=memo, worktags_json=tags)


class BooksStartTestCase(TestCase):
    """ Starts every test with clean caches, and cleans up after it. """

    def setUp(self):
        super(BooksStartTestCase, self).setUp()
        reset_finance_cache()
        self.addCleanup(reset_finance_cache)


# ---------------------------------------------------------------------------
# Every line is in the books
# ---------------------------------------------------------------------------

class EveryLineTests(BooksStartTestCase):
    """ An old line is in the books like any other. """

    def setUp(self):
        super(EveryLineTests, self).setUp()
        self.older = old(datetime.date(2024, 9, 1), '-300.00', 'Old cable order')
        self.newer = old(datetime.date(2025, 9, 1), '-200.00', 'New cable order')

    def test_the_books_start_with_the_oldest_line(self):
        self.assertEqual(books_start_date(), datetime.date(2024, 7, 1))

    def test_every_line_waits_to_be_settled(self):
        self.assertEqual(set(WorkdayTransaction.objects.unreconciled()), {self.older, self.newer})

    def test_an_old_line_settles(self):
        entry = ParsedTransaction(parent_transaction=self.older, amount=Decimal('-300.00'),
                                  effective_date=self.older.accounting_date,
                                  fund_source=fund('legacy'),
                                  lnl_spend_category=category('consumables'))
        entry.full_clean()

    def test_every_line_is_unsettled_money_in_a_report(self):
        self.assertEqual(_unfiled(Period()), (2, Decimal('-500.00')))

    def test_an_old_line_on_no_account_is_counted(self):
        old(datetime.date(2024, 10, 1), '-50.00', student_organization='999-XX Somebody')
        self.assertEqual(balances.Books().unassigned_lines, 1)

    def test_cash_counts_every_line_from_a_balance(self):
        checkpoint('226-AG', datetime.date(2024, 6, 30), '1000.00')
        books = balances.Books()
        self.assertEqual(books.cash_on('226-AG', datetime.date(2025, 6, 30)), Decimal('700.00'))


# ---------------------------------------------------------------------------
# An older export moves the books back
# ---------------------------------------------------------------------------

class ImportMovesTheBooksTests(BooksStartTestCase):
    """ Nothing is pinned: an older export joins the books and moves their start. """

    HEADER = ('Accounting Date,Credit Minus Debit,Operational Transaction,Supplier,'
              'Journal Line Memo,Student Organization,Ledger Account,Spend Category')

    def export(self, *rows):
        body = '\n'.join((self.HEADER,) + rows) + '\n'
        return io.BytesIO(body.encode('utf-8'))

    def row(self, day, amount, memo):
        return '%s,%s,,B&H Photo,%s,%s,71100:Supplies,Supplies' % (day, amount, memo, MAIN)

    def test_an_older_export_joins_the_queue_and_moves_the_books(self):
        old(datetime.date(2025, 8, 1), '-10.00', 'Already here')
        result = import_workday_export(self.export(
            self.row('2018-09-04', '-25.00', 'Old tape'),
            self.row('2025-09-01', '-30.00', 'New tape')), filename='mixed.csv')
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.new_books_start, datetime.date(2018, 7, 1))
        self.assertEqual(result.summary(), '2 imported, 0 skipped as duplicates, 0 errors')
        self.assertEqual(books_start_date(), datetime.date(2018, 7, 1))
        self.assertEqual(WorkdayTransaction.objects.unreconciled().count(), 3)

    def test_a_dry_run_says_where_the_books_would_start(self):
        old(datetime.date(2025, 8, 1), '-10.00', 'Already here')
        result = import_workday_export(self.export(self.row('2024-08-01', '-25.00', 'Old')),
                                       filename='old.csv', dry_run=True)
        self.assertEqual(result.new_books_start, datetime.date(2024, 7, 1))
        self.assertEqual(books_start_date(), datetime.date(2025, 7, 1))

    def test_a_newer_export_leaves_the_start_alone(self):
        old(datetime.date(2025, 8, 1), '-10.00', 'Already here')
        result = import_workday_export(self.export(self.row('2025-09-01', '-25.00', 'New')),
                                       filename='new.csv', dry_run=True)
        self.assertIsNone(result.new_books_start)

    def test_the_first_import_has_nothing_to_move(self):
        result = import_workday_export(self.export(self.row('2024-08-01', '-25.00', 'Old')),
                                       filename='first.csv', dry_run=True)
        self.assertIsNone(result.new_books_start)


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class PagesTests(FinanceViewTestCase):
    """ The queue, the dashboard and a line's page treat an old line as any other. """

    def setUp(self):
        super(PagesTests, self).setUp()
        reset_finance_cache()
        self.addCleanup(reset_finance_cache)
        self.grant('view_subledger', 'edit_subledger')
        self.older = self.make_txn(op='OT-OLD', date=datetime.date(2024, 9, 1),
                                   memo='Old cable order', org=MAIN)
        self.newer = self.make_txn(op='OT-NEW', date=datetime.date(2025, 9, 1),
                                   memo='New cable order', org=MAIN)

    def upload(self, *rows):
        self.grant('import_workdaytransaction')
        body = ('Accounting Date,Credit Minus Debit,Operational Transaction,Supplier,'
                'Journal Line Memo,Student Organization\n' + ''.join(rows))
        upload = SimpleUploadedFile('journal.csv', body.encode('utf-8'), content_type='text/csv')
        return self.client.post(reverse('finance:upload'), {'csv_file': upload})

    def test_the_queue_holds_every_line(self):
        response = self.client.get(reverse('finance:queue') + '?fy=all&partition=all')
        self.assertEqual(response.context['queue_count'], 2)
        self.assertContains(response, 'OT-NEW')
        self.assertContains(response, 'OT-OLD')

    def test_the_dashboard_counts_every_line(self):
        response = self.client.get(reverse('finance:dashboard') + '?fy=all&partition=all')
        self.assertEqual(response.context['unreconciled_count'], 2)

    def test_an_old_line_splits(self):
        response = self.client.get(reverse('finance:txn-detail', args=[self.older.pk]))
        self.assertContains(response, 'fin-split-save')

    def test_the_confirmation_counts_every_line_for_the_queue(self):
        response = self.upload('2025-10-01,-30.00,OT-B,B&H,New tape,%s\n' % MAIN)
        self.assertContains(response, '1 line to settle')
        self.assertNotContains(response, 'the books will start on')

    def test_the_confirmation_says_the_books_move_and_what_to_look_at(self):
        FundTransfer.objects.create(
            account=account('226-AG'), date=datetime.date(2024, 7, 1),
            amount=Decimal('300.00'), from_fund=fund('sga_fr'), to_fund=fund('legacy'),
            kind=FundTransfer.OPENING, description='Opening')
        make_request(owed_at_books_start=Decimal('25.00'))
        response = self.upload('2018-09-04,-25.00,OT-A,B&H,Old tape,%s\n' % MAIN)
        self.assertContains(response, '1 line to settle')
        self.assertContains(response, 'the books will start on')
        self.assertContains(response, 'Jul 1, 2018')
        self.assertContains(response, reverse('finance:opening-balances'))
        self.assertContains(response, 'F.26.86')

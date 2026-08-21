"""
The ingestion queue's reporting, its encumbrances, and settling.

The flows themselves -- the two-step import, undo, bulk reconcile -- are
covered in ``test_views``. What is here is everything those flows *say*: the
warnings after an import, the messages when something is refused, and the
paths that only run when a file or a selection is not what was expected.

That reporting is not decoration. An import that silently drops eleven rows, or
a settle that quietly does nothing, is indistinguishable from one that worked,
and this module is the only thing that notices the difference.
"""
import datetime
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from finance.models import (ParsedTransaction, SpendCategory, SuggestionRule,
                            TransactionStatus, WorkdayTransaction)
from finance.tests.test_views import CSV_HEADER, CSV_ROW, FinanceViewTestCase
from finance.tests.util import category, fund


class ImportReportingTests(FinanceViewTestCase):
    """ What an import tells the Treasurer about the file they just chose. """

    def setUp(self):
        super(ImportReportingTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'import_workdaytransaction')

    def _upload(self, body, **extra):
        upload = SimpleUploadedFile('journal.csv', body.encode('utf-8'),
                                    content_type='text/csv')
        data = {'csv_file': upload}
        data.update(extra)
        return self.client.post(reverse('finance:upload'), data, follow=True)

    def _rows(self, count, start=9100, spend_category=None):
        """
        ``count`` distinct expense rows, so nothing is skipped as a duplicate.

        Built through the csv module rather than by splitting on commas:
        ``CSV_ROW`` carries ``"(1,200.00)"``, and a naive split lands the
        Operational Transaction in the amount column -- which produces a file
        full of unreadable rows and a test that passes for the wrong reason.
        """
        import csv as csv_module

        columns = next(csv_module.reader([CSV_HEADER]))
        template = next(csv_module.reader([CSV_ROW]))
        op = columns.index('Operational Transaction')
        memo = columns.index('Journal Line Memo')
        spend = columns.index('Spend Category')

        out = io.StringIO()
        writer = csv_module.writer(out, lineterminator='\n')
        writer.writerow(columns)
        for index in range(count):
            cells = list(template)
            cells[op] = 'OT-%s' % (start + index)
            cells[memo] = 'Line %s' % index
            if spend_category is not None:
                cells[spend] = spend_category
            writer.writerow(cells)
        return out.getvalue()

    def test_an_unreadable_row_is_named_with_its_line_number(self):
        """ "Row 14 is wrong" is actionable; "some rows were wrong" is not. """
        broken = CSV_ROW.replace('09/15/2025', 'the fifteenth')
        response = self._upload(CSV_HEADER + "\n" + broken + "\n")
        self.assertContains(response, 'Line 2')
        self.assertContains(response, 'Accounting Date')

    def test_a_zero_amount_row_is_reported_rather_than_imported(self):
        """ There is nothing to reconcile, so it is a data problem, not a line. """
        zero = CSV_ROW.replace('"(1,200.00)"', '0.00')
        response = self._upload(CSV_HEADER + "\n" + zero + "\n")
        self.assertContains(response, 'nothing to reconcile')
        self.assertFalse(WorkdayTransaction.objects.exists())

    def test_only_the_first_ten_bad_rows_are_listed(self):
        """ A wholly malformed file must not produce a page of red banners. """
        broken = [CSV_ROW.replace('09/15/2025', 'nope').replace('OT-9001', 'OT-B%s' % i)
                  for i in range(14)]
        response = self._upload(CSV_HEADER + "\n" + "\n".join(broken) + "\n")
        self.assertContains(response, 'and 4 more problem rows')

    def test_a_workday_category_nothing_maps_is_named_after_the_import(self):
        """
        Each one is a category the Treasurer would otherwise pick by hand on
        every line carrying it, forever. One admin row ends that, so the moment
        it first appears is the moment to say so.
        """
        body = self._rows(1, spend_category='Balloon Animals')
        self._upload(body)
        response = self.client.post(reverse('finance:upload-confirm'), {}, follow=True)
        self.assertContains(response, 'No spend category rule covers')
        self.assertContains(response, 'Balloon Animals')

    def test_the_wording_matches_the_number_of_unmapped_categories(self):
        rows = [CSV_ROW.replace('OT-9001', 'OT-U1').replace('Supplies', 'Balloon Animals'),
                CSV_ROW.replace('OT-9001', 'OT-U2').replace('Supplies', 'Kazoo Rental')]
        self._upload(CSV_HEADER + "\n" + "\n".join(rows) + "\n")
        response = self.client.post(reverse('finance:upload-confirm'), {}, follow=True)
        self.assertContains(response, 'these Workday categories')

    def test_a_mapped_category_produces_no_warning(self):
        self._upload(self._rows(1))
        response = self.client.post(reverse('finance:upload-confirm'), {}, follow=True)
        self.assertNotContains(response, 'No spend category rule covers')

    def test_an_unrecognised_column_is_kept_and_reported(self):
        """
        Dropping it would lose data; renaming it silently would hide that
        Workday changed the export. So it lands in worktags and says so.
        """
        header = CSV_HEADER + ',Reconciliation Note'
        row = CSV_ROW + ',checked twice'
        self._upload(header + "\n" + row + "\n")
        response = self.client.post(reverse('finance:upload-confirm'), {}, follow=True)
        self.assertContains(response, 'stored as worktags')
        self.assertContains(response, 'Reconciliation Note')
        txn = WorkdayTransaction.objects.get(operational_transaction='OT-9001')
        self.assertEqual(txn.worktags_json['reconciliation_note'], 'checked twice')

    def test_a_file_that_is_not_an_export_is_refused_before_anything_is_staged(self):
        response = self._upload("Name,Email\nfoo,bar\n")
        self.assertContains(response, 'Workday journal export')
        self.assertNotContains(response, 'about to add')

    def test_an_empty_file_is_refused_clearly(self):
        response = self._upload("")
        self.assertContains(response, 'empty')

    def test_the_confirmation_reports_what_will_be_skipped(self):
        self._upload(self._rows(1))
        self.client.post(reverse('finance:upload-confirm'), {}, follow=True)
        response = self._upload(self._rows(2))
        self.assertContains(response, 'about to add')
        self.assertContains(response, 'Already imported')

    def test_importing_needs_the_import_permission(self):
        reader = get_user_model().objects.create_user(
            username='reader9', email='reader9@wpi.edu', password='x')
        reader.user_permissions.add(Permission.objects.get(codename='view_subledger'))
        self.client.force_login(get_user_model().objects.get(pk=reader.pk))
        upload = SimpleUploadedFile('journal.csv', (CSV_HEADER + "\n" + CSV_ROW).encode(),
                                    content_type='text/csv')
        response = self.client.post(reverse('finance:upload'), {'csv_file': upload})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(WorkdayTransaction.objects.exists())

    def test_a_rejected_upload_form_reports_its_own_errors(self):
        """ Wrong extension, oversized file: caught before the importer runs. """
        upload = SimpleUploadedFile('journal.docx', b'not a journal',
                                    content_type='application/msword')
        response = self.client.post(reverse('finance:upload'), {'csv_file': upload},
                                    follow=True)
        self.assertContains(response, 'neither a CSV nor an .xlsx')


class StagedImportTests(FinanceViewTestCase):
    """
    The file waiting between "choose" and "confirm".

    It is the only piece of an import that lives outside the database, so its
    lifecycle is worth pinning down: consumed on confirm, deleted on cancel,
    and never readable by anyone else.
    """

    def setUp(self):
        super(StagedImportTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'import_workdaytransaction')

    def _choose(self):
        upload = SimpleUploadedFile(
            'journal.csv', (CSV_HEADER + "\n" + CSV_ROW + "\n").encode('utf-8'),
            content_type='text/csv')
        return self.client.post(reverse('finance:upload'), {'csv_file': upload}, follow=True)

    def _staged_token(self):
        from finance.views.ingest import STAGED_SESSION_KEY
        return (self.client.session.get(STAGED_SESSION_KEY) or {}).get('token')

    def test_choosing_a_file_stages_it(self):
        from django.core.files.storage import default_storage
        self._choose()
        token = self._staged_token()
        self.assertTrue(token)
        self.assertTrue(default_storage.exists(token))
        self.addCleanup(default_storage.delete, token)

    def test_confirming_consumes_the_staged_file(self):
        from django.core.files.storage import default_storage
        self._choose()
        token = self._staged_token()
        self.client.post(reverse('finance:upload-confirm'), {}, follow=True)
        self.assertFalse(default_storage.exists(token))
        self.assertIsNone(self._staged_token())

    def test_cancelling_deletes_it(self):
        from django.core.files.storage import default_storage
        self._choose()
        token = self._staged_token()
        self.client.post(reverse('finance:upload-confirm'), {'cancel': '1'}, follow=True)
        self.assertFalse(default_storage.exists(token))
        self.assertFalse(WorkdayTransaction.objects.exists())

    def test_choosing_a_second_file_replaces_the_first(self):
        """ Otherwise an abandoned choice sits in the store until it expires. """
        from django.core.files.storage import default_storage
        self._choose()
        first = self._staged_token()
        self._choose()
        second = self._staged_token()
        self.addCleanup(default_storage.delete, second)
        self.assertNotEqual(first, second)
        self.assertFalse(default_storage.exists(first))

    def test_a_token_outside_the_staging_area_is_refused(self):
        """
        The token names a path in the file store, so it is checked rather than
        trusted -- otherwise it would read any file the store can reach.
        """
        from finance.importers import read_staged
        self.assertIsNone(read_staged('finance/receipts/2025/09/someone-elses.pdf'))
        self.assertIsNone(read_staged('../../secrets'))
        self.assertIsNone(read_staged(''))
        self.assertIsNone(read_staged(None))

    def test_a_confirmation_with_nothing_staged_says_so(self):
        response = self.client.post(reverse('finance:upload-confirm'), {}, follow=True)
        self.assertContains(response, 'no longer waiting')

    def test_a_staged_file_that_has_gone_missing_says_so(self):
        from django.core.files.storage import default_storage
        self._choose()
        default_storage.delete(self._staged_token())
        response = self.client.post(reverse('finance:upload-confirm'), {}, follow=True)
        self.assertContains(response, 'no longer waiting')
        self.assertFalse(WorkdayTransaction.objects.exists())

    def test_stale_staged_files_are_purged_by_the_next_upload(self):
        import datetime as dt
        from django.core.files.storage import default_storage
        from django.utils import timezone
        from finance.importers import STAGING_DIR, purge_stale_staged

        default_storage.save('%s/leftover' % STAGING_DIR, io.BytesIO(b'old'))
        purge_stale_staged(now=timezone.now() + dt.timedelta(hours=7))
        self.assertFalse(default_storage.exists('%s/leftover' % STAGING_DIR))

    def test_a_recent_staged_file_is_left_alone(self):
        from django.core.files.storage import default_storage
        from django.utils import timezone
        from finance.importers import STAGING_DIR, purge_stale_staged

        name = default_storage.save('%s/fresh' % STAGING_DIR, io.BytesIO(b'new'))
        self.addCleanup(default_storage.delete, name)
        purge_stale_staged(now=timezone.now())
        self.assertTrue(default_storage.exists(name))

    def test_purging_an_empty_store_is_not_an_error(self):
        """ Runs before the first ever import, when the directory does not exist. """
        from finance.importers import purge_stale_staged
        purge_stale_staged()


class EncumbranceViewTests(FinanceViewTestCase):
    """ Reserving funds for a purchase the bank feed has not seen yet. """

    def setUp(self):
        super(EncumbranceViewTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')

    def _post(self, url, **overrides):
        data = {
            'amount': '75.00',
            'effective_date': '2025-09-15',
            'description': 'Gaff tape run',
            'audit_explanation': 'Restocking the shop',
            'fund_source': str(fund('sga_budget').pk),
            'lnl_spend_category': str(category('consumables').pk),
        }
        data.update(overrides)
        return self.client.post(url, data, follow=True)

    def test_the_form_renders(self):
        response = self.client.get(reverse('finance:encumbrance-new'))
        self.assertContains(response, 'Log a Pending Purchase')

    def test_a_positive_amount_is_recorded_as_money_going_out(self):
        """
        The Treasurer types what it will cost. Making them remember the sign
        convention would be a question with one correct answer.
        """
        self._post(reverse('finance:encumbrance-new'))
        entry = ParsedTransaction.objects.get(description='Gaff tape run')
        self.assertEqual(entry.amount, Decimal('-75.00'))

    def test_it_is_saved_pending_with_no_bank_line(self):
        self._post(reverse('finance:encumbrance-new'))
        entry = ParsedTransaction.objects.get(description='Gaff tape run')
        self.assertIsNone(entry.parent_transaction)
        self.assertEqual(entry.status, TransactionStatus.PENDING)
        self.assertTrue(entry.is_encumbrance)

    def test_a_zero_amount_is_refused(self):
        self._post(reverse('finance:encumbrance-new'), amount='0')
        self.assertFalse(ParsedTransaction.objects.filter(description='Gaff tape run').exists())

    def test_an_encumbrance_can_be_edited(self):
        self._post(reverse('finance:encumbrance-new'))
        entry = ParsedTransaction.objects.get(description='Gaff tape run')
        url = reverse('finance:encumbrance-edit', args=[entry.pk])
        self.assertContains(self.client.get(url), 'Edit Encumbrance')
        self._post(url, description='Spike tape run')
        entry.refresh_from_db()
        self.assertEqual(entry.description, 'Spike tape run')

    def test_editing_does_not_reassign_the_author(self):
        """ ``created_by`` records who reserved the money, not who last touched it. """
        self._post(reverse('finance:encumbrance-new'))
        entry = ParsedTransaction.objects.get(description='Gaff tape run')
        other = get_user_model().objects.create_user(
            username='second', email='second@wpi.edu', password='x')
        for codename in ('view_subledger', 'edit_subledger'):
            other.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(get_user_model().objects.get(pk=other.pk))
        self._post(reverse('finance:encumbrance-edit', args=[entry.pk]),
                   description='Spike tape run')
        entry.refresh_from_db()
        self.assertEqual(entry.created_by, self.user)

    def test_a_reconciled_slice_cannot_be_edited_as_an_encumbrance(self):
        """ The URL only accepts rows with no bank line behind them. """
        txn = self.make_txn(op='OT-EN1', amount='-40.00')
        slice_ = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=Decimal('-40.00'),
            effective_date=txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        response = self.client.get(reverse('finance:encumbrance-edit', args=[slice_.pk]))
        self.assertEqual(response.status_code, 404)


class SettleViewTests(FinanceViewTestCase):
    """ Marking a fully-allocated bank line settled. """

    def setUp(self):
        super(SettleViewTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.txn = self.make_txn(op='OT-S1', amount='-500.00')

    def _settle(self):
        return self.client.post(reverse('finance:settle', args=[self.txn.pk]), {}, follow=True)

    def test_a_balanced_line_settles(self):
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-500.00'),
            effective_date=self.txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        response = self._settle()
        self.assertContains(response, 'settled')
        self.assertEqual(self.txn.slices.get().status, TransactionStatus.SETTLED)

    def test_a_line_with_no_allocations_is_refused_with_a_reason(self):
        response = self._settle()
        self.assertContains(response, 'no allocation slices')

    def test_an_unbalanced_line_is_refused_with_the_numbers(self):
        """ The message names both totals, because "it does not balance" is not enough. """
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-200.00'),
            effective_date=self.txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        response = self._settle()
        self.assertContains(response, 'Cannot settle')
        self.assertContains(response, '300.00')
        self.assertEqual(self.txn.slices.get().status, TransactionStatus.PENDING)

    def test_settling_needs_its_own_permission(self):
        """ Reconciling and settling are separate jobs and separate permissions. """
        editor = get_user_model().objects.create_user(
            username='editor', email='editor@wpi.edu', password='x')
        for codename in ('view_subledger', 'edit_subledger'):
            editor.user_permissions.add(Permission.objects.get(codename=codename))
        self.client.force_login(get_user_model().objects.get(pk=editor.pk))
        response = self.client.post(reverse('finance:settle', args=[self.txn.pk]))
        self.assertEqual(response.status_code, 403)

    def test_a_get_settles_nothing(self):
        response = self.client.get(reverse('finance:settle', args=[self.txn.pk]))
        self.assertEqual(response.status_code, 405)


class QueueSuggestionEndpointTests(FinanceViewTestCase):
    """ The JSON the queue page fetches to draw its chips. """

    def setUp(self):
        super(QueueSuggestionEndpointTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')

    def test_it_reports_the_direction(self):
        txn = self.make_txn(op='OT-J1', amount='-40.00')
        payload = self.client.get(reverse('finance:suggestions', args=[txn.pk])).json()
        self.assertEqual(payload['kind'], 'expense')

    def test_a_revenue_line_carries_refund_targets(self):
        """ Only revenue can be a credit note, so only revenue is offered them. """
        expense = self.make_txn(op='OT-J2', amount='-40.00')
        entry = ParsedTransaction.objects.create(
            parent_transaction=expense, amount=Decimal('-40.00'),
            effective_date=expense.accounting_date, description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        credit = self.make_txn(op='OT-J3', amount='40.00',
                               date=datetime.date(2025, 9, 20))
        payload = self.client.get(reverse('finance:suggestions', args=[credit.pk])).json()
        self.assertIn('refund_targets', payload)
        self.assertEqual([t['value'] for t in payload['refund_targets']], [str(entry.pk)])

    def test_an_expense_line_carries_none(self):
        txn = self.make_txn(op='OT-J4', amount='-40.00')
        payload = self.client.get(reverse('finance:suggestions', args=[txn.pk])).json()
        self.assertNotIn('refund_targets', payload)

    def test_ids_are_strings_so_the_browser_can_use_them_directly(self):
        """ They go straight into a <select>, whose values are strings. """
        SuggestionRule.objects.create(
            match_field='spend_category', match_mode='exact', pattern='Supplies',
            spend_category=SpendCategory.objects.get(slug='consumables'), priority=1)
        txn = self.make_txn(op='OT-J5', amount='-40.00')
        payload = self.client.get(reverse('finance:suggestions', args=[txn.pk])).json()
        self.assertIsInstance(payload['spend_category']['value'], str)

    def test_it_needs_the_view_permission(self):
        txn = self.make_txn(op='OT-J6', amount='-40.00')
        stranger = get_user_model().objects.create_user(
            username='stranger', email='stranger@wpi.edu', password='x')
        self.client.force_login(stranger)
        response = self.client.get(reverse('finance:suggestions', args=[txn.pk]))
        self.assertEqual(response.status_code, 403)

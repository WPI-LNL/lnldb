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
from django.test import TestCase
from django.urls import reverse

from finance.models import (FRLineItem, FundingRequest, ParsedTransaction, SpendCategory,
                            SuggestionRule, TransactionStatus, WorkdayTransaction)
from finance.suggestions import encumbrance_match_label, suggest_encumbrance_matches
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


class EncumbranceMatchingTests(FinanceViewTestCase):
    """
    Closing an encumbrance against the bank line that turned out to be it.

    The half of the encumbrance story that used to be missing. Three places in
    the UI said an encumbrance "stays Pending until it is matched to an
    imported transaction" and nothing could do the matching, so the only way
    through was to reconcile the imported line the ordinary way -- which writes
    a *second* entry and charges the funding request both the estimate and the
    actual. :meth:`test_matching_charges_the_award_once` is the test that
    exists because of that.
    """

    def setUp(self):
        super(EncumbranceMatchingTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.request = FundingRequest.objects.create(name='Fall Load-ins', fiscal_year=2026)
        self.line = FRLineItem.objects.create(
            funding_request=self.request, name='Consumables',
            amount_awarded=Decimal('500.00'))

    def encumber(self, amount='-200.00', description='Gaff tape', date=None, **extra):
        """ A pending purchase reserved against the funding request line. """
        fields = {
            'parent_transaction': None,
            'amount': Decimal(amount),
            'status': TransactionStatus.PENDING,
            'effective_date': date or datetime.date(2025, 8, 20),
            'description': description,
            'audit_explanation': 'Stock for the fall load-ins',
            'fund_source': fund('sga_fr'),
            'lnl_spend_category': category('consumables'),
            'fr_line_target': self.line,
        }
        fields.update(extra)
        return ParsedTransaction.objects.create(**fields)

    def match(self, txn, entry=None, **extra):
        data = {'encumbrance': '' if entry is None else str(entry.pk)}
        data.update(extra)
        return self.client.post(reverse('finance:match-encumbrance', args=[txn.pk]),
                                data, follow=True)

    def messages(self, response):
        return [str(m) for m in response.context['messages']]

    # -- the point of the whole feature ------------------------------------
    def test_matching_charges_the_award_once(self):
        """
        The bug this exists to stop: an encumbrance and a reconciliation for
        one purchase, both burning down the same funding request line.
        """
        txn = self.make_txn(op='OT-ENC1', amount='-203.55')
        entry = self.encumber('-200.00')
        self.assertEqual(self.line.spent, Decimal('200.00'))

        self.match(txn, entry)

        self.assertEqual(self.line.spent, Decimal('203.55'))
        self.assertEqual(ParsedTransaction.objects.count(), 1)

    def test_the_amount_becomes_the_actual(self):
        """ An encumbrance is an estimate; the bank line is what happened. """
        txn = self.make_txn(op='OT-ENC2', amount='-203.55')
        entry = self.encumber('-200.00')
        self.match(txn, entry)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal('-203.55'))
        self.assertEqual(entry.parent_transaction, txn)

    def test_the_date_moves_to_the_accounting_date(self):
        """
        Otherwise a purchase reserved in one fiscal year and charged in the
        next sits in both: the entry in FY25, its bank line in FY26.
        """
        txn = self.make_txn(op='OT-ENC3', amount='-200.00',
                            date=datetime.date(2025, 7, 3))
        entry = self.encumber('-200.00', date=datetime.date(2025, 6, 20))
        self.match(txn, entry)
        entry.refresh_from_db()
        self.assertEqual(entry.effective_date, datetime.date(2025, 7, 3))

    def test_routing_is_left_alone(self):
        """ Somebody already decided what the money was for. """
        txn = self.make_txn(op='OT-ENC4', amount='-200.00')
        entry = self.encumber('-200.00')
        self.match(txn, entry)
        entry.refresh_from_db()
        self.assertEqual(entry.fr_line_target, self.line)
        self.assertEqual(entry.lnl_spend_category, category('consumables'))
        self.assertEqual(entry.description, 'Gaff tape')

    def test_a_matched_line_settles_and_leaves_the_queue(self):
        txn = self.make_txn(op='OT-ENC5', amount='-200.00')
        entry = self.encumber('-200.00')
        self.match(txn, entry)
        entry.refresh_from_db()
        self.assertEqual(entry.status, TransactionStatus.SETTLED)
        self.assertFalse(WorkdayTransaction.objects.unreconciled().filter(pk=txn.pk).exists())

    def test_settling_needs_the_settle_permission(self):
        """ Without it the match still happens; it just stays Pending. """
        self.user.user_permissions.remove(Permission.objects.get(codename='settle_subledger'))
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_login(self.user)

        txn = self.make_txn(op='OT-ENC6', amount='-200.00')
        entry = self.encumber('-200.00')
        self.match(txn, entry)
        entry.refresh_from_db()
        self.assertEqual(entry.parent_transaction, txn)
        self.assertEqual(entry.status, TransactionStatus.PENDING)

    # -- the estimate was not the actual -----------------------------------
    def test_an_over_estimate_keeps_the_difference_reserved(self):
        """
        A $500 order part-filled by a $203.55 invoice still has $296.45
        committed. Releasing it silently would free money nobody has released.
        """
        txn = self.make_txn(op='OT-ENC7', amount='-203.55')
        entry = self.encumber('-500.00', description='Whole gear order')
        self.match(txn, entry)

        # The reservation is the row that survives -- same pk, written down by
        # what the line took. See test_the_reservation_keeps_its_identity.
        entry.refresh_from_db()
        self.assertIsNone(entry.parent_transaction)
        self.assertEqual(entry.amount, Decimal('-296.45'))
        self.assertEqual(entry.status, TransactionStatus.PENDING)

        drawn = ParsedTransaction.objects.get(parent_transaction=txn)
        self.assertEqual(drawn.amount, Decimal('-203.55'))
        self.assertEqual(drawn.fr_line_target, self.line)
        self.assertEqual(drawn.description, 'Whole gear order')
        # $203.55 spent plus $296.45 still committed: the award has not moved.
        self.assertEqual(self.line.spent, Decimal('500.00'))

    def test_an_under_estimate_simply_grows(self):
        """ Nothing is left over, so no remainder row is written. """
        txn = self.make_txn(op='OT-ENC8', amount='-260.00')
        entry = self.encumber('-200.00')
        self.match(txn, entry)
        self.assertEqual(ParsedTransaction.objects.count(), 1)
        self.assertEqual(self.line.spent, Decimal('260.00'))

    def test_the_message_names_both_figures(self):
        txn = self.make_txn(op='OT-ENC9', amount='-203.55')
        response = self.match(txn, self.encumber('-500.00'))
        message = self.messages(response)[0]
        self.assertIn('$500.00', message)
        self.assertIn('$203.55', message)
        self.assertIn('$296.45 stays reserved', message)

    # -- refusals ----------------------------------------------------------
    def test_choosing_nothing_says_so(self):
        txn = self.make_txn(op='OT-ENC10', amount='-200.00')
        self.encumber('-200.00')
        response = self.match(txn, None)
        self.assertIn('Pick an encumbrance', self.messages(response)[0])
        self.assertTrue(WorkdayTransaction.objects.unreconciled().filter(pk=txn.pk).exists())

    def test_an_already_matched_encumbrance_is_refused(self):
        """ Two people working the queue at once; the row went stale on screen. """
        txn = self.make_txn(op='OT-ENC11', amount='-200.00')
        entry = self.encumber('-200.00')
        self.match(txn, entry)

        other = self.make_txn(op='OT-ENC12', amount='-200.00')
        response = self.match(other, entry)
        self.assertIn('no longer pending', self.messages(response)[0])

    def test_a_full_line_has_nothing_left_to_settle(self):
        txn = self.make_txn(op='OT-ENC13', amount='-200.00')
        self.match(txn, self.encumber('-200.00'))
        response = self.match(txn, self.encumber('-200.00', description='Another'))
        self.assertIn('already fully allocated', self.messages(response)[0])

    def test_revenue_cannot_settle_an_encumbrance(self):
        """ You cannot reserve money coming in. """
        txn = self.make_txn(op='OT-ENC14', amount='500.00')
        response = self.match(txn, self.encumber('-200.00'))
        self.assertIn('money coming in', self.messages(response)[0])

    def test_editing_is_required(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='edit_subledger'))
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        txn = self.make_txn(op='OT-ENC15', amount='-200.00')
        response = self.client.post(
            reverse('finance:match-encumbrance', args=[txn.pk]),
            {'encumbrance': str(self.encumber('-200.00').pk)})
        self.assertEqual(response.status_code, 403)

    def test_get_is_not_allowed(self):
        txn = self.make_txn(op='OT-ENC16', amount='-200.00')
        response = self.client.get(reverse('finance:match-encumbrance', args=[txn.pk]))
        self.assertEqual(response.status_code, 405)

    # -- the XHR path the queue page actually uses -------------------------
    def xhr(self, txn, entry=None):
        return self.client.post(
            reverse('finance:match-encumbrance', args=[txn.pk]),
            {'encumbrance': '' if entry is None else str(entry.pk)},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_xhr_reports_the_row_as_done(self):
        txn = self.make_txn(op='OT-ENC20', amount='-200.00')
        payload = self.xhr(txn, self.encumber('-200.00')).json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['done'])
        self.assertTrue(payload['settled'])

    def test_xhr_does_not_offer_undo(self):
        """
        The queue's Undo deletes a row's allocations. On a matched encumbrance
        that would destroy the description, the reason and the reservation --
        none of which came from the bank line.
        """
        txn = self.make_txn(op='OT-ENC21', amount='-200.00')
        self.assertIs(self.xhr(txn, self.encumber('-200.00')).json()['undoable'], False)

    def test_xhr_refusals_carry_their_own_message(self):
        txn = self.make_txn(op='OT-ENC22', amount='500.00')
        response = self.xhr(txn, self.encumber('-200.00'))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])
        self.assertIn('money coming in', response.json()['message'])

    # -- what the queue offers ---------------------------------------------
    # ``?fy=`` because the filter bar otherwise defaults to the fiscal year the
    # machine is in today, which would hide a 2025-dated fixture and pass this
    # test for the wrong reason. Same convention as the queue tests in
    # ``test_views``.
    def test_the_queue_offers_the_candidates(self):
        self.make_txn(op='OT-ENC17', amount='-203.55')
        self.encumber('-200.00', description='Gaff tape order')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, 'OT-ENC17')
        self.assertContains(response, 'Already encumbered?')
        self.assertContains(response, 'Gaff tape order')
        self.assertContains(response, 'Maybe encumbered')

    def test_the_queue_stays_quiet_when_nothing_is_encumbered(self):
        self.make_txn(op='OT-ENC18', amount='-203.55')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, 'OT-ENC18')
        self.assertNotContains(response, 'Already encumbered?')

    def test_a_wildly_different_reservation_does_not_warn_on_the_row(self):
        """
        Still offered in the picker -- a badly estimated match is a match, and
        only a person can tell -- but a $900 reservation against a $12 charge
        must not put a warning on the row, or the warning stops being read.
        """
        self.make_txn(op='OT-ENC24', amount='-12.00')
        self.encumber('-900.00', description='Console flight case')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, 'Console flight case')
        self.assertNotContains(response, 'Maybe encumbered')

    def test_the_reconcile_form_stays_identifiable(self):
        """
        ``queue.js`` builds the Undo URL from the reconcile form's action, and
        used to find it with ``.find('form')`` -- the first form in the row.
        The encumbrance picker now sits above it, so the class is what keeps
        Undo pointed at the right endpoint.
        """
        self.make_txn(op='OT-ENC23', amount='-203.55')
        self.encumber('-200.00')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, 'fin-reconcile-form')

    def test_the_suggestion_endpoint_carries_them_too(self):
        txn = self.make_txn(op='OT-ENC19', amount='-203.55')
        entry = self.encumber('-200.00', description='Gaff tape order')
        response = self.client.get(reverse('finance:suggestions', args=[txn.pk]))
        payload = response.json()
        self.assertEqual([c['value'] for c in payload['encumbrances']], [str(entry.pk)])
        self.assertIn('Gaff tape order', payload['encumbrances'][0]['label'])


class EncumbranceDrawdownTests(FinanceViewTestCase):
    """
    One reservation paying for many bank lines.

    The ordinary shape of a big purchase: somebody encumbers what the whole job
    will cost, and Workday delivers it as ten invoice lines weeks apart. The
    reservation is the row that persists -- it keeps its primary key, its author
    and its history across every line it pays for and reads down towards zero,
    so it is still recognisably the same thing in the picker on the tenth match
    as it was on the first.
    """

    def setUp(self):
        super(EncumbranceDrawdownTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.author = get_user_model().objects.create_user(
            username='crew', email='crew@wpi.edu', password='x')
        self.request = FundingRequest.objects.create(name='PCDI Build', fiscal_year=2026)
        self.line = FRLineItem.objects.create(
            funding_request=self.request, name='Gear', amount_awarded=Decimal('2000.00'))
        self.encumbrance = ParsedTransaction.objects.create(
            parent_transaction=None, amount=Decimal('-1000.00'),
            status=TransactionStatus.PENDING, effective_date=datetime.date(2025, 8, 1),
            description='PCDI kit build', audit_explanation='Invoiced in pieces',
            fund_source=fund('sga_fr'), lnl_spend_category=category('consumables'),
            fr_line_target=self.line, created_by=self.author)

    def bank_line(self, op, amount, day=15):
        return self.make_txn(op=op, amount=amount, date=datetime.date(2025, 9, day))

    def match(self, txn, entry):
        return self.client.post(reverse('finance:match-encumbrance', args=[txn.pk]),
                                {'encumbrance': str(entry.pk)}, follow=True)

    def draw(self, lines, entry=None, **extra):
        data = {'selected': ",".join(str(t.pk) for t in lines),
                'encumbrance': str((entry or self.encumbrance).pk)}
        data.update(extra)
        return self.client.post(reverse('finance:bulk-match-encumbrance'), data, follow=True)

    def messages(self, response):
        return [str(m) for m in response.context['messages']]

    # -- one at a time -----------------------------------------------------
    def test_a_smaller_line_draws_down_rather_than_closing(self):
        txn = self.bank_line('SINV-1', '-80.00')
        self.match(txn, self.encumbrance)

        self.encumbrance.refresh_from_db()
        self.assertIsNone(self.encumbrance.parent_transaction)
        self.assertEqual(self.encumbrance.amount, Decimal('-920.00'))
        self.assertEqual(txn.slices.get().amount, Decimal('-80.00'))

    def test_the_reservation_keeps_its_identity(self):
        """
        Same row, not a fresh remainder each time. Its author and its history
        are the record of who committed the money and why, and a new pk on
        every draw would leave that behind on a row nobody looks at again.
        """
        pk, created = self.encumbrance.pk, self.encumbrance.created_on
        for n, amount in enumerate(['-80.00', '-120.00', '-95.50'], start=1):
            self.match(self.bank_line('SINV-%s' % n, amount), self.encumbrance)
            self.encumbrance.refresh_from_db()
            self.assertEqual(self.encumbrance.pk, pk)
            self.assertEqual(self.encumbrance.created_by, self.author)
            self.assertEqual(self.encumbrance.created_on, created)
        self.assertEqual(self.encumbrance.amount, Decimal('-704.50'))

    def test_the_drawn_slice_carries_the_reservations_routing(self):
        txn = self.bank_line('SINV-1', '-80.00')
        self.match(txn, self.encumbrance)
        drawn = txn.slices.get()
        self.assertEqual(drawn.fr_line_target, self.line)
        self.assertEqual(drawn.lnl_spend_category, category('consumables'))
        self.assertEqual(drawn.description, 'PCDI kit build')

    def test_the_allocator_authors_the_slice_not_the_reserver(self):
        """ Two different facts, and the ledger has room for both. """
        txn = self.bank_line('SINV-1', '-80.00')
        self.match(txn, self.encumbrance)
        self.assertEqual(txn.slices.get().created_by, self.user)
        self.encumbrance.refresh_from_db()
        self.assertEqual(self.encumbrance.created_by, self.author)

    def test_the_last_line_takes_the_reservation_row_itself(self):
        """ Nothing left over, so it becomes the entry rather than spawning one. """
        first = self.bank_line('SINV-1', '-400.00')
        last = self.bank_line('SINV-2', '-600.00')
        self.match(first, self.encumbrance)
        self.match(last, self.encumbrance)

        self.encumbrance.refresh_from_db()
        self.assertEqual(self.encumbrance.parent_transaction, last)
        self.assertEqual(self.encumbrance.amount, Decimal('-600.00'))
        self.assertEqual(self.encumbrance.status, TransactionStatus.SETTLED)
        self.assertFalse(
            ParsedTransaction.objects.filter(parent_transaction__isnull=True).exists())

    def test_a_line_much_larger_than_the_reservation_is_only_partly_covered(self):
        """
        A $1,000 reservation is not evidence about a $5,000 charge. Swallowing
        the difference would charge the budget line $4,000 nobody reserved.
        """
        txn = self.bank_line('SINV-BIG', '-5000.00')
        self.match(txn, self.encumbrance)

        self.assertEqual(txn.slices.get().amount, Decimal('-1000.00'))
        txn.refresh_from_db()
        self.assertEqual(txn.unallocated_amount, Decimal('-4000.00'))
        self.assertTrue(WorkdayTransaction.objects.unreconciled().filter(pk=txn.pk).exists())

    def test_the_message_says_what_is_left_on_the_line(self):
        response = self.match(self.bank_line('SINV-BIG', '-5000.00'), self.encumbrance)
        self.assertIn('$4000.00 of this line is still unallocated',
                      self.messages(response)[0])

    def test_a_slightly_larger_line_is_still_covered_whole(self):
        """ $1,000.00 reserved against $1,003.55 charged is an estimate, not a gap. """
        txn = self.bank_line('SINV-1', '-1003.55')
        self.match(txn, self.encumbrance)
        self.assertEqual(txn.slices.get().amount, Decimal('-1003.55'))
        txn.refresh_from_db()
        self.assertFalse(txn.unallocated_amount)

    # -- the whole selection at once ---------------------------------------
    def test_one_reservation_covers_a_whole_selection(self):
        lines = [self.bank_line('SINV-%s' % n, amount, day=n)
                 for n, amount in enumerate(['-80.00', '-120.00', '-95.50', '-140.00'], start=1)]
        self.draw(lines)

        for txn in lines:
            txn.refresh_from_db()
            self.assertFalse(txn.unallocated_amount, txn.reference)
            self.assertEqual(txn.slices.get().description, 'PCDI kit build')
        self.encumbrance.refresh_from_db()
        self.assertEqual(self.encumbrance.amount, Decimal('-564.50'))
        # Charged once: the four lines, not the four lines plus the reservation.
        self.assertEqual(self.line.spent, Decimal('1000.00'))

    def test_a_bulk_draw_settles_what_it_finishes(self):
        lines = [self.bank_line('SINV-%s' % n, '-100.00', day=n) for n in (1, 2, 3)]
        self.draw(lines)
        for txn in lines:
            self.assertEqual(txn.slices.get().status, TransactionStatus.SETTLED)

    def test_a_bulk_draw_stops_when_the_reservation_runs_out(self):
        """ It covers the purchase it was written for, not the rest of the export. """
        lines = [self.bank_line('SINV-%s' % n, '-400.00', day=n) for n in (1, 2, 3, 4)]
        self.draw(lines)

        covered = [t for t in lines if not WorkdayTransaction.objects
                   .unreconciled().filter(pk=t.pk).exists()]
        self.assertEqual(len(covered), 2)
        self.assertEqual(self.line.spent, Decimal('1000.00'))

    def test_the_lines_it_could_not_reach_are_named(self):
        """
        $1,000 over four $400 lines reaches three of them -- the third for the
        last $200 -- and never gets to the fourth. Being told which is the
        difference between finishing the batch and finding it next month.
        """
        lines = [self.bank_line('SINV-%s' % n, '-400.00', day=n) for n in (1, 2, 3, 4)]
        response = self.draw(lines)
        joined = " ".join(self.messages(response))
        self.assertIn('ran out before', joined)
        self.assertIn('SINV-4', joined)
        self.assertFalse(lines[3].slices.exists())

    def test_a_partly_covered_line_is_called_out(self):
        lines = [self.bank_line('SINV-1', '-900.00', day=1),
                 self.bank_line('SINV-2', '-300.00', day=2)]
        response = self.draw(lines)
        joined = " ".join(self.messages(response))
        self.assertIn('did not cover all of', joined)
        self.assertIn('SINV-2', joined)

    def test_oldest_line_first_whatever_order_was_ticked(self):
        """ The drawdown has to be reproducible, not dependent on click order. """
        early = self.bank_line('SINV-EARLY', '-600.00', day=2)
        late = self.bank_line('SINV-LATE', '-600.00', day=20)
        self.draw([late, early])

        early.refresh_from_db()
        self.assertFalse(early.unallocated_amount)
        self.assertTrue(WorkdayTransaction.objects.unreconciled().filter(pk=late.pk).exists())

    def test_revenue_in_the_selection_is_skipped_and_said_so(self):
        expense = self.bank_line('SINV-1', '-100.00', day=1)
        revenue = self.bank_line('ISD-1', '400.00', day=2)
        response = self.draw([expense, revenue])
        self.assertIn('revenue line', " ".join(self.messages(response)))
        revenue.refresh_from_db()
        self.assertFalse(revenue.slices.exists())

    def test_choosing_no_encumbrance_says_so(self):
        response = self.client.post(
            reverse('finance:bulk-match-encumbrance'),
            {'selected': str(self.bank_line('SINV-1', '-100.00').pk), 'encumbrance': ''},
            follow=True)
        self.assertIn('Pick the encumbrance', " ".join(self.messages(response)))

    def test_selecting_nothing_says_so(self):
        response = self.client.post(
            reverse('finance:bulk-match-encumbrance'),
            {'selected': '', 'encumbrance': str(self.encumbrance.pk)}, follow=True)
        self.assertIn('Nothing was selected', " ".join(self.messages(response)))

    def test_a_bulk_draw_needs_the_edit_permission(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='edit_subledger'))
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('finance:bulk-match-encumbrance'),
            {'selected': str(self.bank_line('SINV-1', '-100.00').pk),
             'encumbrance': str(self.encumbrance.pk)})
        self.assertEqual(response.status_code, 403)

    def test_the_bar_offers_open_reservations(self):
        self.bank_line('SINV-1', '-100.00')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, 'Draw selected')
        self.assertContains(response, 'PCDI kit build')
        self.assertContains(response, 'still reserved')


class EncumbranceMatchRankingTests(TestCase):
    """
    Which encumbrances are offered, and in what order.

    A shortlist, never an answer: nothing here is auto-applied and nothing is
    pre-selected, because matching the wrong row files a purchase against the
    wrong budget line *and* marks a live commitment spent, and neither is
    visible once done.
    """

    def _txn(self, amount='-203.55', date=None, supplier='B&H Photo'):
        return WorkdayTransaction.objects.create(
            operational_transaction='OT-RANK', supplier=supplier,
            accounting_date=date or datetime.date(2025, 9, 15),
            net_amount=Decimal(amount), memo='Cables',
            worktags_json={'ledger_account': '71100:Supplies'})

    def _encumbrance(self, amount, description='Reserved', date=None, explanation=''):
        return ParsedTransaction.objects.create(
            parent_transaction=None, amount=Decimal(amount),
            status=TransactionStatus.PENDING,
            effective_date=date or datetime.date(2025, 9, 1),
            description=description, audit_explanation=explanation,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))

    def test_the_closest_amount_comes_first(self):
        txn = self._txn('-203.55')
        self._encumbrance('-900.00', 'Flight case')
        close = self._encumbrance('-200.00', 'Cable order')
        self._encumbrance('-260.00', 'Spools')
        self.assertEqual(suggest_encumbrance_matches(txn)[0], close)

    def test_naming_the_payee_breaks_a_tie(self):
        txn = self._txn('-200.00', supplier='B&H Photo')
        self._encumbrance('-200.00', 'Some cables')
        named = self._encumbrance('-200.00', 'Cables from B&H Photo')
        self.assertEqual(suggest_encumbrance_matches(txn)[0], named)

    def test_a_reservation_that_covers_the_line_beats_one_that_does_not(self):
        """
        The drawdown case, and the reason the score is not symmetric: a $1,000
        reservation against an $80 line is one encumbrance being delivered a
        line at a time, not a bad match. Ranking it by the raw difference would
        bury it under every small stray on the page.
        """
        txn = self._txn('-80.00')
        self._encumbrance('-40.00', 'Half of it')
        big = self._encumbrance('-1000.00', 'Whole PCDI build')
        self.assertEqual(suggest_encumbrance_matches(txn)[0], big)

    def test_the_tightest_sufficient_reservation_comes_first(self):
        """ Several would cover it; the one with least left over is offered. """
        txn = self._txn('-200.00')
        self._encumbrance('-5000.00', 'Everything')
        tight = self._encumbrance('-220.00', 'About right')
        self._encumbrance('-900.00', 'Plenty')
        self.assertEqual(suggest_encumbrance_matches(txn)[0], tight)

    def test_a_small_shortfall_is_not_held_against_a_match(self):
        """ $200.00 reserved against $203.55 charged is an estimate, not a gap. """
        txn = self._txn('-203.55')
        near = self._encumbrance('-200.00', 'The cable order')
        self._encumbrance('-260.00', 'Something roomier')
        self.assertEqual(suggest_encumbrance_matches(txn)[0], near)

    def test_a_reservation_far_too_small_ranks_last(self):
        txn = self._txn('-5000.00')
        self._encumbrance('-50.00', 'Nowhere near')
        covers = self._encumbrance('-5200.00', 'The real one')
        self.assertEqual(suggest_encumbrance_matches(txn)[0], covers)

    def test_a_settled_entry_is_never_offered(self):
        txn = self._txn('-200.00')
        entry = self._encumbrance('-200.00')
        ParsedTransaction.objects.filter(pk=entry.pk).update(
            status=TransactionStatus.SETTLED, parent_transaction=self._txn('-200.00'))
        self.assertEqual(suggest_encumbrance_matches(txn), [])

    def test_an_entry_already_on_a_bank_line_is_never_offered(self):
        """ It is a reconciled slice, not an open commitment. """
        txn = self._txn('-200.00')
        other = self._txn('-200.00')
        ParsedTransaction.objects.create(
            parent_transaction=other, amount=Decimal('-200.00'),
            status=TransactionStatus.PENDING, effective_date=other.accounting_date,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        self.assertEqual(suggest_encumbrance_matches(txn), [])

    def test_revenue_is_offered_nothing(self):
        self._encumbrance('-200.00')
        self.assertEqual(suggest_encumbrance_matches(self._txn('500.00')), [])

    def test_something_reserved_years_ago_is_not_offered(self):
        """ Wide, but not unbounded: an encumbrance that old is abandoned. """
        txn = self._txn('-200.00', date=datetime.date(2025, 9, 15))
        self._encumbrance('-200.00', date=datetime.date(2023, 1, 5))
        self.assertEqual(suggest_encumbrance_matches(txn), [])

    def test_something_reserved_long_after_the_charge_is_not_offered(self):
        txn = self._txn('-200.00', date=datetime.date(2025, 9, 15))
        self._encumbrance('-200.00', date=datetime.date(2026, 3, 1))
        self.assertEqual(suggest_encumbrance_matches(txn), [])

    def test_reserved_a_few_days_after_the_charge_is_still_offered(self):
        """ Logging the purchase the week after it went through is ordinary. """
        txn = self._txn('-200.00', date=datetime.date(2025, 9, 15))
        entry = self._encumbrance('-200.00', date=datetime.date(2025, 9, 19))
        self.assertEqual(suggest_encumbrance_matches(txn), [entry])

    def test_the_shortlist_is_capped(self):
        txn = self._txn('-200.00')
        for n in range(12):
            self._encumbrance('-%s.00' % (200 + n), 'Order %s' % n)
        self.assertEqual(len(suggest_encumbrance_matches(txn)), 8)

    def test_the_label_states_the_gap(self):
        txn = self._txn('-203.55')
        label = encumbrance_match_label(self._encumbrance('-200.00', 'Cable order'), txn)
        self.assertIn('Cable order', label)
        self.assertIn('$200.00 reserved', label)
        self.assertIn('3.55 over', label)

    def test_an_exact_match_says_so(self):
        txn = self._txn('-200.00')
        label = encumbrance_match_label(self._encumbrance('-200.00'), txn)
        self.assertIn('exact match', label)

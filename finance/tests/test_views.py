import datetime
import json
import logging
from decimal import Decimal

import reversion
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from reversion.models import Version

from data.tests.util import ViewTestCase
from events.tests.generators import Event2019Factory, OrgFactory
from finance.forms import BulkReconcileForm, ReconcileForm
from finance.models import (FRLineItem, FundingRequest, ParsedTransaction, ProjectTag,
                            TransactionStatus, WorkdayTransaction)
from finance.tests.util import category, fund

logging.disable(logging.WARNING)

CSV_HEADER = ("Accounting Date,Debit Amount,Credit Amount,Credit Minus Debit,"
              "Operational Transaction,Supplier,Employee,Journal,Journal Line Memo,Header Memo,"
              "Fund,Cost Center,Ledger Account,Spend Category,Revenue Category,Activity,"
              "Student Organization,Program")
CSV_ROW = ('09/15/2025,1200.00,0.00,"(1,200.00)",OT-9001,B&H Photo,,JRN-1,Lighting order,,'
           '110-FD,CC-1,310-AG,Supplies,,,,Ops')


class FinanceViewTestCase(ViewTestCase):
    """ Base with helpers for granting the module's permissions. """

    def grant(self, *codenames):
        for codename in codenames:
            self.user.user_permissions.add(Permission.objects.get(codename=codename))
        # Permission caching is per-instance; drop it so the next check re-reads.
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_login(self.user)

    def make_txn(self, op='OT-1', amount='-1200.00', org=None, date=None, memo='Test line'):
        """ ``org`` is the Student Organization worktag, which drives the partition. """
        worktags = {'ledger_account': '71100:Supplies', 'spend_category': 'Supplies'}
        if org:
            worktags['student_organization'] = org
        return WorkdayTransaction.objects.create(
            operational_transaction=op,
            accounting_date=date or datetime.date(2025, 9, 15),
            net_amount=Decimal(amount),
            supplier='B&H Photo',
            memo=memo,
            worktags_json=worktags)


class TemplateHygieneTests(TestCase):
    """
    Django's ``{# ... #}`` comment is single-line only. Spread one over two
    lines and it stops being a comment — the text renders verbatim on the page.
    Multi-line notes must use ``{% comment %}``.
    """

    def test_no_multiline_hash_comments(self):
        import glob
        import io
        import os

        # Resolved from the configured template roots rather than the working
        # directory, so the test holds wherever it is run from.
        template_dirs = [d for engine in settings.TEMPLATES for d in engine.get('DIRS', [])]
        candidates = [os.path.join(str(d), 'finance') for d in template_dirs]
        searched = [d for d in candidates if os.path.isdir(d)]
        self.assertTrue(searched, "Could not locate the finance template directory")

        offenders = []
        for directory in searched:
            for path in glob.glob(os.path.join(directory, '*.html')):
                with io.open(path, encoding='utf-8') as fh:
                    for number, line in enumerate(fh, 1):
                        if '{#' in line and '#}' not in line:
                            offenders.append('%s:%s' % (os.path.basename(path), number))
        self.assertEqual(offenders, [],
                         "Multi-line {# #} comments render as visible text: %s" % offenders)


class PermissionTests(FinanceViewTestCase):
    """ Role-based occlusion: read-only for members, write for the Treasurer. """

    def test_all_pages_require_view_permission(self):
        for name, args in (('finance:dashboard', []), ('finance:ledger', []),
                           ('finance:queue', []), ('finance:projects', []),
                           ('finance:fr-list', [])):
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 403, name)

    def test_view_permission_grants_read_access(self):
        self.grant('view_subledger', 'view_fundingrequest')
        for name in ('finance:dashboard', 'finance:ledger', 'finance:queue',
                     'finance:projects', 'finance:fr-list'):
            self.assertOk(self.client.get(reverse(name)))

    def test_read_only_user_cannot_write(self):
        self.grant('view_subledger')
        txn = self.make_txn()
        response = self.client.post(reverse('finance:reconcile', args=[txn.pk]), {})
        self.assertEqual(response.status_code, 403)

    def test_read_only_user_cannot_import(self):
        self.grant('view_subledger')
        response = self.client.post(reverse('finance:upload'), {})
        self.assertEqual(response.status_code, 403)

    def test_read_only_banner_shown_to_members(self):
        self.grant('view_subledger')
        response = self.client.get(reverse('finance:dashboard'))
        self.assertContains(response, "Read-only view")

    def test_banner_hidden_from_treasurer(self):
        self.grant('view_subledger', 'edit_subledger')
        response = self.client.get(reverse('finance:dashboard'))
        self.assertNotContains(response, "Read-only view")


class DashboardTests(FinanceViewTestCase):
    def setUp(self):
        super(DashboardTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'view_fundingrequest')

    def test_renders_empty(self):
        self.assertOk(self.client.get(reverse('finance:dashboard')))

    def test_action_banner_appears_when_unreconciled(self):
        self.make_txn(op='OT-A')
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        self.assertContains(response, "awaiting reconciliation")

    def test_action_banner_absent_when_clear(self):
        txn = self.make_txn(op='OT-B')
        ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'),
            effective_date=txn.accounting_date, status=TransactionStatus.SETTLED)
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        self.assertNotContains(response, "awaiting reconciliation")

    def test_pie_chart_renders_with_data(self):
        txn = self.make_txn(op='OT-C')
        ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), effective_date=txn.accounting_date)
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        self.assertContains(response, "fin-chart-categories")
        self.assertContains(response, "Consumables")

    def test_all_dashboard_charts_render(self):
        org = OrgFactory.create(name='Student Group', workday_fund=810)
        event = Event2019Factory.create(billing_org=org)
        revenue = self.make_txn(op='OT-CH1', amount='500.00')
        ParsedTransaction.objects.create(
            parent_transaction=revenue, amount=Decimal('500.00'), linked_event=event,
            effective_date=revenue.accounting_date)
        expense = self.make_txn(op='OT-CH2')
        tag = ProjectTag.objects.create(name='NEL26', code='NEL26')
        ParsedTransaction.objects.create(
            parent_transaction=expense, amount=expense.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'), project_tag=tag,
            effective_date=expense.accounting_date)

        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        for canvas in ('fin-cashflow', 'fin-chart-categories',
                       'fin-chart-clienttypes', 'fin-chart-services'):
            self.assertContains(response, canvas)
        self.assertContains(response, 'Revenue by Client')
        self.assertContains(response, 'Project Spending')
        self.assertContains(response, 'Student Group')      # client bar
        self.assertContains(response, 'Student Organization')  # client-type slice
        self.assertContains(response, 'NEL26')              # project stack

    def test_chart_payload_is_json_not_stringified_decimals(self):
        """
        json_script serialises Decimal as a string, which Chart.js plots as
        zero. The view must hand over floats.
        """
        import json
        txn = self.make_txn(op='OT-CH3')
        ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), effective_date=txn.accounting_date)
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        payload = response.context['chart_data']
        self.assertTrue(all(isinstance(v, float) for v in payload['categories']['data']))
        self.assertTrue(all(isinstance(v, float) for v in payload['cash_flow']['revenue']))
        json.dumps(payload)   # must be natively serialisable

    def test_burndown_renders(self):
        fr = FundingRequest.objects.create(name='NEL26 Grant', fiscal_year=2026)
        FRLineItem.objects.create(funding_request=fr, name='Fixtures',
                                  amount_awarded=Decimal('1000.00'))
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        self.assertContains(response, "NEL26 Grant")
        self.assertContains(response, "fin-burndown")

    def test_burndown_line_items_start_collapsed(self):
        """ Only the request's combined burndown shows until it is expanded. """
        fr = FundingRequest.objects.create(name='NEL26 Grant', fiscal_year=2026)
        FRLineItem.objects.create(funding_request=fr, name='Fixtures',
                                  amount_awarded=Decimal('1000.00'))
        FRLineItem.objects.create(funding_request=fr, name='Cable',
                                  amount_awarded=Decimal('500.00'))
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        # The lines are present in the DOM but inside a collapsed container.
        self.assertContains(response, 'class="collapse fin-fr-lines"')
        self.assertContains(response, 'id="fr-lines-%s"' % fr.pk)
        self.assertContains(response, 'data-target="#fr-lines-%s"' % fr.pk)
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, '2 line items')

    def test_year_end_calculator_is_gone(self):
        """ Removed at the Treasurer's request; it will be handled differently. """
        response = self.client.get(reverse('finance:dashboard'))
        self.assertNotContains(response, "Year-End Calculator")
        self.assertNotContains(response, "Reserve Rollback")
        self.assertNotContains(response, "show token")


class FilterBarTests(FinanceViewTestCase):
    def setUp(self):
        super(FilterBarTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')

    def test_partition_filters_the_queue(self):
        """
        This filter matched nothing at all: it looked for '315-AG' in Ledger
        Account, and real exports carry the org code in Student Organization.
        """
        self.make_txn(op='OT-FP', org='315-AG Projection', memo='Projector lamp')
        self.make_txn(op='OT-FE', org='226-AG Lens & Light Club', memo='Gaff tape')

        response = self.client.get(reverse('finance:queue') + '?fy=2026&partition=projection')
        self.assertContains(response, 'Projector lamp')
        self.assertNotContains(response, 'Gaff tape')

        response = self.client.get(reverse('finance:queue') + '?fy=2026&partition=event')
        self.assertContains(response, 'Gaff tape')
        self.assertNotContains(response, 'Projector lamp')

    def test_an_unknown_org_code_counts_as_event_production(self):
        """ Otherwise it appears in neither view and goes quietly unreconciled. """
        self.make_txn(op='OT-FU', org='', memo='Mystery charge')
        response = self.client.get(reverse('finance:queue') + '?fy=2026&partition=event')
        self.assertContains(response, 'Mystery charge')

    def test_partition_filters_the_ledger(self):
        proj = self.make_txn(op='OT-P', org='315-AG')
        ParsedTransaction.objects.create(
            parent_transaction=proj, amount=proj.net_amount, fund_source=fund('sga_budget'),
            description='Projector lamp', effective_date=proj.accounting_date)

        event = self.make_txn(op='OT-E', org='226-AG Lens & Light Club')
        ParsedTransaction.objects.create(
            parent_transaction=event, amount=event.net_amount, fund_source=fund('sga_budget'),
            description='Gaff tape', effective_date=event.accounting_date)

        response = self.client.get(reverse('finance:ledger') + '?fy=2026&partition=projection')
        self.assertContains(response, "Projector lamp")
        self.assertNotContains(response, "Gaff tape")

        response = self.client.get(reverse('finance:ledger') + '?fy=2026&partition=event')
        self.assertContains(response, "Gaff tape")
        self.assertNotContains(response, "Projector lamp")

    def test_fiscal_year_filters_the_ledger(self):
        old = self.make_txn(op='OT-OLD', date=datetime.date(2024, 9, 1))
        ParsedTransaction.objects.create(
            parent_transaction=old, amount=old.net_amount, fund_source=fund('sga_budget'),
            description='Last year cable', effective_date=old.accounting_date)
        new = self.make_txn(op='OT-NEW', date=datetime.date(2025, 9, 1))
        ParsedTransaction.objects.create(
            parent_transaction=new, amount=new.net_amount, fund_source=fund('sga_budget'),
            description='This year cable', effective_date=new.accounting_date)

        response = self.client.get(reverse('finance:ledger') + '?fy=2026')
        self.assertContains(response, "This year cable")
        self.assertNotContains(response, "Last year cable")

    def test_partition_persists_in_session(self):
        self.client.get(reverse('finance:ledger') + '?partition=projection')
        response = self.client.get(reverse('finance:dashboard'))
        self.assertEqual(response.context['filter_state'].partition, 'projection')

    # -- regression: the "All" resets used to be unselectable ---------------
    def test_all_partition_clears_a_sticky_partition(self):
        self.client.get(reverse('finance:dashboard') + '?partition=projection')
        response = self.client.get(reverse('finance:dashboard') + '?partition=all')
        self.assertEqual(response.context['filter_state'].partition, 'all')
        self.assertIsNone(response.context['filter_state'].projection_flag)

    def test_all_years_clears_a_sticky_fiscal_year(self):
        self.client.get(reverse('finance:dashboard') + '?fy=2026')
        response = self.client.get(reverse('finance:dashboard') + '?fy=all')
        self.assertIsNone(response.context['filter_state'].fiscal_year)

    def test_all_selections_survive_navigation(self):
        self.client.get(reverse('finance:dashboard') + '?fy=all&partition=all')
        response = self.client.get(reverse('finance:ledger'))
        self.assertIsNone(response.context['filter_state'].fiscal_year)
        self.assertEqual(response.context['filter_state'].partition, 'all')

    def test_filter_links_always_emit_both_parameters(self):
        """
        An omitted parameter means "fall back to the session", so a reset link
        must state its value explicitly or it becomes a no-op.
        """
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026&partition=projection')
        state = response.context['filter_state']
        self.assertEqual(state.url_with(partition='all'), '?fy=2026&partition=all')
        self.assertEqual(state.url_with(fiscal_year=''), '?fy=all&partition=projection')
        self.assertEqual(state.querystring, 'fy=2026&partition=projection')

    def test_all_years_link_is_rendered_with_the_sentinel(self):
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        self.assertContains(response, 'fy=all')

    def test_all_years_shows_every_fiscal_year(self):
        old = self.make_txn(op='OT-Y1', date=datetime.date(2024, 9, 1))
        ParsedTransaction.objects.create(
            parent_transaction=old, amount=old.net_amount, fund_source=fund('sga_budget'),
            description='FY25 cable', effective_date=old.accounting_date)
        new = self.make_txn(op='OT-Y2', date=datetime.date(2025, 9, 1))
        ParsedTransaction.objects.create(
            parent_transaction=new, amount=new.net_amount, fund_source=fund('sga_budget'),
            description='FY26 cable', effective_date=new.accounting_date)

        self.client.get(reverse('finance:ledger') + '?fy=2026')       # make it sticky
        response = self.client.get(reverse('finance:ledger') + '?fy=all')
        self.assertContains(response, 'FY25 cable')
        self.assertContains(response, 'FY26 cable')

    def test_all_partition_shows_both_sides(self):
        proj = self.make_txn(op='OT-PA', org='315-AG')
        ParsedTransaction.objects.create(
            parent_transaction=proj, amount=proj.net_amount, fund_source=fund('sga_budget'),
            description='Projector lamp', effective_date=proj.accounting_date)
        event = self.make_txn(op='OT-EA', org='226-AG Lens & Light Club')
        ParsedTransaction.objects.create(
            parent_transaction=event, amount=event.net_amount, fund_source=fund('sga_budget'),
            description='Gaff tape', effective_date=event.accounting_date)

        self.client.get(reverse('finance:ledger') + '?fy=2026&partition=projection')
        response = self.client.get(reverse('finance:ledger') + '?fy=2026&partition=all')
        self.assertContains(response, 'Projector lamp')
        self.assertContains(response, 'Gaff tape')


class LedgerTests(FinanceViewTestCase):
    def setUp(self):
        super(LedgerTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')
        txn = self.make_txn(op='OT-L1')
        self.entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), description='Gaff tape',
            effective_date=txn.accounting_date)

    def test_renders(self):
        response = self.client.get(reverse('finance:ledger') + '?fy=2026')
        self.assertContains(response, "Gaff tape")

    def test_search(self):
        response = self.client.get(reverse('finance:ledger') + '?fy=2026&q=gaff')
        self.assertContains(response, "Gaff tape")
        response = self.client.get(reverse('finance:ledger') + '?fy=2026&q=nonexistent')
        self.assertNotContains(response, "Gaff tape")

    def test_sorting_does_not_error(self):
        for column in ('date', 'amount', 'status', 'spend_category', 'project'):
            self.assertOk(self.client.get(
                reverse('finance:ledger') + '?sort=%s&dir=asc' % column))

    def test_bulk_assign_project(self):
        tag = ProjectTag.objects.create(name='NEL26', code='NEL26')
        response = self.client.post(reverse('finance:bulk-action'), {
            'action': 'project_tag',
            'project_tag': tag.pk,
            'selected': str(self.entry.pk),
        })
        self.assertEqual(response.status_code, 302)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.project_tag, tag)

    def test_bulk_assign_spend_category(self):
        response = self.client.post(reverse('finance:bulk-action'), {
            'action': 'lnl_spend_category',
            'lnl_spend_category': category('repairs').pk,
            'selected': str(self.entry.pk),
        })
        self.assertEqual(response.status_code, 302)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.lnl_spend_category, category('repairs'))

    def test_bulk_settle_respects_balance_rule(self):
        """ A half-allocated bank line must not be settleable in bulk. """
        parent = self.make_txn(op='OT-L2', amount='-1000.00')
        partial = ParsedTransaction.objects.create(
            parent_transaction=parent, amount=Decimal('-400.00'), fund_source=fund('sga_budget'),
            effective_date=parent.accounting_date)
        self.client.post(reverse('finance:bulk-action'), {
            'action': 'status',
            'status': TransactionStatus.SETTLED,
            'selected': str(partial.pk),
        })
        partial.refresh_from_db()
        self.assertEqual(partial.status, TransactionStatus.PENDING)


class IngestionTests(FinanceViewTestCase):
    def setUp(self):
        super(IngestionTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'import_workdaytransaction',
                   'settle_subledger')

    def _upload(self, body=None, **extra):
        """ Choose a file. Nothing is written yet -- see :meth:`_confirm`. """
        payload = body or (CSV_HEADER + "\n" + CSV_ROW + "\n")
        upload = SimpleUploadedFile('journal.csv', payload.encode('utf-8'), content_type='text/csv')
        data = {'csv_file': upload}
        data.update(extra)
        return self.client.post(reverse('finance:upload'), data, follow=True)

    def _confirm(self, **extra):
        return self.client.post(reverse('finance:upload-confirm'), extra, follow=True)

    def _import(self, body=None):
        """
        Both halves, for the tests that are about something else.

        Confirms only when a confirmation was actually asked for: a file with
        no new lines in it goes straight through, and pressing Confirm on a
        page that was never shown is not what a Treasurer would do.
        """
        response = self._upload(body)
        if b'about to add' not in response.content:
            return response
        return self._confirm()

    def test_queue_renders(self):
        self.make_txn(op='OT-Q1')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, "OT-Q1")

    def test_choosing_a_file_writes_nothing_and_asks_first(self):
        """
        The count is the whole point: last month's export parses perfectly and
        reads correctly, and nothing but a number gives it away in time.
        """
        response = self._upload()
        self.assertContains(response, "about to add")
        self.assertContains(response, "1 unreconciled line")
        self.assertFalse(WorkdayTransaction.objects.exists())

    def test_confirming_creates_the_transactions(self):
        self._upload()
        response = self._confirm()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(WorkdayTransaction.objects.filter(operational_transaction='OT-9001').exists())

    def test_cancelling_imports_nothing(self):
        self._upload()
        response = self._confirm(cancel='1')
        self.assertContains(response, "Import cancelled")
        self.assertFalse(WorkdayTransaction.objects.exists())

    def test_confirming_twice_imports_once(self):
        """ The staged file is consumed, so a resubmitted confirmation is inert. """
        self._upload()
        self._confirm()
        response = self._confirm()
        self.assertEqual(WorkdayTransaction.objects.count(), 1)
        self.assertContains(response, "no longer waiting")

    def test_preview_only_skips_the_confirmation(self):
        """ Asking to look and not touch already answers "are you sure?". """
        response = self._upload(dry_run='on')
        self.assertContains(response, "Preview only")
        self.assertNotContains(response, "about to add")
        self.assertFalse(WorkdayTransaction.objects.exists())

    def test_a_file_with_nothing_new_skips_the_confirmation(self):
        self._import()
        response = self._upload()
        self.assertNotContains(response, "about to add")
        self.assertContains(response, "already been imported")

    def test_duplicate_upload_is_reported_not_duplicated(self):
        self._import()
        response = self._import()
        self.assertEqual(WorkdayTransaction.objects.filter(operational_transaction='OT-9001').count(), 1)
        self.assertContains(response, "already been imported")

    def test_bad_file_is_rejected_gracefully(self):
        response = self._upload("Name,Email\nfoo,bar\n")
        self.assertContains(response, "Workday journal export")
        self.assertEqual(WorkdayTransaction.objects.count(), 0)

    def test_expense_row_shows_expense_pickers_only(self):
        """ Poka-Yoke: a negative line must not offer the event linker. """
        self.make_txn(op='OT-Q2', amount='-500.00')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, "Spend Category")
        self.assertNotContains(response, "Link to Event")

    def test_revenue_row_shows_event_linker_only(self):
        self.make_txn(op='OT-Q3', amount='500.00')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, "Link to Event")
        self.assertNotContains(response, "Spend Category")

    def test_the_paying_account_is_shown_on_the_row(self):
        self.make_txn(op='OT-Q4', org='315-AG')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, "315-AG")
        # The tick box is offered, not disabled: a 315-AG line may be filed as
        # Event Production, it just has to be explained.
        self.assertNotContains(response, "PROJECTION LOCKED")

    def test_the_reason_box_is_offered_on_the_projection_account(self):
        self.make_txn(op='OT-Q4B', org='315-AG')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertContains(response, "fin-partition-reason")

    def test_the_reason_box_is_not_offered_on_the_main_account(self):
        self.make_txn(op='OT-Q4C', org='226-AG Lens & Light Club')
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        self.assertNotContains(response, "fin-partition-reason")

    def test_reconcile_creates_and_settles(self):
        txn = self.make_txn(op='OT-Q5', amount='-500.00')
        response = self.client.post(reverse('finance:reconcile', args=[txn.pk]), {
            'txn%s-fund_source' % txn.pk: fund('sga_budget').pk,
            'txn%s-lnl_spend_category' % txn.pk: category('consumables').pk,
        })
        self.assertEqual(response.status_code, 302)
        entry = txn.slices.get()
        self.assertEqual(entry.amount, Decimal('-500.00'))
        self.assertEqual(entry.status, TransactionStatus.SETTLED)

    def test_reconcile_of_a_projection_account_line_stays_on_projection(self):
        """ Unticking the box is now possible, so the box is what is checked. """
        txn = self.make_txn(op='OT-Q6', org='315-AG')
        self.client.post(reverse('finance:reconcile', args=[txn.pk]), {
            'txn%s-fund_source' % txn.pk: fund('sga_budget').pk,
            'txn%s-lnl_spend_category' % txn.pk: category('repairs').pk,
            'txn%s-is_projection' % txn.pk: 'on',
        })
        self.assertTrue(txn.slices.get().is_projection)

    def test_leaving_the_projection_account_needs_a_reason(self):
        txn = self.make_txn(op='OT-Q6B', org='315-AG')
        payload = {
            'txn%s-fund_source' % txn.pk: fund('sga_budget').pk,
            'txn%s-lnl_spend_category' % txn.pk: category('repairs').pk,
            # is_projection deliberately unticked
        }
        self.client.post(reverse('finance:reconcile', args=[txn.pk]), payload)
        self.assertFalse(txn.slices.exists(), "refused until it is explained")

        payload['txn%s-audit_explanation' % txn.pk] = 'Recharged to Event Production per SGA.'
        self.client.post(reverse('finance:reconcile', args=[txn.pk]), payload)
        entry = txn.slices.get()
        self.assertFalse(entry.is_projection)
        self.assertTrue(entry.crosses_partition)

    def test_the_main_account_crosses_without_ceremony(self):
        """ A Projection purchase bought out of 226-AG, reimbursed by SGA. """
        txn = self.make_txn(op='OT-Q6C', org='226-AG Lens & Light Club')
        self.client.post(reverse('finance:reconcile', args=[txn.pk]), {
            'txn%s-fund_source' % txn.pk: fund('sga_budget').pk,
            'txn%s-lnl_spend_category' % txn.pk: category('repairs').pk,
            'txn%s-is_projection' % txn.pk: 'on',
        })
        entry = txn.slices.get()
        self.assertTrue(entry.is_projection)
        self.assertTrue(entry.crosses_partition)

    # -- how the row is laid out -------------------------------------------
    #
    # The queue is worked twenty-five rows at a time, so what is on screen per
    # row is the whole usability question. These pin the answers down.

    def test_an_ordinary_row_is_two_boxes_and_a_button(self):
        """ Project, the event, the partition and the cross-year tick fold away. """
        self.make_txn(op='OT-UI1', amount='-40.00', org='226-AG Lens & Light Club')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        self.assertIn('fin-fields-more is-folded', html)

    def test_a_row_with_something_to_say_opens_itself(self):
        """
        A 315-AG line has a partition worth seeing and a reason box that may be
        demanded, so folding it away would hide the question.
        """
        self.make_txn(op='OT-UI2', amount='-40.00', org='315-AG Projection')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        row = html[html.index('OT-UI2'):]
        self.assertIn('aria-expanded="true"', row[:row.index('</form>')])

    def test_every_control_is_styled_the_same_way(self):
        """
        Django, crispy and django-ajax-selects each render differently left to
        themselves, which is what made one row look like three form libraries.
        """
        import re
        self.make_txn(op='OT-UI3', amount='-40.00')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        controls = re.findall(r'<select[^>]*>', html)
        controls += [tag for tag in re.findall(r'<input[^>]*>', html)
                     if 'type="text"' in tag]
        self.assertTrue(controls)
        for tag in controls:
            self.assertIn('form-control', tag, tag)

    def test_the_row_carries_no_inline_styling(self):
        """ Every rule lives in the stylesheet, so the rows cannot drift apart. """
        self.make_txn(op='OT-UI4', amount='-40.00')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        self.assertNotIn('style="margin-right', html)

    def test_an_answered_box_does_not_also_nag(self):
        """ A caption saying where the answer came from, or a chip offering one
        -- never both, which is what the hand-written blocks used to do. """
        self.make_txn(op='OT-UI5', amount='-40.00')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        field = html[html.index('id_txn'):]
        field = field[:field.index('</div>')]
        self.assertNotIn('fin-suggest', field)

    def test_the_import_panel_starts_out_of_the_way(self):
        """ Importing happens monthly; reconciling is what the page is for. """
        self.make_txn(op='OT-UI6', amount='-40.00')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        self.assertIn('fin-import-toggle', html)
        self.assertIn('fin-import-panel is-folded', html)

    def test_folding_is_undone_when_the_script_is_not_running(self):
        """
        A fold only script can open is a trap, not a tidy-up: a stale or failed
        queue.js would make those fields unreachable rather than merely hidden.
        """
        self.make_txn(op='OT-UI7', amount='-40.00')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        block = html[html.index('<noscript>'):html.index('</noscript>')]
        self.assertIn('.fin-fields-more.is-folded', block)
        self.assertIn('.fin-import-panel.is-folded', block)
        self.assertIn('.fin-more-toggle', block)

    #: The assets this module owns, wherever they are served from. They live in
    #: the site-wide static/css and static/js alongside everything else, so they
    #: are named rather than found by a path prefix.
    OWN_ASSETS = ('css/finance.css', 'js/queue.js', 'js/routing.js')

    def test_every_finance_asset_carries_a_cache_buster(self):
        """
        Without the stamp a changed stylesheet is invisible until a hard
        refresh, and a script that never arrives looks exactly like a button
        that does nothing. See :func:`finance.templatetags.finance_extras.asset`.
        """
        import re
        self.make_txn(op='OT-UI8', amount='-40.00')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        found = re.findall(r'/static/([^"?]+)(\?v=[^"]*)?', html)
        stamped = {path: bool(stamp) for path, stamp in found}
        for name in self.OWN_ASSETS:
            self.assertIn(name, stamped, "%s is no longer on the queue page" % name)
            self.assertTrue(stamped[name], "%s is served without a cache buster" % name)

    def test_the_module_keeps_no_static_folder_of_its_own(self):
        """ Its CSS and JS sit in static/css and static/js like everything else. """
        import os
        from django.conf import settings
        from django.contrib.staticfiles import finders

        for name in self.OWN_ASSETS:
            self.assertIsNotNone(finders.find(name), "%s is missing from the static tree" % name)
        for directory in settings.STATICFILES_DIRS:
            self.assertFalse(os.path.isdir(os.path.join(str(directory), 'finance')),
                             "static/finance is back")

    def test_suggestions_endpoint(self):
        txn = self.make_txn(op='OT-Q7')
        response = self.client.get(reverse('finance:suggestions', args=[txn.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['kind'], 'expense')
        # The JSON payload carries ids as strings so the browser can drop them
        # straight into a <select>.
        self.assertEqual(data['spend_category']['value'], str(category('consumables').pk))
        self.assertEqual(data['spend_category']['label'], 'Consumables')

    def test_encumbrance_creation(self):
        response = self.client.post(reverse('finance:encumbrance-new'), {
            'amount': '75.00',
            'effective_date': '2025-09-15',
            'description': 'Gaff tape run',
            'audit_explanation': 'Restocking the shop',
            'fund_source': fund('sga_budget').pk,
            'lnl_spend_category': category('consumables').pk,
        })
        self.assertEqual(response.status_code, 302)
        entry = ParsedTransaction.objects.get(description='Gaff tape run')
        self.assertEqual(entry.amount, Decimal('-75.00'))  # normalised to an expense
        self.assertTrue(entry.is_encumbrance)
        self.assertEqual(entry.status, TransactionStatus.PENDING)


class SplitViewTests(FinanceViewTestCase):
    def setUp(self):
        super(SplitViewTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.txn = self.make_txn(op='OT-S1', amount='-1200.00')

    def _post(self, rows):
        data = {
            'slices-TOTAL_FORMS': str(len(rows)),
            'slices-INITIAL_FORMS': '0',
            'slices-MIN_NUM_FORMS': '0',
            'slices-MAX_NUM_FORMS': '1000',
        }
        for index, row in enumerate(rows):
            for key, value in row.items():
                data['slices-%s-%s' % (index, key)] = value
        return self.client.post(reverse('finance:txn-detail', args=[self.txn.pk]), data)

    def test_detail_renders_immutable_pane(self):
        response = self.client.get(reverse('finance:txn-detail', args=[self.txn.pk]))
        self.assertContains(response, "Workday Record")
        self.assertContains(response, "OT-S1")
        self.assertContains(response, "read-only")

    def test_balanced_split_saves(self):
        response = self._post([
            {'amount': '-200.00', 'description': 'Consumables',
             'fund_source': fund('sga_budget').pk, 'lnl_spend_category': category('consumables').pk},
            {'amount': '-1000.00', 'description': 'Capital',
             'fund_source': fund('sga_budget').pk, 'lnl_spend_category': category('new_stuff').pk},
        ])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.txn.slices.count(), 2)
        self.assertTrue(self.txn.is_fully_allocated)

    def test_unbalanced_split_is_rejected(self):
        response = self._post([
            {'amount': '-200.00', 'description': 'Partial',
             'fund_source': fund('sga_budget').pk, 'lnl_spend_category': category('consumables').pk},
        ])
        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        self.assertEqual(self.txn.slices.count(), 0)
        self.assertContains(response, "unallocated")

    def test_split_cannot_flip_direction(self):
        response = self._post([
            {'amount': '-1400.00', 'description': 'Expense',
             'fund_source': fund('sga_budget').pk, 'lnl_spend_category': category('consumables').pk},
            {'amount': '200.00', 'description': 'Sneaky revenue',
             'fund_source': fund('sga_budget').pk, 'lnl_spend_category': category('consumables').pk},
        ])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.txn.slices.count(), 0)

    def test_save_button_disabled_until_balanced(self):
        response = self.client.get(reverse('finance:txn-detail', args=[self.txn.pk]))
        self.assertContains(response, 'id="fin-split-save"')
        self.assertContains(response, 'disabled')


class EntryDetailTests(FinanceViewTestCase):
    def setUp(self):
        super(EntryDetailTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'view_subledger_receipts')
        txn = self.make_txn(op='OT-D1')
        self.entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), description='Gaff tape',
            effective_date=txn.accounting_date)

    def test_renders(self):
        response = self.client.get(reverse('finance:entry-detail', args=[self.entry.pk]))
        self.assertContains(response, "Gaff tape")
        self.assertContains(response, "Audit Trail")

    def test_inherited_event_metadata_shown(self):
        org = OrgFactory.create(name='Student Group', workday_fund=810)
        event = Event2019Factory.create(billing_org=org)
        revenue_parent = self.make_txn(op='OT-D2', amount='500.00')
        entry = ParsedTransaction.objects.create(
            parent_transaction=revenue_parent, amount=Decimal('500.00'), linked_event=event,
            effective_date=revenue_parent.accounting_date)
        response = self.client.get(reverse('finance:entry-detail', args=[entry.pk]))
        self.assertContains(response, "Student Organization")
        self.assertContains(response, "Inherited from the Event")

    def test_history_from_an_older_schema_still_renders(self):
        """
        Regression: a snapshot taken before a field changed shape (routing
        columns became foreign keys, so 'sga_budget' sits where an id belongs)
        made reversion raise RevertError, which took the whole page down.
        """
        for comment in ('first', 'second'):
            with reversion.create_revision():
                reversion.set_comment(comment)
                self.entry.save()

        newest = Version.objects.get_for_object(self.entry).first()
        payload = json.loads(newest.serialized_data)
        payload[0]['fields']['fund_source'] = 'sga_budget'
        newest.serialized_data = json.dumps(payload)
        newest.save(update_fields=['serialized_data'])

        response = self.client.get(reverse('finance:entry-detail', args=[self.entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "details unavailable")

    def test_delete_removes_slice_not_bank_line(self):
        response = self.client.post(reverse('finance:entry-delete', args=[self.entry.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ParsedTransaction.objects.filter(pk=self.entry.pk).exists())
        self.assertTrue(WorkdayTransaction.objects.filter(operational_transaction='OT-D1').exists())


class ProjectExplorerTests(FinanceViewTestCase):
    def setUp(self):
        super(ProjectExplorerTests, self).setUp()
        self.grant('view_subledger', 'manage_projecttag')
        self.parent = ProjectTag.objects.create(name='New Equipment List', code='NEL26')
        self.child = ProjectTag.objects.create(name='D60 Lustrs', code='D60-LUSTR',
                                               parent=self.parent)
        txn = self.make_txn(op='OT-T1', amount='-8000.00')
        ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'), project_tag=self.child,
            description='Lustr fixtures', effective_date=txn.accounting_date)

    def test_tree_renders(self):
        response = self.client.get(reverse('finance:projects'))
        self.assertContains(response, "New Equipment List")
        self.assertContains(response, "D60 Lustrs")

    def test_selected_node_shows_lifetime_rollup(self):
        """
        The fully-loaded cost spans every year regardless of the FY filter --
        that is the whole point of the explorer.
        """
        response = self.client.get(reverse('finance:projects-detail', args=[self.parent.pk]))
        self.assertContains(response, "True Fully-Loaded Cost")
        self.assertContains(response, "8,000.00")   # rolled up from the child
        self.assertContains(response, "all fiscal years")

    def test_ledger_below_respects_the_fiscal_year_filter(self):
        response = self.client.get(
            reverse('finance:projects-detail', args=[self.parent.pk]) + '?fy=2026')
        self.assertContains(response, "Lustr fixtures")
        response = self.client.get(
            reverse('finance:projects-detail', args=[self.parent.pk]) + '?fy=2030')
        self.assertNotContains(response, "Lustr fixtures")

    def test_excluding_descendants(self):
        response = self.client.get(
            reverse('finance:projects-detail', args=[self.parent.pk]) + '?fy=2026&children=0')
        self.assertNotContains(response, "Lustr fixtures")

    def test_create_project(self):
        response = self.client.post(reverse('finance:project-new'), {
            'name': 'Console Refresh', 'code': 'CON27', 'parent': '',
            'description': '', 'is_projection': '', 'archived': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProjectTag.objects.filter(code='CON27').exists())


class FundingRequestViewTests(FinanceViewTestCase):
    def setUp(self):
        super(FundingRequestViewTests, self).setUp()
        self.grant('view_subledger', 'view_fundingrequest', 'manage_fundingrequest')
        self.fr = FundingRequest.objects.create(name='NEL26 Grant', fiscal_year=2026)
        self.line = FRLineItem.objects.create(funding_request=self.fr, name='Fixtures',
                                              amount_awarded=Decimal('1000.00'))

    def test_list_renders(self):
        response = self.client.get(reverse('finance:fr-list') + '?fy=2026')
        self.assertContains(response, "NEL26 Grant")

    def test_detail_renders_burndown(self):
        response = self.client.get(reverse('finance:fr-detail', args=[self.fr.pk]))
        self.assertContains(response, "Fixtures")
        self.assertContains(response, "fin-burndown")

    def _edit_post(self, **overrides):
        """ A complete POST for the edit page: the existing line plus a new one. """
        data = {
            'name': 'NEL26 Grant', 'reference': 'A.X.X', 'fiscal_year': '2026',
            'date_submitted': '', 'date_approved': '', 'is_projection': '',
            'closed': '', 'notes': '',
            'line_items-TOTAL_FORMS': '2', 'line_items-INITIAL_FORMS': '1',
            'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000',
            'line_items-0-id': str(self.line.pk), 'line_items-0-name': 'Fixtures',
            'line_items-0-description': 'Moving heads', 'line_items-0-amount_awarded': '1000.00',
            'line_items-0-lnl_spend_category': '', 'line_items-0-project_tag': '',
            'line_items-0-sort_order': '',
            'line_items-1-id': '', 'line_items-1-name': 'Cable',
            'line_items-1-description': 'Soco and edison', 'line_items-1-amount_awarded': '250.00',
            'line_items-1-lnl_spend_category': '', 'line_items-1-project_tag': '',
            'line_items-1-sort_order': '',
        }
        data.update(overrides)
        return data

    def test_edit_existing_request_saves(self):
        """
        Regression: saving a request that already had line items raised a
        reversion RegistrationError, because FundingRequest follows line_items
        and FRLineItem was not itself registered. A brand new request never hit
        it, since it has no lines at the moment its post_save fires.
        """
        response = self.client.post(reverse('finance:fr-edit', args=[self.fr.pk]),
                                    self._edit_post())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.fr.line_items.count(), 2)
        self.assertEqual(self.fr.line_items.get(name='Fixtures').description, 'Moving heads')

    def test_removing_a_saved_line_deletes_it(self):
        """
        The X on a saved row ticks the hidden DELETE flag; this is what that
        flag does once the form is submitted.
        """
        response = self.client.post(
            reverse('finance:fr-edit', args=[self.fr.pk]),
            self._edit_post(**{'line_items-0-DELETE': 'on'}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(FRLineItem.objects.filter(pk=self.line.pk).exists())
        self.assertEqual([line.name for line in self.fr.line_items.all()], ['Cable'])

    def test_edit_form_offers_the_same_remove_control_on_every_row(self):
        response = self.client.get(reverse('finance:fr-edit', args=[self.fr.pk]))
        content = response.content.decode()
        # One X per row: the saved line plus the three blank ones.
        self.assertEqual(content.count('fin-fr-drop'), 4)
        # ...and the saved row still carries the DELETE flag the X drives.
        self.assertIn('fin-fr-delete-flag', content)
        self.assertIn('line_items-0-DELETE', content)

    def test_invalid_line_leaves_request_untouched(self):
        """ A rejected line must not leave a half-saved header behind. """
        response = self.client.post(
            reverse('finance:fr-edit', args=[self.fr.pk]),
            self._edit_post(name='Renamed', **{'line_items-1-amount_awarded': '-5.00'}))
        self.assertEqual(response.status_code, 200)
        self.fr.refresh_from_db()
        self.assertEqual(self.fr.name, 'NEL26 Grant')
        self.assertEqual(self.fr.line_items.count(), 1)

    def test_overspend_flagged(self):
        txn = self.make_txn(op='OT-F1', amount='-1500.00')
        ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'), fr_line_target=self.line,
            effective_date=txn.accounting_date)
        response = self.client.get(reverse('finance:fr-detail', args=[self.fr.pk]))
        self.assertContains(response, "over by")


class ReconcileJsonTests(FinanceViewTestCase):
    """
    The queue posts one row at a time so allocating a line cannot discard what
    is typed into the others. That needs the view to answer XHR with JSON.
    """

    def setUp(self):
        super(ReconcileJsonTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.txn = self.make_txn(op='OT-AJ1', amount='-250.00')

    def _post(self, ajax=True, **overrides):
        data = {
            'txn%s-fund_source' % self.txn.pk: str(fund('sga_budget').pk),
            'txn%s-lnl_spend_category' % self.txn.pk: str(category('consumables').pk),
            'txn%s-fr_line_target' % self.txn.pk: '',
            'txn%s-project_tag' % self.txn.pk: '',
            'txn%s-audit_explanation' % self.txn.pk: '',
            'txn%s-is_projection' % self.txn.pk: '',
        }
        data.update({'txn%s-%s' % (self.txn.pk, k): v for k, v in overrides.items()})
        headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'} if ajax else {}
        return self.client.post(reverse('finance:reconcile', args=[self.txn.pk]), data, **headers)

    def test_a_good_row_answers_with_json(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertTrue(payload['done'])
        self.assertTrue(payload['settled'])
        self.assertIn('reconciled and settled', payload['message'])
        self.assertEqual(ParsedTransaction.objects.count(), 1)

    def test_a_bad_row_answers_with_field_errors(self):
        response = self._post(fund_source='')
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['ok'])
        # Keyed by field so the page can put the message beside the input.
        self.assertIn('fund_source', payload['errors'])
        self.assertEqual(ParsedTransaction.objects.count(), 0)

    def test_nothing_is_saved_when_the_row_is_rejected(self):
        self._post(fund_source='')
        self.assertFalse(ParsedTransaction.objects.exists())
        self.assertFalse(WorkdayTransaction.objects.get(pk=self.txn.pk).is_reconciled)

    def test_the_plain_post_still_redirects(self):
        """ Without JavaScript the form must behave exactly as it used to. """
        response = self._post(ajax=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ParsedTransaction.objects.count(), 1)

    def test_a_plain_post_failure_still_redirects_with_a_message(self):
        response = self._post(ajax=False, fund_source='')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ParsedTransaction.objects.count(), 0)

    def test_a_part_allocated_line_takes_only_what_is_left(self):
        """
        A line part-allocated on the split page still shows in the queue. The
        row allocates the remainder, not the full bank amount again.
        """
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-100.00'),
            effective_date=self.txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['done'])
        self.assertEqual(ParsedTransaction.objects.count(), 2)
        self.assertEqual(ParsedTransaction.objects.latest('pk').amount, Decimal('-150.00'))
        self.assertTrue(WorkdayTransaction.objects.get(pk=self.txn.pk).is_fully_allocated)


class FundingRequestInheritanceTests(FinanceViewTestCase):
    """
    A funding request line already records what it was awarded for. Choosing
    the line on the queue should carry that across rather than asking again.
    """

    def setUp(self):
        super(FundingRequestInheritanceTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')
        self.txn = self.make_txn(op='OT-FRI', amount='-250.00')
        self.project = ProjectTag.objects.create(name='New Equipment List', code='NEL26')
        fr = FundingRequest.objects.create(name='NEL26 Grant', fiscal_year=self.txn.fiscal_year)
        self.line = FRLineItem.objects.create(
            funding_request=fr, name='Consumables', amount_awarded=Decimal('1000.00'),
            lnl_spend_category=category('consumables'), project_tag=self.project)
        self.bare_line = FRLineItem.objects.create(
            funding_request=fr, name='Unclassified', amount_awarded=Decimal('500.00'))

    def _options(self):
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        return str(form['fr_line_target'])

    def test_the_line_carries_its_spend_category_to_the_browser(self):
        self.assertIn('data-spend-category="%s"' % category('consumables').pk, self._options())

    def test_the_line_carries_its_project_to_the_browser(self):
        self.assertIn('data-project-tag="%s"' % self.project.pk, self._options())

    def test_a_line_with_no_expected_routing_carries_none(self):
        rendered = self._options()
        # The bare line's option must not claim routing it does not have.
        option = [chunk for chunk in rendered.split('<option')
                  if 'value="%s"' % self.bare_line.pk in chunk][0]
        self.assertNotIn('data-spend-category', option)
        self.assertNotIn('data-project-tag', option)

    def test_the_inherited_values_are_what_the_server_accepts(self):
        """ End to end: post what the browser would fill in and it validates. """
        data = {
            't-fund_source': str(fund('sga_fr').pk),
            't-fr_line_target': str(self.line.pk),
            't-lnl_spend_category': str(self.line.lnl_spend_category_id),
            't-project_tag': str(self.line.project_tag_id),
            't-audit_explanation': '', 't-is_projection': '',
        }
        form = ReconcileForm(data, parent_transaction=self.txn, prefix='t')
        self.assertTrue(form.is_valid(), form.errors)

    def test_the_picker_costs_no_query_per_line(self):
        """
        Each option shows the line's remaining balance, which was a query per
        line, per form, per row of the queue.
        """
        for n in range(6):
            FRLineItem.objects.create(
                funding_request=self.line.funding_request, name='Line %s' % n,
                amount_awarded=Decimal('100.00'))
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        with self.assertNumQueries(1):
            str(form['fr_line_target'])


class AssetStampTests(TestCase):
    """
    The cache-buster used to be the git SHA, which does not change between
    commits, so an edited stylesheet or script kept being served from the
    browser's cache. A script that never arrives looks exactly like a button
    that does nothing, which is a miserable thing to debug.
    """

    def test_in_development_it_follows_the_file(self):
        import os
        from django.contrib.staticfiles import finders
        from finance.templatetags.finance_extras import asset

        with override_settings(DEBUG=True):
            url = asset('js/queue.js')
        mtime = int(os.path.getmtime(finders.find('js/queue.js')))
        self.assertEqual(url, '/static/js/queue.js?v=%s' % mtime)

    def test_editing_a_file_changes_the_stamp(self):
        import os
        from django.contrib.staticfiles import finders
        from finance.templatetags.finance_extras import asset

        path = finders.find('js/queue.js')
        original = os.path.getmtime(path)
        with override_settings(DEBUG=True):
            before = asset('js/queue.js')
            os.utime(path, (original + 60, original + 60))
            try:
                self.assertNotEqual(asset('js/queue.js'), before)
            finally:
                os.utime(path, (original, original))

    def test_in_production_it_is_the_release(self):
        """ Files there only change when a deploy does, and no file is stat'd. """
        from finance.templatetags.finance_extras import asset

        with override_settings(DEBUG=False, GIT_RELEASE='abc123'):
            self.assertEqual(asset('js/queue.js'), '/static/js/queue.js?v=abc123')

    def test_a_missing_file_still_produces_a_url(self):
        from finance.templatetags.finance_extras import asset

        with override_settings(DEBUG=True):
            self.assertEqual(asset('js/not-here.js'), '/static/js/not-here.js')


class UnreconcileTests(FinanceViewTestCase):
    """
    The way back out of an allocation.

    Noticing a line was filed wrong is one thought; taking it back used to be
    five navigations and a confirmation page per slice, which in practice meant
    the wrong answer stayed.
    """

    def setUp(self):
        super(UnreconcileTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.txn = self.make_txn(op='OT-U1', amount='-500.00')
        self.entry = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-500.00'),
            effective_date=self.txn.accounting_date, description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'),
            status=TransactionStatus.SETTLED)

    def _undo(self, **extra):
        return self.client.post(reverse('finance:unreconcile', args=[self.txn.pk]),
                                extra, follow=True)

    def test_the_allocations_go_and_the_line_returns_to_the_queue(self):
        self._undo()
        self.assertFalse(ParsedTransaction.objects.filter(pk=self.entry.pk).exists())
        self.assertEqual(self.txn.unallocated_amount, Decimal('-500.00'))
        self.assertIn(self.txn, WorkdayTransaction.objects.unreconciled())

    def test_a_settled_allocation_is_undone_too(self):
        """
        Reconciling settles the line in the same click when it balances, so an
        undo that refused to touch settled slices could never undo anything.
        """
        self.assertEqual(self.entry.status, TransactionStatus.SETTLED)
        self._undo()
        self.assertEqual(self.txn.slices.count(), 0)

    def test_the_workday_line_itself_is_untouched(self):
        self._undo()
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.net_amount, Decimal('-500.00'))
        self.assertEqual(self.txn.operational_transaction, 'OT-U1')

    def test_a_refunded_allocation_is_refused_with_a_reason(self):
        """ The refund exists to reverse that purchase; the row is load-bearing. """
        ParsedTransaction.objects.create(
            parent_transaction=self.make_txn(op='OT-U2', amount='120.00'),
            amount=Decimal('120.00'), effective_date=self.txn.accounting_date,
            refund_of=self.entry, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        response = self._undo()
        self.assertContains(response, "Remove the refund first")
        self.assertTrue(ParsedTransaction.objects.filter(pk=self.entry.pk).exists())

    def test_undoing_nothing_says_so_rather_than_failing(self):
        self.txn.slices.all().delete()
        response = self._undo()
        self.assertContains(response, "nothing allocated")

    def test_it_answers_xhr_with_json(self):
        response = self.client.post(
            reverse('finance:unreconcile', args=[self.txn.pk]), {},
            headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['removed'], 1)

    def test_it_needs_the_edit_permission(self):
        stranger = get_user_model().objects.create_user(
            username='nosy', email='nosy@wpi.edu', password='x')
        self.client.force_login(stranger)
        response = self.client.post(reverse('finance:unreconcile', args=[self.txn.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ParsedTransaction.objects.filter(pk=self.entry.pk).exists())

    def test_get_is_not_enough_to_delete_anything(self):
        response = self.client.get(reverse('finance:unreconcile', args=[self.txn.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(ParsedTransaction.objects.filter(pk=self.entry.pk).exists())


class BulkReconcileTests(FinanceViewTestCase):
    """
    Reconciling a batch of rows that all take the same answers.

    A monthly export arrives with a dozen supply orders on it, all Consumables
    out of the standing budget, and the per-row form asks the same two
    questions a dozen times.
    """

    def setUp(self):
        super(BulkReconcileTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.a = self.make_txn(op='OT-B1', amount='-40.00')
        self.b = self.make_txn(op='OT-B2', amount='-55.00')

    def _post(self, ids=None, **extra):
        data = {
            'selected': ','.join(str(t.pk) for t in (ids if ids is not None else [self.a, self.b])),
            'fund_source': fund('sga_budget').pk,
            'lnl_spend_category': category('consumables').pk,
        }
        data.update(extra)
        return self.client.post(reverse('finance:bulk-reconcile'), data, follow=True)

    def test_every_selected_line_gets_the_same_routing(self):
        self._post()
        for txn in (self.a, self.b):
            entry = txn.slices.get()
            self.assertEqual(entry.fund_source, fund('sga_budget'))
            self.assertEqual(entry.lnl_spend_category, category('consumables'))

    def test_each_slice_takes_its_own_line_amount(self):
        """ One answer, but not one amount -- each row keeps its own value. """
        self._post()
        self.assertEqual(self.a.slices.get().amount, Decimal('-40.00'))
        self.assertEqual(self.b.slices.get().amount, Decimal('-55.00'))

    def test_the_lines_leave_the_queue(self):
        self._post()
        remaining = WorkdayTransaction.objects.unreconciled()
        self.assertNotIn(self.a, remaining)
        self.assertNotIn(self.b, remaining)

    def test_they_are_settled_when_the_permission_allows(self):
        self._post()
        self.assertEqual(self.a.slices.get().status, TransactionStatus.SETTLED)

    def test_a_partly_allocated_line_is_finished_not_doubled(self):
        """ The slice takes what is left, exactly as the single-row form does. """
        ParsedTransaction.objects.create(
            parent_transaction=self.a, amount=Decimal('-15.00'),
            effective_date=self.a.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self._post(ids=[self.a])
        self.assertEqual(self.a.slices.count(), 2)
        self.assertEqual(self.a.unallocated_amount, Decimal('0.00'))

    def test_revenue_is_reported_and_left_alone(self):
        """ Expense routing on money coming in is refused by the database. """
        credit = self.make_txn(op='OT-B3', amount='500.00')
        response = self._post(ids=[self.a, credit])
        self.assertContains(response, "revenue line skipped")
        self.assertEqual(credit.slices.count(), 0)
        self.assertEqual(self.a.slices.count(), 1)

    def test_an_already_reconciled_line_is_not_touched_twice(self):
        ParsedTransaction.objects.create(
            parent_transaction=self.a, amount=self.a.net_amount,
            effective_date=self.a.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        response = self._post(ids=[self.a])
        self.assertContains(response, "already fully allocated")
        self.assertEqual(self.a.slices.count(), 1)

    def test_the_category_is_optional(self):
        self._post(lnl_spend_category='')
        self.assertIsNone(self.a.slices.get().lnl_spend_category)

    def test_a_fund_is_required(self):
        response = self._post(fund_source='')
        self.assertEqual(self.a.slices.count(), 0)
        self.assertContains(response, "required")

    def test_nothing_selected_says_so(self):
        response = self._post(selected='')
        self.assertContains(response, "Nothing was selected")

    def test_a_fund_needing_a_funding_request_is_not_offered(self):
        """
        Its FR line cannot be chosen in bulk, so every row would come out
        invalid -- the same reason the ledger's bulk bar leaves it out.
        """
        form = BulkReconcileForm()
        offered = [f.slug for f in form.fields['fund_source'].queryset]
        self.assertNotIn('sga_fr', offered)
        self.assertIn('sga_budget', offered)

    def test_it_needs_the_edit_permission(self):
        stranger = get_user_model().objects.create_user(
            username='onlooker', email='onlooker@wpi.edu', password='x')
        self.client.force_login(stranger)
        response = self.client.post(reverse('finance:bulk-reconcile'), {
            'selected': str(self.a.pk), 'fund_source': fund('sga_budget').pk})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.a.slices.count(), 0)

    def test_get_reconciles_nothing(self):
        response = self.client.get(reverse('finance:bulk-reconcile'))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.a.slices.count(), 0)

    def test_the_queue_offers_a_checkbox_on_expense_rows_only(self):
        self.make_txn(op='OT-B4', amount='500.00')
        html = self.client.get(reverse('finance:queue') + '?fy=2026').content.decode()
        # Two expense rows in setUp, plus the revenue row which gets none.
        self.assertEqual(html.count('class="fin-queue-check"'), 2)
        self.assertIn('fin-qbulk-bar', html)


class AutocompleteAssetsOnPagesTests(FinanceViewTestCase):
    """
    Every finance page must be able to run ``ajax_select.js`` to completion.

    Merely having the script on the page proves nothing, and asserting that was
    the first mistake made here. ``base.html`` loads ``ajax_select.js`` for the
    whole site, and its last line is::

        })(window.jQuery, window.django.jQuery);

    ``window.django`` is created by ``admin/js/jquery.init.js``, which
    ``base.html`` does not load. So on any page that supplies nothing further,
    that line throws ``TypeError`` before the module body runs: the plugin is
    never registered, the ready handler never binds, and every
    ``data-ajax-select`` input on the page stays an ordinary text box that
    searches nothing.

    The condition worth testing is therefore an ordering one -- ``jquery.init.js``
    must appear, and an ``ajax_select.js`` tag must come *after* it.
    """

    #: Defines ``window.django`` and calls ``jQuery.noConflict(true)``, which
    #: also puts ``window.$`` back to the jQuery 1.10 the finance scripts want.
    INIT = 'admin/js/jquery.init.js'
    LOOKUP = 'ajax_select/js/ajax_select.js'

    def setUp(self):
        super(AutocompleteAssetsOnPagesTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')

    def _assert_wired(self, url_name, *args):
        response = self.client.get(reverse(url_name, args=args))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()

        self.assertIn(
            self.INIT, body,
            '%s never loads jquery.init.js, so window.django is undefined and the '
            'copy of ajax_select.js that base.html loads throws before registering '
            'anything. The event picker is an inert text box.' % url_name)

        init_at = body.index(self.INIT)
        after = body.find(self.LOOKUP, init_at)
        self.assertNotEqual(
            after, -1,
            '%s loads jquery.init.js but no copy of ajax_select.js after it, so '
            'nothing ever registers the autocomplete.' % url_name)
        return body

    def test_the_queue_can_run_the_autocomplete_script(self):
        """ The queue is the page the event picker matters most on. """
        self._assert_wired('finance:queue')

    def test_the_ledger_can_run_the_autocomplete_script(self):
        self._assert_wired('finance:ledger')

    def test_the_encumbrance_form_can_run_the_autocomplete_script(self):
        self._assert_wired('finance:encumbrance-new')

    def test_the_entry_page_can_run_the_autocomplete_script(self):
        txn = self.make_txn()
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn,
            amount=txn.net_amount,
            effective_date=txn.accounting_date,
            description='Supplies',
            fund_source=fund(),
            lnl_spend_category=category(),
        )
        self._assert_wired('finance:entry-detail', entry.pk)

    def test_the_transaction_page_can_run_the_autocomplete_script(self):
        """ The split modal has a formset, so there is no ``form`` to take media from. """
        txn = self.make_txn(op='OT-SPLIT')
        self._assert_wired('finance:txn-detail', txn.pk)

    def test_the_dashboard_can_run_the_autocomplete_script(self):
        """
        Included for consistency rather than need.

        The media is emitted once for the whole app precisely so no page has to
        remember, and a page with no autocomplete on it simply finds nothing to
        wire up.
        """
        self._assert_wired('finance:dashboard')

    def test_the_markup_the_script_looks_for_is_present(self):
        """
        The script and the markup have to agree, or neither is any use.

        ``ajax_select.js`` binds to ``input[data-ajax-select=autocompleteselect]``
        and reads the endpoint out of ``data-plugin-options``.
        """
        body = self._assert_wired('finance:encumbrance-new')
        self.assertIn('data-ajax-select', body)
        self.assertIn('ajax_lookup/Events', body)

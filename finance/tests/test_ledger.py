"""
The spreadsheet ledger: its facets, and the guard rails on its bulk actions.

The ledger is the page people read the year off, so a filter that silently
returns the wrong rows is worse than one that errors -- nothing on screen would
say so. Every facet is tested for what it includes *and* what it leaves out.

The bulk bar is tested hardest of all. It writes to many rows at once from one
click, and the rule it follows is that it must never be the thing that writes a
row the rest of the app would have rejected: anything it cannot legally apply
is reported and skipped, never forced and never silently dropped.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from finance.models import (FRLineItem, FundingRequest, ParsedTransaction, ProjectTag,
                            TransactionStatus)
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund


class LedgerFacetTests(FinanceViewTestCase):
    """ Each facet narrows the ledger to exactly what it names, and no more. """

    def setUp(self):
        super(LedgerFacetTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')

        self.tag = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        spend_txn = self.make_txn(op='OT-F1', amount='-120.00')
        self.spend = ParsedTransaction.objects.create(
            parent_transaction=spend_txn, amount=Decimal('-120.00'),
            effective_date=spend_txn.accounting_date, description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'),
            project_tag=self.tag, status=TransactionStatus.SETTLED)

        income_txn = self.make_txn(op='OT-F2', amount='700.00')
        self.income = ParsedTransaction.objects.create(
            parent_transaction=income_txn, amount=Decimal('700.00'),
            effective_date=income_txn.accounting_date, description='Concert billing',
            non_event_revenue_type_id=None, status=TransactionStatus.PENDING)
        from finance.models import RevenueSource
        self.income.non_event_revenue_type = RevenueSource.objects.active().first()
        self.income.save()

        repair_txn = self.make_txn(op='OT-F3', amount='-90.00')
        self.repair = ParsedTransaction.objects.create(
            parent_transaction=repair_txn, amount=Decimal('-90.00'),
            effective_date=repair_txn.accounting_date, description='Chain motor service',
            fund_source=fund('legacy'), lnl_spend_category=category('repairs'))

    def _ledger(self, query=''):
        return self.client.get(reverse('finance:ledger') + '?fy=2026&' + query)

    def test_the_status_facet_narrows_to_that_status(self):
        settled = self._ledger('status=%s' % TransactionStatus.SETTLED)
        self.assertContains(settled, 'Gaff tape')
        self.assertNotContains(settled, 'Chain motor service')

    def test_an_unknown_status_is_ignored_rather_than_erroring(self):
        """ A hand-edited URL should not be able to 500 the page. """
        response = self._ledger('status=neither')
        self.assertContains(response, 'Gaff tape')
        self.assertContains(response, 'Chain motor service')

    def test_the_category_facet_filters_by_slug(self):
        """ Slugs, so a link stays readable and survives a rename in the admin. """
        response = self._ledger('category=repairs')
        self.assertContains(response, 'Chain motor service')
        self.assertNotContains(response, 'Gaff tape')

    def test_the_fund_facet_filters_by_slug(self):
        response = self._ledger('fund=legacy')
        self.assertContains(response, 'Chain motor service')
        self.assertNotContains(response, 'Gaff tape')

    def test_the_project_facet_filters_by_id(self):
        response = self._ledger('project=%s' % self.tag.pk)
        self.assertContains(response, 'Gaff tape')
        self.assertNotContains(response, 'Chain motor service')

    def test_a_non_numeric_project_is_ignored(self):
        """ ``project`` is an id, so anything else is a malformed URL, not a filter. """
        response = self._ledger('project=NEL26')
        self.assertContains(response, 'Gaff tape')
        self.assertContains(response, 'Chain motor service')

    def test_the_revenue_facet_shows_only_money_coming_in(self):
        response = self._ledger('kind=revenue')
        self.assertContains(response, 'Concert billing')
        self.assertNotContains(response, 'Gaff tape')

    def test_the_expense_facet_shows_only_money_going_out(self):
        response = self._ledger('kind=expense')
        self.assertContains(response, 'Gaff tape')
        self.assertNotContains(response, 'Concert billing')

    def test_a_refund_counts_as_an_expense_not_as_revenue(self):
        """ A contra-expense belongs with what it reverses; see ``entry_type``. """
        credit_txn = self.make_txn(op='OT-F4', amount='20.00')
        ParsedTransaction.objects.create(
            parent_transaction=credit_txn, amount=Decimal('20.00'),
            effective_date=credit_txn.accounting_date, description='Tape returned',
            refund_of=self.spend, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self.assertContains(self._ledger('kind=expense'), 'Tape returned')
        self.assertNotContains(self._ledger('kind=revenue'), 'Tape returned')

    def test_facets_combine_rather_than_replace_one_another(self):
        response = self._ledger('kind=expense&fund=legacy')
        self.assertContains(response, 'Chain motor service')
        self.assertNotContains(response, 'Gaff tape')
        self.assertNotContains(response, 'Concert billing')

    def test_the_search_reaches_the_audit_note_and_the_bank_line(self):
        self.spend.audit_explanation = 'Restocking after the fall season'
        self.spend.save()
        self.assertContains(self._ledger('q=restocking'), 'Gaff tape')
        self.assertContains(self._ledger('q=OT-F1'), 'Gaff tape')

    def test_the_search_reaches_the_project_code(self):
        self.assertContains(self._ledger('q=NEL26'), 'Gaff tape')

    def test_the_totals_are_reported_in_cents(self):
        """
        These are aggregates, and an aggregate is where float noise gets in.
        See :func:`finance.models.money`.
        """
        response = self._ledger()
        self.assertEqual(str(response.context['expense_total']), '210.00')
        self.assertEqual(str(response.context['revenue_total']), '700.00')
        self.assertEqual(str(response.context['net_total']), '490.00')

    def test_the_totals_follow_the_filter(self):
        """ A filtered page whose totals describe the unfiltered set is a lie. """
        response = self._ledger('fund=legacy')
        self.assertEqual(str(response.context['expense_total']), '90.00')

    def test_paging_keeps_the_filters(self):
        response = self._ledger('q=gaff&kind=expense')
        self.assertIn('q=gaff', response.context['querystring'])
        self.assertIn('kind=expense', response.context['querystring'])
        self.assertNotIn('page=', response.context['querystring'])


class BulkActionGuardTests(FinanceViewTestCase):
    """
    What the bulk bar refuses to do, and how it says so.

    Each of these is a rule that holds elsewhere in the app; the risk is that
    acting on many rows at once is the one path that quietly bypasses it.
    """

    def setUp(self):
        super(BulkActionGuardTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')
        expense_txn = self.make_txn(op='OT-G1', amount='-120.00')
        self.expense = ParsedTransaction.objects.create(
            parent_transaction=expense_txn, amount=Decimal('-120.00'),
            effective_date=expense_txn.accounting_date, description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))

        from finance.models import RevenueSource
        income_txn = self.make_txn(op='OT-G2', amount='700.00')
        self.income = ParsedTransaction.objects.create(
            parent_transaction=income_txn, amount=Decimal('700.00'),
            effective_date=income_txn.accounting_date, description='Concert billing',
            non_event_revenue_type=RevenueSource.objects.active().first())

    def _act(self, action, value, entries, **extra):
        data = {'action': action, action: value,
                'selected': ','.join(str(e.pk) for e in entries)}
        data.update(extra)
        return self.client.post(reverse('finance:bulk-action'), data, follow=True)

    def test_expense_routing_is_refused_on_revenue_and_said_out_loud(self):
        """
        A database constraint refuses it, so without the guard a mixed
        selection takes the whole action down with a 500.
        """
        response = self._act('fund_source', fund('legacy').pk, [self.expense, self.income])
        self.assertContains(response, 'revenue entry was skipped')
        self.expense.refresh_from_db()
        self.income.refresh_from_db()
        self.assertEqual(self.expense.fund_source, fund('legacy'))
        self.assertIsNone(self.income.fund_source)

    def test_a_category_is_refused_on_revenue_too(self):
        response = self._act('lnl_spend_category', category('repairs').pk,
                             [self.expense, self.income])
        self.assertContains(response, 'revenue entry was skipped')
        self.income.refresh_from_db()
        self.assertIsNone(self.income.lnl_spend_category)

    def test_an_entry_charged_to_a_funding_request_keeps_its_fund(self):
        """
        The fund and the FR line are a pair. Changing one in bulk without the
        other leaves a row the model would refuse.
        """
        request = FundingRequest.objects.create(name='A Term Films', reference='F.26.6',
                                                fiscal_year=2026)
        line = FRLineItem.objects.create(funding_request=request, name='Film Rights',
                                         amount_awarded=Decimal('5000.00'))
        self.expense.fund_source = fund('sga_fr')
        self.expense.fr_line_target = line
        self.expense.save()

        response = self._act('fund_source', fund('legacy').pk, [self.expense])
        self.assertContains(response, 'charged to a funding request line')
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.fund_source, fund('sga_fr'))

    def test_a_project_may_be_assigned_to_revenue_and_expense_alike(self):
        """ A project tag says what the money was *for*; both directions have one. """
        tag = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        self._act('project_tag', tag.pk, [self.expense, self.income])
        self.expense.refresh_from_db()
        self.income.refresh_from_db()
        self.assertEqual(self.expense.project_tag, tag)
        self.assertEqual(self.income.project_tag, tag)

    def test_an_encumbrance_cannot_be_settled_in_bulk(self):
        """ Nothing has cleared the bank, so there is nothing to settle against. """
        encumbrance = ParsedTransaction.objects.create(
            amount=Decimal('-400.00'), effective_date=datetime.date(2025, 9, 15),
            description='Deposit on a console', fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'))
        response = self._act('status', TransactionStatus.SETTLED, [encumbrance])
        self.assertContains(response, 'not fully allocated yet')
        encumbrance.refresh_from_db()
        self.assertEqual(encumbrance.status, TransactionStatus.PENDING)

    def test_a_balanced_line_does_settle_in_bulk(self):
        response = self._act('status', TransactionStatus.SETTLED, [self.expense])
        self.assertContains(response, 'Updated 1 entry')
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.status, TransactionStatus.SETTLED)

    def test_a_fund_needing_a_funding_request_is_never_offered(self):
        """
        Guarded at the form rather than per row: the FR line cannot be chosen
        in bulk, so there is no selection for which this fund would be valid.
        """
        from finance.forms import BulkActionForm
        offered = [f.slug for f in BulkActionForm().fields['fund_source'].queryset]
        self.assertNotIn('sga_fr', offered)
        self.assertIn('sga_budget', offered)

    def test_a_row_the_change_would_invalidate_is_named_not_written(self):
        """
        Every row is validated on its own rather than trusting the selection.

        ``save()`` does not validate, so a row written by a migration or from
        the shell can be legal to the database and invalid to ``clean()`` --
        here, revenue naming neither an event nor a revenue type. Touching it
        in bulk must report it, not save it and not abandon the whole action.
        """
        from finance.models import WorkdayTransaction
        orphan_txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-G3', accounting_date=datetime.date(2025, 9, 15),
            net_amount=Decimal('250.00'))
        orphan = ParsedTransaction.objects.create(
            parent_transaction=orphan_txn, amount=Decimal('250.00'),
            effective_date=orphan_txn.accounting_date, description='Unattributed deposit')

        tag = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        response = self._act('project_tag', tag.pk, [orphan, self.expense])

        self.assertContains(response, 'unchanged')
        orphan.refresh_from_db()
        self.assertIsNone(orphan.project_tag)
        # The valid row in the same selection still goes through.
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.project_tag, tag)

    def test_an_empty_selection_says_so(self):
        response = self._act('project_tag', ProjectTag.objects.create(
            name='Rig', code='RIG').pk, [])
        self.assertContains(response, 'Nothing was selected')

    def test_an_action_with_no_value_is_refused(self):
        response = self.client.post(reverse('finance:bulk-action'), {
            'action': 'project_tag', 'project_tag': '',
            'selected': str(self.expense.pk)}, follow=True)
        self.assertContains(response, 'Pick a value to apply')

    def test_the_bulk_bar_needs_the_edit_permission(self):
        stranger = get_user_model().objects.create_user(
            username='reader', email='reader@wpi.edu', password='x')
        self.client.force_login(stranger)
        response = self.client.post(reverse('finance:bulk-action'), {
            'action': 'lnl_spend_category', 'lnl_spend_category': category('repairs').pk,
            'selected': str(self.expense.pk)})
        self.assertEqual(response.status_code, 403)
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.lnl_spend_category, category('consumables'))

    def test_a_bulk_change_is_recorded_in_the_audit_trail(self):
        """ Many rows from one click is exactly when "who did this?" gets asked. """
        from reversion.models import Version
        tag = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        self._act('project_tag', tag.pk, [self.expense])
        versions = Version.objects.get_for_object(self.expense)
        self.assertTrue(versions)
        self.assertIn('Bulk project tag', versions[0].revision.get_comment())

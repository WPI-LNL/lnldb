"""
SGA budgets beside funding requests: one budget a year, named for its year,
with numbered lines on either side grouped under the Treasurer's own
categories; requested and approved amounts on every line, where a blank
approved amount is SGA not having decided and $0 is SGA turning a line down.
"""
import datetime
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from finance.admin import FRLineItemInline
from finance.calculators import revenue_by_source, sga_receivables
from finance.forms import (BudgetCategoryFormSet, BulkActionForm, FRLineItemFormSet,
                           FundingRequestForm, ReconcileForm, open_fr_lines)
from finance.models import (BudgetCategory, DrawsOn, FRLineItem, FundingKind, FundingRequest,
                            FundSource, LineTotals, ParsedTransaction, RevenueSource,
                            WorkdayTransaction, current_fiscal_year, fiscal_year_bounds)
from finance.reports import _money_in
from finance.suggestions import AWARD, EXPORT, HIGH, MEDIUM, MEMO, parse_memo, suggest_all
from finance.templatetags.finance_extras import approved, requested
from finance.tests.test_forms import bank
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, encumbrance, fund, revenue_source
from finance.views.ledger import LEDGER_CSV_COLUMNS

YEAR = current_fiscal_year()
YY = str(YEAR)[-2:]


def make_budget(year=YEAR, name=None, **kwargs):
    return FundingRequest.objects.create(kind=FundingKind.BUDGET, fiscal_year=year,
                                         name=name or 'FY%s SGA Budget' % str(year)[-2:],
                                         **kwargs)


def charge(line, amount='-100.00', op='OT-B1', fund_slug='sga_fr'):
    """ Spending charged to ``line``, written straight to the table as a fixture. """
    return ParsedTransaction.objects.create(
        parent_transaction=bank(op=op, amount=amount), amount=Decimal(amount),
        effective_date=datetime.date(2025, 9, 15), fund_source=fund(fund_slug),
        lnl_spend_category=category('consumables'), fr_line_target=line)


class FundSettingTests(TestCase):
    """ The migration carried the yes/no across and pointed SGA's budget fund at budgets. """

    def test_seeded_funds_draw_on_the_right_lines(self):
        draws = dict(FundSource.objects.values_list('slug', 'draws_on'))
        self.assertEqual(draws['sga_fr'], DrawsOn.REQUEST)
        self.assertEqual(draws['sga_budget'], DrawsOn.BUDGET)
        self.assertEqual(draws['legacy'], DrawsOn.NOTHING)

    def test_only_the_request_fund_requires_a_funding_request_line(self):
        self.assertTrue(fund('sga_fr').requires_funding_request)
        self.assertFalse(fund('sga_budget').requires_funding_request)
        self.assertTrue(fund('sga_budget').draws_on_budget)


class BudgetRuleTests(TestCase):

    def test_one_budget_a_year(self):
        make_budget()
        second = FundingRequest(kind=FundingKind.BUDGET, fiscal_year=YEAR,
                                name='FY%s SGA Budget' % YY)
        with self.assertRaises(ValidationError) as caught:
            second.full_clean()
        self.assertIn('fiscal_year', caught.exception.message_dict)
        self.assertIn('already a budget', caught.exception.message_dict['fiscal_year'][0])

    def test_another_year_is_fine(self):
        make_budget(year=YEAR - 1)
        make_budget().full_clean()

    def test_the_name_must_give_the_budgets_own_year(self):
        budget = FundingRequest(kind=FundingKind.BUDGET, fiscal_year=YEAR,
                                name='FY%s SGA Budget' % str(YEAR - 1)[-2:])
        with self.assertRaises(ValidationError) as caught:
            budget.full_clean()
        self.assertIn('name', caught.exception.message_dict)

    def test_the_name_must_give_a_year(self):
        budget = FundingRequest(kind=FundingKind.BUDGET, fiscal_year=YEAR, name='SGA Budget')
        with self.assertRaises(ValidationError) as caught:
            budget.full_clean()
        self.assertIn('Put the fiscal year in the name', caught.exception.message_dict['name'][0])

    def test_four_digit_and_spaced_years_are_read(self):
        for name in ('fy %s budget' % YY, 'SGA Budget FY%s' % YEAR, 'FY %s SGA Budget' % YEAR):
            FundingRequest(kind=FundingKind.BUDGET, fiscal_year=YEAR, name=name).full_clean()

    def test_a_requests_name_is_not_checked(self):
        FundingRequest(fiscal_year=YEAR, name='FY20 leftovers').full_clean()

    def test_a_budget_has_no_number_side_or_opening_figure_of_its_own(self):
        budget = FundingRequest(kind=FundingKind.BUDGET, fiscal_year=YEAR,
                                name='FY%s SGA Budget' % YY, reference='A.%s.4' % YY,
                                is_projection=True, owed_at_books_start=Decimal('50.00'))
        budget.full_clean()
        self.assertEqual(budget.reference, '')
        self.assertFalse(budget.is_projection)
        self.assertEqual(budget.owed_at_books_start, Decimal('0.00'))

    def test_type_is_fixed_once_money_is_charged(self):
        fr = FundingRequest.objects.create(name='Truss', fiscal_year=YEAR)
        line = FRLineItem.objects.create(funding_request=fr, name='Truss',
                                         amount_awarded=Decimal('500.00'))
        charge(line)
        fr.kind = FundingKind.BUDGET
        fr.name = 'FY%s SGA Budget' % YY
        with self.assertRaises(ValidationError) as caught:
            fr.full_clean()
        self.assertIn('kind', caught.exception.message_dict)

    def test_type_can_change_before_any_money(self):
        fr = FundingRequest.objects.create(name='FY%s SGA Budget' % YY, fiscal_year=YEAR)
        fr.kind = FundingKind.BUDGET
        fr.full_clean()

    def test_a_budget_reads_as_its_year_in_a_picker(self):
        self.assertEqual(make_budget().short_label, 'FY%s · Budget' % YY)

    def test_line_number_is_four_digits(self):
        budget = make_budget()
        line = FRLineItem(funding_request=budget, name='Gaff', number='452',
                          amount_awarded=Decimal('10.00'))
        with self.assertRaises(ValidationError) as caught:
            line.full_clean()
        self.assertIn('number', caught.exception.message_dict)


class ApprovalTests(TestCase):
    """ Blank is pending SGA approval; $0 is denied. The two are never confused. """

    def setUp(self):
        self.fr = FundingRequest.objects.create(name='Fall OpEx', fiscal_year=YEAR)
        self.approved = FRLineItem.objects.create(
            funding_request=self.fr, name='Tape', amount_requested=Decimal('300.00'),
            amount_awarded=Decimal('200.00'))
        self.waiting = FRLineItem.objects.create(
            funding_request=self.fr, name='Cable', amount_requested=Decimal('150.00'))
        self.turned_down = FRLineItem.objects.create(
            funding_request=self.fr, name='Hazer', amount_requested=Decimal('900.00'),
            amount_awarded=Decimal('0.00'))

    def test_line_states(self):
        self.assertTrue(self.waiting.is_waiting)
        self.assertFalse(self.waiting.is_turned_down)
        self.assertIsNone(self.waiting.remaining)
        self.assertTrue(self.turned_down.is_turned_down)
        self.assertFalse(self.turned_down.is_waiting)
        self.assertEqual(self.turned_down.remaining, Decimal('0.00'))

    def test_totals_add_the_decided_lines_and_count_the_waiting(self):
        fr = FundingRequest.objects.with_totals().get(pk=self.fr.pk)
        self.assertEqual(fr.total_awarded, Decimal('200.00'))
        self.assertEqual(fr.waiting_count, 1)
        self.assertTrue(fr.approved_known)
        self.assertEqual(fr.total_requested, Decimal('1350.00'))
        self.assertEqual(fr.requested_missing_count, 0)
        # The same figures without the annotations.
        plain = FundingRequest.objects.get(pk=self.fr.pk)
        self.assertEqual((plain.total_awarded, plain.waiting_count, plain.total_requested),
                         (Decimal('200.00'), 1, Decimal('1350.00')))

    def test_approved_is_unknown_only_when_nothing_is_decided(self):
        fr = FundingRequest.objects.create(name='Spring', fiscal_year=YEAR)
        FRLineItem.objects.create(funding_request=fr, name='One')
        self.assertFalse(FundingRequest.objects.with_totals().get(pk=fr.pk).approved_known)
        self.assertIn('Pending SGA Approval',
                      approved(FundingRequest.objects.with_totals().get(pk=fr.pk)))

    def test_the_figures_say_which_is_which(self):
        self.assertIn('Pending SGA Approval', approved(self.waiting))
        self.assertIn('?', approved(self.waiting))
        self.assertIn('Denied', approved(self.turned_down))
        self.assertIn('$0', approved(self.turned_down))
        self.assertNotIn('Denied', approved(self.waiting))
        self.assertNotIn('Pending', approved(self.turned_down))
        self.assertEqual(approved(self.approved), '$200.00')
        total = approved(FundingRequest.objects.with_totals().get(pk=self.fr.pk))
        self.assertIn('$200.00', total)
        self.assertIn('1 line pending SGA approval', total)

    def test_requested_is_unknown_when_not_entered(self):
        line = FRLineItem.objects.create(funding_request=self.fr, name='Old line',
                                         amount_awarded=Decimal('10.00'))
        self.assertIn('?', requested(line))
        self.assertIn('1 line without one',
                      requested(FundingRequest.objects.with_totals().get(pk=self.fr.pk)))

    def test_neither_waiting_nor_turned_down_lines_can_be_charged(self):
        offered = set(open_fr_lines())
        self.assertIn(self.approved, offered)
        self.assertNotIn(self.waiting, offered)
        self.assertNotIn(self.turned_down, offered)

    def test_approved_budget_lines_are_offered_and_pending_ones_are_not(self):
        budget = make_budget()
        line = FRLineItem.objects.create(funding_request=budget, name='Gaff', number='4521',
                                         amount_awarded=Decimal('100.00'))
        pending = FRLineItem.objects.create(funding_request=budget, name='Gel', number='4522')
        offered = set(open_fr_lines())
        self.assertIn(line, offered)
        self.assertNotIn(pending, offered)


class LineTotalsTests(TestCase):

    def test_figures_of_a_set_of_lines(self):
        budget = make_budget()
        one = FRLineItem.objects.create(funding_request=budget, name='Gaff', number='4521',
                                        amount_requested=Decimal('100.00'),
                                        amount_awarded=Decimal('80.00'))
        FRLineItem.objects.create(funding_request=budget, name='Film', number='4522',
                                  amount_requested=Decimal('50.00'), is_projection=True)
        charge(one, amount='-30.00', fund_slug='sga_budget')
        totals = LineTotals(FRLineItem.objects.filter(funding_request=budget).with_spend())
        self.assertEqual(totals.line_count, 2)
        self.assertEqual(totals.total_requested, Decimal('150.00'))
        self.assertEqual(totals.total_awarded, Decimal('80.00'))
        self.assertEqual(totals.waiting_count, 1)
        self.assertEqual(totals.total_spent, Decimal('30.00'))
        self.assertEqual(totals.total_remaining, Decimal('50.00'))
        self.assertEqual(totals.percent_spent, 38)
        self.assertFalse(totals.is_overspent)


class DepositTests(TestCase):
    """ SGA's payments naming a budget: the deposit in, money returned out. """

    def setUp(self):
        self.budget = make_budget(year=YEAR - 1)
        self.line = FRLineItem.objects.create(funding_request=self.budget, name='Gaff',
                                              number='4521', amount_awarded=Decimal('1000.00'))

    def pay(self, amount, op):
        return ParsedTransaction.objects.create(
            parent_transaction=bank(op=op, amount=amount), amount=Decimal(amount),
            effective_date=datetime.date(2025, 7, 1), fund_source=fund('sga_budget'),
            funding_request=self.budget)

    def test_nothing_yet(self):
        self.assertEqual(self.budget.deposit_status, 'Not deposited yet')
        self.assertEqual(self.budget.budget_status, 'Nothing in or out yet')

    def test_part_deposited(self):
        # This year's: last year's would already be saying what goes back.
        self.budget.fiscal_year = YEAR
        self.budget.name = 'FY%s SGA Budget' % YY
        self.budget.save()
        self.pay('600.00', 'OT-D1')
        self.assertEqual(self.budget.deposit_status, '$600.00 of $1,000.00 deposited')
        self.assertEqual(self.budget.budget_status, 'Left to spend this year')

    def test_unspent_goes_back_after_the_year(self):
        self.pay('1000.00', 'OT-D1')
        charge(self.line, amount='-400.00', op='OT-D2', fund_slug='sga_budget')
        self.assertEqual(self.budget.left_in_account, Decimal('600.00'))
        self.assertEqual(self.budget.deposit_status, '$600.00 goes back to SGA')
        self.assertEqual(self.budget.budget_status, 'Goes back to SGA')

    def test_returned(self):
        self.pay('1000.00', 'OT-D1')
        charge(self.line, amount='-400.00', op='OT-D2', fund_slug='sga_budget')
        self.pay('-600.00', 'OT-D3')
        self.assertEqual(self.budget.total_returned, Decimal('600.00'))
        self.assertEqual(self.budget.left_in_account, Decimal('0.00'))
        self.assertEqual(self.budget.deposit_status, 'Returned $600.00 to SGA')
        self.assertEqual(self.budget.budget_status, 'The rest went back to SGA')

    def test_sga_never_owes_on_a_budget(self):
        self.pay('1000.00', 'OT-D1')
        self.assertNotIn(self.budget, [row['request'] for row in sga_receivables()['rows']])


class BudgetFormTests(TestCase):

    def post_lines(self, rows, fr=None, kind=FundingKind.BUDGET):
        data = {
            'line_items-TOTAL_FORMS': str(len(rows)),
            'line_items-INITIAL_FORMS': str(sum(1 for row in rows if row.get('id'))),
            'line_items-MIN_NUM_FORMS': '0',
            'line_items-MAX_NUM_FORMS': '1000',
        }
        for index, row in enumerate(rows):
            for key, value in row.items():
                data['line_items-%s-%s' % (index, key)] = value
        return FRLineItemFormSet(data, instance=fr, kind=kind)

    def test_header_refuses_a_name_for_another_year(self):
        form = FundingRequestForm({'kind': 'budget', 'name': 'FY%s SGA Budget' % str(YEAR - 1)[-2:],
                                   'fiscal_year': str(YEAR)})
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_type_box_is_locked_once_money_is_charged(self):
        fr = FundingRequest.objects.create(name='Truss', fiscal_year=YEAR)
        line = FRLineItem.objects.create(funding_request=fr, name='Truss',
                                         amount_awarded=Decimal('500.00'))
        self.assertFalse(FundingRequestForm(instance=fr).fields['kind'].disabled)
        charge(line)
        self.assertTrue(FundingRequestForm(instance=fr).fields['kind'].disabled)

    def test_approved_box_is_a_plain_dollar_box_with_its_meaning_under_it(self):
        """
        Grey words in the empty box read as a dropdown, so the box has no
        placeholder; the tag under it says Pending, Denied or nothing.
        """
        states = {}
        for typed in ('', '0', '0.00', '120.50', 'abc'):
            formset = self.post_lines([{'name': 'Tape', 'amount_awarded': typed}])
            states[typed] = formset.forms[0].approval_state
        self.assertEqual(states, {'': 'pending', '0': 'denied', '0.00': 'denied',
                                  '120.50': '', 'abc': ''})
        line = FRLineItemFormSet(instance=make_budget(), kind=FundingKind.BUDGET).empty_form
        self.assertEqual(line.approval_state, 'pending')
        self.assertNotIn('placeholder', str(line['amount_awarded']))

    def test_blank_approved_is_saved_as_waiting_not_zero(self):
        fr = make_budget()
        formset = self.post_lines([{'name': 'Gaff', 'number': '4521', 'amount_requested': '50.00',
                                    'amount_awarded': ''}], fr=fr)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertIsNone(fr.line_items.get().amount_awarded)

    def test_a_charged_line_cannot_go_back_to_pending(self):
        fr = FundingRequest.objects.create(name='Truss', fiscal_year=YEAR)
        line = FRLineItem.objects.create(funding_request=fr, name='Truss',
                                         amount_awarded=Decimal('500.00'))
        charge(line)
        formset = self.post_lines([{'id': str(line.pk), 'name': 'Truss', 'amount_awarded': ''}],
                                  fr=fr, kind=FundingKind.REQUEST)
        self.assertFalse(formset.is_valid())
        self.assertIn("can't go back to pending", str(formset.errors))

    def test_number_must_be_four_digits(self):
        formset = self.post_lines([{'name': 'Gaff', 'number': '45210', 'amount_awarded': '1'}],
                                  fr=make_budget())
        self.assertFalse(formset.is_valid())

    def test_two_lines_cannot_share_a_number(self):
        formset = self.post_lines([
            {'name': 'Gaff', 'number': '4521', 'amount_awarded': '1'},
            {'name': 'Spike', 'number': '4521', 'amount_awarded': '1'},
        ], fr=make_budget())
        self.assertFalse(formset.is_valid())
        self.assertIn('both have the Request ID 4521', str(formset.non_form_errors()))

    def post_categories(self, rows, fr):
        data = {
            'budget_categories-TOTAL_FORMS': str(len(rows)),
            'budget_categories-INITIAL_FORMS': str(sum(1 for row in rows if row.get('id'))),
            'budget_categories-MIN_NUM_FORMS': '0',
            'budget_categories-MAX_NUM_FORMS': '1000',
        }
        for index, row in enumerate(rows):
            for key, value in row.items():
                data['budget_categories-%s-%s' % (index, key)] = value
        return BudgetCategoryFormSet(data, instance=fr, prefix='budget_categories')

    def test_lines_nest_under_saved_and_new_categories_by_key(self):
        fr = make_budget()
        saved = BudgetCategory.objects.create(funding_request=fr, name='Consumables', sort_order=0)
        categories = self.post_categories([
            {'id': str(saved.pk), 'key': str(saved.pk), 'name': 'Consumables', 'sort_order': '1'},
            {'key': 'new-1', 'name': ' Repairs ', 'sort_order': '0'},
        ], fr)
        lines = self.post_lines([
            {'name': 'Gaff', 'number': '4521', 'category_key': str(saved.pk), 'amount_awarded': '1'},
            {'name': 'Spike', 'number': '4522', 'category_key': 'new-1', 'amount_awarded': '1'},
            {'name': 'Misc', 'number': '4524', 'amount_awarded': '1'},
        ], fr=fr)
        self.assertTrue(categories.is_valid(), categories.errors)
        self.assertTrue(lines.is_valid(), lines.errors)
        categories.save()
        lines.assign_categories(categories.by_key())
        lines.save()
        names = dict(fr.line_items.values_list('name', 'category__name'))
        self.assertEqual(names, {'Gaff': 'Consumables', 'Spike': 'Repairs', 'Misc': None})
        self.assertEqual(list(fr.budget_categories.values_list('name', flat=True)),
                         ['Repairs', 'Consumables'])

    def test_a_category_can_be_empty(self):
        fr = make_budget()
        categories = self.post_categories([{'key': 'new-0', 'name': 'Film', 'sort_order': '0'}], fr)
        self.assertTrue(categories.is_valid(), categories.errors)
        categories.save()
        self.assertEqual(fr.budget_categories.get().name, 'Film')

    def test_a_new_category_needs_a_name(self):
        categories = self.post_categories([{'key': 'new-0', 'name': '', 'sort_order': '0'}],
                                          make_budget())
        self.assertFalse(categories.is_valid())
        self.assertIn('needs a name', str(categories.errors))

    def test_two_categories_cannot_share_a_name(self):
        categories = self.post_categories([
            {'key': 'new-0', 'name': 'Film', 'sort_order': '0'},
            {'key': 'new-1', 'name': 'film', 'sort_order': '1'},
        ], make_budget())
        self.assertFalse(categories.is_valid())

    def test_removing_a_category_leaves_its_lines_with_none(self):
        fr = make_budget()
        film = BudgetCategory.objects.create(funding_request=fr, name='Film')
        line = FRLineItem.objects.create(funding_request=fr, name='Rights', number='4541',
                                         category=film, amount_awarded=Decimal('5.00'))
        categories = self.post_categories([
            {'id': str(film.pk), 'key': str(film.pk), 'name': 'Film', 'DELETE': 'on'}], fr)
        self.assertTrue(categories.is_valid(), categories.errors)
        categories.save()
        self.assertFalse(fr.budget_categories.exists())
        line.refresh_from_db()
        self.assertIsNone(line.category)
        self.assertEqual(categories.by_key()[str(film.pk)], None)

    def test_a_requests_lines_have_no_budget_fields(self):
        fr = FundingRequest.objects.create(name='Truss', fiscal_year=YEAR)
        formset = self.post_lines([{'name': 'Truss', 'number': '4521', 'category_key': '7',
                                    'is_projection': 'on', 'amount_awarded': '5'}],
                                  fr=fr, kind=FundingKind.REQUEST)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.assign_categories({'7': BudgetCategory.objects.create(funding_request=fr,
                                                                      name='Rigging')})
        formset.save()
        line = fr.line_items.get()
        self.assertEqual((line.number, line.is_projection, line.category), ('', False, None))


class FundingPageTests(FinanceViewTestCase):

    def setUp(self):
        super(FundingPageTests, self).setUp()
        self.grant('view_subledger', 'view_fundingrequest', 'manage_fundingrequest')

    def test_tab_is_sga_funding_with_one_new_button_on_the_page(self):
        response = self.client.get(reverse('finance:fr-list'))
        content = response.content.decode()
        self.assertIn('>SGA Funding</a>', content)
        # On the page, not in the finance bar every page shares.
        self.assertIn('fin-page-actions', content)
        bar = content.split('fin-topbar-inner')[1].split('fin-page')[0]
        self.assertNotIn('?kind=budget', bar)
        self.assertIn('?kind=request', content)
        self.assertIn('?kind=budget', content)
        self.assertNotIn('New request', content)
        self.assertIn('<span>Budget</span>', content)

    def test_new_button_only_for_those_who_can_add(self):
        self.revoke('manage_fundingrequest')
        response = self.client.get(reverse('finance:fr-list'))
        self.assertNotContains(response, '?kind=request')

    def test_new_button_only_on_the_sga_funding_page(self):
        budget = make_budget()
        for url in (reverse('finance:dashboard'), reverse('finance:fr-detail', args=[budget.pk])):
            self.assertNotContains(self.client.get(url), '?kind=budget')

    def test_budget_box_lists_the_budget(self):
        budget = make_budget()
        FRLineItem.objects.create(funding_request=budget, name='Gaff', number='4521',
                                  amount_requested=Decimal('100.00'),
                                  amount_awarded=Decimal('90.00'))
        response = self.client.get(reverse('finance:fr-list') + '?fy=%s' % YEAR)
        self.assertContains(response, budget.name)
        self.assertContains(response, 'Not deposited yet')
        self.assertContains(response, '$90.00')

    def test_partition_filter_counts_that_sides_lines(self):
        budget = make_budget()
        FRLineItem.objects.create(funding_request=budget, name='Gaff', number='4521',
                                  amount_awarded=Decimal('90.00'))
        FRLineItem.objects.create(funding_request=budget, name='Film', number='4522',
                                  amount_awarded=Decimal('700.00'), is_projection=True)
        response = self.client.get(reverse('finance:fr-list') + '?fy=%s&partition=projection' % YEAR)
        budget_box = response.content.decode().split('<span>Budget</span>')[1]
        self.assertIn('$700.00', budget_box)
        self.assertNotIn('$790.00', budget_box)

    def test_new_budget_starts_named_for_its_year(self):
        response = self.client.get(reverse('finance:fr-new') + '?kind=budget')
        self.assertContains(response, 'New budget')
        self.assertContains(response, 'value="FY%s SGA Budget"' % YY)
        self.assertContains(response, 'is-budget')

    def _budget_post(self, **overrides):
        """ What the page sends for a new budget: two new categories, and lines nested by key. """
        data = {
            'kind': 'budget', 'name': 'FY%s SGA Budget' % YY, 'fiscal_year': str(YEAR),
            'date_submitted': '', 'date_approved': '', 'closed': '', 'notes': '',
            'budget_categories-TOTAL_FORMS': '2', 'budget_categories-INITIAL_FORMS': '0',
            'budget_categories-MIN_NUM_FORMS': '0', 'budget_categories-MAX_NUM_FORMS': '1000',
            'budget_categories-0-key': 'new-0', 'budget_categories-0-name': 'Consumables',
            'budget_categories-0-sort_order': '0',
            'budget_categories-1-key': 'new-1', 'budget_categories-1-name': 'Film',
            'budget_categories-1-sort_order': '1',
            'line_items-TOTAL_FORMS': '3', 'line_items-INITIAL_FORMS': '0',
            'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000',
            'line_items-0-category_key': 'new-0', 'line_items-0-number': '4521',
            'line_items-0-name': 'Gaff tape', 'line_items-0-amount_requested': '400.00',
            'line_items-0-amount_awarded': '300.00', 'line_items-0-sort_order': '0',
            'line_items-1-category_key': 'new-0', 'line_items-1-number': '4522',
            'line_items-1-name': 'Batteries', 'line_items-1-amount_requested': '100.00',
            'line_items-1-amount_awarded': '', 'line_items-1-sort_order': '1',
            'line_items-2-category_key': 'new-1', 'line_items-2-number': '',
            'line_items-2-name': 'Film rights', 'line_items-2-amount_requested': '900.00',
            'line_items-2-amount_awarded': '0', 'line_items-2-is_projection': 'on',
            'line_items-2-sort_order': '0',
        }
        data.update(overrides)
        return data

    def test_create_a_budget_and_see_it_grouped(self):
        response = self.client.post(reverse('finance:fr-new'), self._budget_post())
        self.assertEqual(response.status_code, 302)
        budget = FundingRequest.objects.budgets().get()
        self.assertEqual(budget.line_items.count(), 3)
        self.assertEqual(list(budget.budget_categories.values_list('name', flat=True)),
                         ['Consumables', 'Film'])
        self.assertTrue(budget.line_items.get(name='Film rights').is_projection)

        page = self.client.get(reverse('finance:fr-detail', args=[budget.pk]))
        self.assertTemplateUsed(page, 'finance/budget_detail.html')
        content = page.content.decode()
        self.assertIn('fin-budget-group', content)
        self.assertIn('<code>4521</code>', content)
        self.assertIn('Request ID', content)
        self.assertIn('Pending SGA Approval', content)
        self.assertIn('Denied', content)
        self.assertIn('no Request ID yet', content)
        self.assertNotIn('Project', content.split('id="fin-budget-lines"')[1])
        self.assertIn('SGA deposit', content)
        self.assertNotIn('Report form', content)

    def test_a_second_budget_for_the_year_is_refused_with_a_link(self):
        existing = make_budget()
        response = self.client.post(reverse('finance:fr-new'), self._budget_post())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('finance:fr-edit', args=[existing.pk]))
        self.assertEqual(FundingRequest.objects.budgets().count(), 1)

    def test_rename_a_category_for_every_line(self):
        self.client.post(reverse('finance:fr-new'), self._budget_post())
        budget = FundingRequest.objects.budgets().get()
        consumables = budget.budget_categories.get(name='Consumables')
        film = budget.budget_categories.get(name='Film')
        edit = self.client.get(reverse('finance:fr-edit', args=[budget.pk]))
        self.assertContains(edit, 'budget_categories-TOTAL_FORMS')
        data = {
            'kind': 'budget', 'name': budget.name, 'fiscal_year': str(YEAR),
            'budget_categories-TOTAL_FORMS': '2', 'budget_categories-INITIAL_FORMS': '2',
            'budget_categories-MIN_NUM_FORMS': '0', 'budget_categories-MAX_NUM_FORMS': '1000',
            'budget_categories-0-id': str(consumables.pk), 'budget_categories-0-name': 'Supplies',
            'budget_categories-0-key': str(consumables.pk), 'budget_categories-0-sort_order': '1',
            'budget_categories-1-id': str(film.pk), 'budget_categories-1-name': 'Film',
            'budget_categories-1-key': str(film.pk), 'budget_categories-1-sort_order': '0',
            'line_items-TOTAL_FORMS': '0', 'line_items-INITIAL_FORMS': '0',
            'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000',
        }
        # The lines are left out of the post: Django only reads the rows it is
        # told about, and unlisted saved rows are kept as they are.
        response = self.client.post(reverse('finance:fr-edit', args=[budget.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            sorted(budget.line_items.filter(category__name='Supplies')
                   .values_list('name', flat=True)), ['Batteries', 'Gaff tape'])
        self.assertEqual(list(budget.budget_categories.values_list('name', flat=True)),
                         ['Film', 'Supplies'])

    def test_request_page_shows_requested_and_approved(self):
        fr = FundingRequest.objects.create(name='Truss', fiscal_year=YEAR)
        FRLineItem.objects.create(funding_request=fr, name='Truss',
                                  amount_requested=Decimal('800.00'))
        response = self.client.get(reverse('finance:fr-detail', args=[fr.pk]))
        self.assertContains(response, 'Requested')
        self.assertContains(response, '$800.00')
        self.assertContains(response, 'Pending SGA Approval')

    def test_edit_form_nests_lines_under_their_categories(self):
        self.client.post(reverse('finance:fr-new'), self._budget_post())
        budget = FundingRequest.objects.budgets().get()
        consumables = budget.budget_categories.get(name='Consumables')
        content = self.client.get(reverse('finance:fr-edit', args=[budget.pk])).content.decode()
        block = content.split('data-key="%s"' % consumables.pk)[1].split('</tbody>')[0]
        self.assertIn('value="Gaff tape"', block)
        self.assertIn('value="Batteries"', block)
        self.assertNotIn('value="Film rights"', block)
        # The page offers the empty rows the Add buttons clone.
        self.assertIn('id="fin-category-template"', content)
        self.assertIn('budget_categories-__prefix__-name', content)
        self.assertNotIn('project_tag', content.split('id="fin-fr-lines"')[1])

    def test_move_a_line_and_remove_a_category(self):
        self.client.post(reverse('finance:fr-new'), self._budget_post())
        budget = FundingRequest.objects.budgets().get()
        consumables = budget.budget_categories.get(name='Consumables')
        film = budget.budget_categories.get(name='Film')
        gaff = budget.line_items.get(name='Gaff tape')
        rights = budget.line_items.get(name='Film rights')
        data = {
            'kind': 'budget', 'name': budget.name, 'fiscal_year': str(YEAR),
            'budget_categories-TOTAL_FORMS': '2', 'budget_categories-INITIAL_FORMS': '2',
            'budget_categories-MIN_NUM_FORMS': '0', 'budget_categories-MAX_NUM_FORMS': '1000',
            'budget_categories-0-id': str(consumables.pk), 'budget_categories-0-name': 'Consumables',
            'budget_categories-0-key': str(consumables.pk), 'budget_categories-0-sort_order': '0',
            'budget_categories-1-id': str(film.pk), 'budget_categories-1-name': 'Film',
            'budget_categories-1-key': str(film.pk), 'budget_categories-1-DELETE': 'on',
            'line_items-TOTAL_FORMS': '2', 'line_items-INITIAL_FORMS': '2',
            'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000',
            # Gaff tape is moved out of Consumables; Film's line is left with
            # no category when Film is removed.
            'line_items-0-id': str(gaff.pk), 'line_items-0-name': 'Gaff tape',
            'line_items-0-number': '4521', 'line_items-0-amount_awarded': '300.00',
            'line_items-0-category_key': '', 'line_items-0-sort_order': '0',
            'line_items-1-id': str(rights.pk), 'line_items-1-name': 'Film rights',
            'line_items-1-amount_awarded': '0', 'line_items-1-is_projection': 'on',
            'line_items-1-category_key': '', 'line_items-1-sort_order': '1',
        }
        response = self.client.post(reverse('finance:fr-edit', args=[budget.pk]), data)
        self.assertEqual(response.status_code, 302)
        gaff.refresh_from_db()
        rights.refresh_from_db()
        self.assertIsNone(gaff.category)
        self.assertIsNone(rights.category)
        self.assertEqual(list(budget.budget_categories.values_list('name', flat=True)),
                         ['Consumables'])
        self.assertEqual(budget.line_items.get(name='Batteries').category, consumables)

    def test_report_form_does_not_offer_a_budget(self):
        budget = make_budget()
        response = self.client.get(reverse('finance:report', args=['fr-report-form'])
                                   + '?request=%s' % budget.pk)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Phase 2: money through budgets
# ---------------------------------------------------------------------------

#: A day in the current fiscal year, so a budget for YEAR is the one in reach.
DAY = fiscal_year_bounds(YEAR)[0] + datetime.timedelta(days=75)
MAIN = '226-AG Lens & Light Club'
_ops = iter(range(1000, 9999))


def workday(memo, amount, date=DAY, supplier='Amazon Capital Services, Inc.', journal=False,
            **worktags):
    """
    A Workday line: a supplier invoice, or with ``journal`` SGA's journal
    entry that names nobody.
    """
    tags = {'student_organization': MAIN, 'ledger_account': '71100:Supplies',
            'journal_line_memo': memo}
    tags.update(worktags)
    if journal:
        tags['journal'] = '27090054-JE - Worcester Polytechnic Institute - WPI - 09/30/2026'
        op, supplier = '', ''
    else:
        op = 'Supplier Invoice: 2609%04d-SIN' % next(_ops)
    return WorkdayTransaction.objects.create(
        operational_transaction=op, accounting_date=date, net_amount=Decimal(amount),
        supplier=supplier, memo=memo, worktags_json=tags)


class BudgetWorld(object):
    """ This year's budget: Gaff tape under Consumables, Film rights on Projection. """

    def make_world(self):
        self.budget = make_budget()
        self.consumables = BudgetCategory.objects.create(funding_request=self.budget,
                                                         name='Consumables')
        self.gaff = FRLineItem.objects.create(
            funding_request=self.budget, name='Gaff tape', number='4521',
            category=self.consumables, amount_awarded=Decimal('300.00'),
            lnl_spend_category=category('consumables'))
        self.film = FRLineItem.objects.create(
            funding_request=self.budget, name='Film rights', number='4541', is_projection=True,
            amount_awarded=Decimal('2000.00'))
        self.pending = FRLineItem.objects.create(
            funding_request=self.budget, name='Batteries', number='4522',
            category=self.consumables)
        self.request = FundingRequest.objects.create(name='Truss', reference='F.%s.6' % YY,
                                                     fiscal_year=YEAR)
        self.truss = FRLineItem.objects.create(funding_request=self.request, name='Truss',
                                               amount_awarded=Decimal('500.00'))

    def entry(self, line=None, fund_slug='sga_budget', amount='-50.00', **kwargs):
        txn = workday('Gaff tape', amount)
        return ParsedTransaction(parent_transaction=txn, amount=Decimal(amount),
                                 effective_date=DAY, fund_source=fund(fund_slug),
                                 lnl_spend_category=category('consumables'),
                                 fr_line_target=line, **kwargs)


class ChargingBudgetLinesTests(BudgetWorld, TestCase):
    """ SGA Budget money names a budget line; no other fund may. """

    def setUp(self):
        self.make_world()

    def errors(self, entry):
        with self.assertRaises(ValidationError) as caught:
            entry.full_clean()
        return caught.exception.message_dict

    def test_sga_budget_spending_must_name_a_budget_line(self):
        message = self.errors(self.entry())['fr_line_target'][0]
        self.assertIn('has to name the budget line', message)
        self.assertIn('name the budget under SGA budget', message)

    def test_a_budget_line_is_fine(self):
        self.entry(self.gaff).full_clean()

    def test_sga_budget_cannot_be_charged_to_a_request_line(self):
        message = self.errors(self.entry(self.truss))['fr_line_target'][0]
        self.assertIn('Truss is a funding request line, but SGA Budget is charged to budget lines',
                      message)

    def test_the_request_fund_cannot_be_charged_to_a_budget_line(self):
        message = self.errors(self.entry(self.gaff, fund_slug='sga_fr'))['fr_line_target'][0]
        self.assertIn('4521 Gaff tape is a budget line', message)

    def test_legacy_cannot_be_charged_to_a_budget_line(self):
        message = self.errors(self.entry(self.gaff, fund_slug='legacy'))['fr_line_target'][0]
        self.assertIn('only a fund that draws on budgets', message)

    def test_an_entry_takes_its_budget_lines_side(self):
        entry = self.entry(self.film)
        entry.save()
        self.assertTrue(entry.is_projection)
        entry = self.entry(self.gaff)
        entry.is_projection = True
        entry.save()
        self.assertFalse(entry.is_projection)

    def test_a_deposit_must_name_the_budget(self):
        txn = workday('SGA budget deposit', '5000.00', journal=True)
        deposit = ParsedTransaction(parent_transaction=txn, amount=Decimal('5000.00'),
                                    effective_date=DAY, fund_source=fund('sga_budget'),
                                    non_event_revenue_type=RevenueSource.objects.get(
                                        slug='sga_baseline'))
        self.assertIn('has to name the budget SGA deposited it for',
                      self.errors(deposit)['funding_request'][0])
        deposit.funding_request = self.budget
        deposit.full_clean()
        deposit.save()
        # A budget has no side: the deposit stays on its account's.
        self.assertFalse(deposit.is_projection)
        self.assertEqual(FundingRequest.objects.with_totals().get(pk=self.budget.pk)
                         .total_deposited, Decimal('5000.00'))

    def test_money_returned_to_sga_names_the_budget_and_no_line(self):
        txn = workday('Return unspent budget', '-700.00', journal=True)
        ParsedTransaction(parent_transaction=txn, amount=Decimal('-700.00'), effective_date=DAY,
                          fund_source=fund('sga_budget'), funding_request=self.budget).full_clean()

    def test_a_request_cannot_be_paid_into_the_budget_fund(self):
        txn = workday('Reimbursement', '500.00', journal=True)
        payment = ParsedTransaction(parent_transaction=txn, amount=Decimal('500.00'),
                                    effective_date=DAY, fund_source=fund('sga_budget'),
                                    non_event_revenue_type=RevenueSource.objects.get(
                                        slug='sga_baseline'),
                                    funding_request=self.request)
        self.assertIn('draws on funding requests', self.errors(payment)['funding_request'][0])


class BudgetPickerTests(BudgetWorld, TestCase):
    """ Budget lines are picked the way request lines are, under their categories. """

    def setUp(self):
        self.make_world()

    def form(self, data=None, txn=None):
        txn = txn or workday('Gaff tape', '-50.00')
        return ReconcileForm(data, parent_transaction=txn, prefix='t')

    def test_lines_sit_under_their_budget_and_category(self):
        rendered = str(self.form()['fr_line_target'])
        self.assertIn('label="FY%s · Budget · Consumables"' % YY, rendered)
        self.assertIn('label="FY%s · Budget · No category"' % YY, rendered)
        self.assertIn('4521 Gaff tape — $300.00 left', rendered)
        self.assertIn('data-kind="budget"', rendered)
        self.assertIn('data-kind="request"', rendered)
        self.assertNotIn('Batteries', rendered)
        # Consumables before the lines in no category.
        self.assertLess(rendered.index('Consumables'), rendered.index('No category'))

    def test_boxes_know_their_budget_labels(self):
        form = self.form()
        self.assertIn('data-budget-label="Budget line"', str(form['fr_line_target']))
        self.assertIn('data-budget-label="Budget"', str(form['fr_request']))
        self.assertIn('data-draws-on="budget"', str(form['fund_source']))
        self.assertIn('data-draws-on="request"', str(form['fund_source']))

    def post(self, line, fund_slug, request=None):
        return self.form({'t-fund_source': str(fund(fund_slug).pk),
                          't-lnl_spend_category': str(category('consumables').pk),
                          't-fr_line_target': str(line.pk),
                          't-fr_request': str(request.pk) if request else ''})

    def test_a_budget_line_on_sga_budget_is_accepted(self):
        form = self.post(self.gaff, 'sga_budget', self.budget)
        self.assertTrue(form.is_valid(), form.errors)

    def test_a_request_line_on_sga_budget_is_refused_on_the_line(self):
        form = self.post(self.truss, 'sga_budget')
        self.assertFalse(form.is_valid())
        self.assertIn('charged to budget lines', form.errors['fr_line_target'][0])

    def test_a_line_from_another_budget_or_request_than_the_box_beside_it(self):
        form = self.post(self.gaff, 'sga_budget', self.request)
        self.assertFalse(form.is_valid())
        self.assertIn('or change the request', form.errors['fr_line_target'][0])

    def test_bulk_fund_bar_leaves_out_every_fund_that_draws_on_lines(self):
        slugs = set(BulkActionForm().fields['fund_source'].queryset.values_list('slug', flat=True))
        self.assertNotIn('sga_budget', slugs)
        self.assertNotIn('sga_fr', slugs)
        self.assertIn('legacy', slugs)

    def test_the_sga_payment_box_offers_budgets_too(self):
        txn = workday('SGA budget deposit', '5000.00', journal=True)
        rendered = str(self.form(txn=txn)['funding_request'])
        self.assertIn('FY%s · Budget — not deposited yet' % YY, rendered)
        self.assertIn('data-budget-label="Deposit for budget"', rendered)


class BudgetMemoTests(TestCase):
    """ The house memo with a Request ID where a request number would be. """

    def test_the_full_format(self):
        fields = parse_memo('Velcro restock, consumables, (4521)')
        self.assertEqual((fields.description, fields.line_hint, fields.budget_line,
                          fields.reference),
                         ('Velcro restock', 'consumables', '4521', ''))

    def test_inline_in_brackets_and_bare_last_field(self):
        self.assertEqual(parse_memo('Gaff tape (4521)').budget_line, '4521')
        self.assertEqual(parse_memo('Gaff tape (4521)').description, 'Gaff tape')
        self.assertEqual(parse_memo('Gaff tape, consumables, 4521').budget_line, '4521')

    def test_a_year_in_a_name_is_not_a_line(self):
        fields = parse_memo('Spring Fest 2026')
        self.assertEqual(fields.budget_line, '')
        self.assertEqual(fields.description, 'Spring Fest 2026')

    def test_a_request_number_wins(self):
        fields = parse_memo('Truss, F.27.6, (4521)')
        self.assertEqual(fields.reference, 'F.27.6')
        self.assertEqual(fields.budget_line, '')


class BudgetSuggestionTests(BudgetWorld, TestCase):
    """ The queue fills a budget line in from the memo's Request ID, and from Tracking. """

    def setUp(self):
        self.make_world()

    def test_the_request_id_fills_line_budget_fund_and_category(self):
        found = suggest_all(workday('Velcro restock, consumables, (4521)', '-40.00'))
        self.assertEqual(found['fr_line_target'].value, self.gaff.pk)
        self.assertEqual(found['fr_line_target'].confidence, HIGH)
        self.assertEqual(found['fr_line_target'].source, MEMO)
        self.assertEqual(found['fr_request'].value, self.budget.pk)
        self.assertEqual(found['fund_source'].value, fund('sga_budget').pk)
        self.assertIn('Request ID 4521', found['fund_source'].reason)
        self.assertEqual(found['spend_category'].value, category('consumables').pk)
        self.assertEqual(found['spend_category'].source, AWARD)
        self.assertEqual(found['description'], 'Velcro restock')
        self.assertFalse(found['warning'])

    def test_the_form_is_filled_in(self):
        form = ReconcileForm(parent_transaction=workday('Velcro, consumables, (4521)', '-40.00'),
                             prefix='t')
        self.assertEqual(form.initial['fr_line_target'], self.gaff.pk)
        self.assertEqual(form.initial['fund_source'], fund('sga_budget').pk)

    def test_a_middle_field_that_does_not_fit_the_line_is_flagged(self):
        found = suggest_all(workday('Lamps, lighting, (4521)', '-40.00'))
        self.assertEqual(found['fr_line_target'].value, self.gaff.pk)
        self.assertEqual(found['fr_line_target'].confidence, MEDIUM)
        self.assertIn('but says "lighting" -- check it', found['fr_line_target'].reason)

    def test_a_line_pending_approval_is_not_filled(self):
        found = suggest_all(workday('AA batteries, consumables, (4522)', '-40.00'))
        self.assertIsNone(found['fr_line_target'])
        self.assertIn('pending SGA approval', found['warning'])
        self.assertEqual(found['fr_request'].value, self.budget.pk)

    def test_an_unknown_request_id_on_a_line_tracked_to_the_budget_warns(self):
        found = suggest_all(workday('Tape, consumables, (4599)', '-40.00', tracking='SGA Budget'))
        self.assertIsNone(found['fr_line_target'])
        self.assertEqual(found['warning_label'], 'Unknown Request ID 4599')
        self.assertEqual(found['fund_source'].source, EXPORT)

    def test_an_unknown_number_nothing_else_ties_to_the_budget_is_left_alone(self):
        found = suggest_all(workday('Tape, consumables, (4599)', '-40.00'))
        self.assertNotEqual(found['fund_source'].value, fund('sga_budget').pk)
        self.assertFalse(found['warning'])

    def test_tracked_with_no_request_id_fills_the_budget_and_one_clear_line(self):
        found = suggest_all(workday('Gaff tape restock', '-40.00', tracking='SGA Budget'))
        self.assertEqual(found['fund_source'].value, fund('sga_budget').pk)
        self.assertEqual(found['fr_request'].value, self.budget.pk)
        self.assertEqual(found['fr_line_target'].value, self.gaff.pk)
        self.assertEqual(found['fr_line_target'].confidence, MEDIUM)

    def test_tracked_with_no_words_in_common_fills_no_line(self):
        found = suggest_all(workday('Misc order', '-40.00', tracking='SGA Budget'))
        self.assertEqual(found['fr_request'].value, self.budget.pk)
        self.assertIsNone(found['fr_line_target'])

    def test_tracked_in_a_year_with_no_budget_says_so(self):
        found = suggest_all(workday('Gaff tape', '-40.00', tracking='SGA Budget',
                                    date=DAY + datetime.timedelta(days=366)))
        self.assertEqual(found['warning_label'], 'No FY%s budget' % str(YEAR + 1)[-2:])
        self.assertEqual(found['unknown_budget'], {'fiscal_year': YEAR + 1})

    def test_sgas_deposit_names_the_budget(self):
        found = suggest_all(workday('FY%s budget' % YY, '2300.00', journal=True,
                                    tracking='SGA Budget'))
        self.assertEqual(found['funding_request'].value, self.budget.pk)
        self.assertEqual(found['revenue_source'].value,
                         RevenueSource.objects.get(slug='sga_baseline').pk)
        self.assertEqual(found['fund_source'].value, fund('sga_budget').pk)

    def test_a_suppliers_credit_tracked_to_the_budget_is_not_a_deposit(self):
        found = suggest_all(workday('Credit', '20.00', tracking='SGA Budget'))
        self.assertIsNone(found['funding_request'])

    def test_money_going_back_names_last_years_budget_while_it_has_money_left(self):
        last = make_budget(year=YEAR - 1)
        earlier = DAY - datetime.timedelta(days=365)
        ParsedTransaction.objects.create(
            parent_transaction=workday('Deposit', '900.00', journal=True, date=earlier),
            amount=Decimal('900.00'), effective_date=earlier,
            fund_source=fund('sga_budget'), funding_request=last)
        found = suggest_all(workday('Unspent budget', '-900.00', journal=True,
                                    tracking='SGA Budget'))
        self.assertTrue(found['sga_return'])
        self.assertEqual(found['funding_request'].value, last.pk)
        self.assertIsNone(found['spend_category'])


class BudgetPagesTests(BudgetWorld, FinanceViewTestCase):
    """ The dashboard's burndown and the ledger show budget lines. """

    def setUp(self):
        super(BudgetPagesTests, self).setUp()
        self.grant('view_subledger', 'view_fundingrequest')
        self.make_world()
        self.entry(self.gaff).save()

    def test_the_dashboard_burndown_has_the_budget(self):
        response = self.client.get(reverse('finance:dashboard') + '?fy=%s' % YEAR)
        self.assertContains(response, 'SGA funding burndown')
        self.assertContains(response, self.budget.name)
        self.assertContains(response, '4521 Gaff tape')
        self.assertContains(response, 'Open budget')

    def test_the_side_filter_narrows_a_budget_to_that_sides_lines(self):
        response = self.client.get(reverse('finance:dashboard')
                                   + '?fy=%s&partition=projection' % YEAR)
        content = response.content.decode()
        self.assertIn('Film rights', content)
        self.assertNotIn('4521 Gaff tape', content)
        self.assertNotIn('<strong>Truss</strong>', content)

    def test_the_ledger_names_the_budget_line(self):
        response = self.client.get(reverse('finance:ledger') + '?fy=%s' % YEAR)
        self.assertContains(response, '4521 Gaff tape')
        self.assertContains(response, 'SGA Line')


class LargeBudgetTests(FinanceViewTestCase):
    """ Django refuses more than 1000 fields by default; a budget can run past that. """

    def test_a_hundred_lines_half_on_projection_save(self):
        self.grant('view_fundingrequest', 'manage_fundingrequest')
        budget = make_budget()
        data = {'kind': 'budget', 'name': budget.name, 'fiscal_year': str(YEAR),
                'line_items-TOTAL_FORMS': '100', 'line_items-INITIAL_FORMS': '100',
                'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000'}
        for index in range(100):
            line = FRLineItem.objects.create(funding_request=budget, name='Line %d' % index,
                                             number='%04d' % (5000 + index),
                                             amount_awarded=Decimal('10.00'))
            row = {'id': line.pk, 'funding_request': budget.pk, 'number': line.number,
                   'name': line.name, 'description': '', 'amount_requested': '',
                   'amount_awarded': '12.00', 'lnl_spend_category': '', 'sort_order': index,
                   'category_key': ''}
            if index % 2:
                row['is_projection'] = 'on'
            data.update({'line_items-%d-%s' % (index, key): value for key, value in row.items()})
        self.assertGreater(len(data), 1000)
        response = self.client.post(reverse('finance:fr-edit', args=[budget.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(budget.line_items.filter(amount_awarded=Decimal('12.00')).count(), 100)
        self.assertEqual(budget.line_items.filter(is_projection=True).count(), 50)


class SideLockTests(BudgetWorld, TestCase):
    """ Each entry took its side from its line, so a side with money on it stays put. """

    def setUp(self):
        self.make_world()

    def side_box(self, line, budget=None):
        formset = FRLineItemFormSet(instance=budget or self.budget, kind=FundingKind.BUDGET)
        form = next(form for form in formset.forms if form.instance.pk == line.pk)
        return form.fields['is_projection']

    def test_the_box_locks_once_anything_is_charged(self):
        self.assertFalse(self.side_box(self.gaff).disabled)
        self.entry(self.gaff).save()
        self.assertTrue(self.side_box(self.gaff).disabled)
        self.assertFalse(self.side_box(self.film).disabled)

    def test_an_encumbrance_locks_it_too(self):
        ParsedTransaction.objects.create(
            encumbrance=encumbrance('Order', DAY), amount=Decimal('-25.00'), effective_date=DAY,
            fund_source=fund('sga_budget'), fr_line_target=self.gaff,
            lnl_spend_category=category('consumables'))
        self.assertTrue(self.side_box(self.gaff).disabled)

    def test_a_tick_sent_anyway_changes_nothing(self):
        self.entry(self.gaff).save()
        data = {'line_items-TOTAL_FORMS': '1', 'line_items-INITIAL_FORMS': '1',
                'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000',
                'line_items-0-id': self.gaff.pk, 'line_items-0-name': self.gaff.name,
                'line_items-0-number': '4521', 'line_items-0-amount_awarded': '300.00',
                'line_items-0-is_projection': 'on'}
        formset = FRLineItemFormSet(data, instance=self.budget, kind=FundingKind.BUDGET,
                                    queryset=FRLineItem.objects.filter(pk=self.gaff.pk))
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.gaff.refresh_from_db()
        self.assertFalse(self.gaff.is_projection)

    def test_the_model_refuses_it_for_the_admin(self):
        self.entry(self.gaff).save()
        self.gaff.is_projection = True
        with self.assertRaises(ValidationError) as caught:
            self.gaff.full_clean()
        self.assertIn('is_projection', caught.exception.message_dict)

    def test_a_line_with_nothing_on_it_can_change(self):
        self.film.is_projection = False
        self.film.full_clean()

    def test_a_requests_side_locks_as_well(self):
        self.assertFalse(FundingRequestForm(instance=self.request).fields['is_projection'].disabled)
        self.entry(self.truss, fund_slug='sga_fr').save()
        self.assertTrue(FundingRequestForm(instance=self.request).fields['is_projection'].disabled)
        self.request.is_projection = True
        with self.assertRaises(ValidationError) as caught:
            self.request.full_clean()
        self.assertIn('is_projection', caught.exception.message_dict)


class ClosedBudgetTests(BudgetWorld, TestCase):
    """ A closed budget isn't in the line picker, so the queue says so instead. """

    def setUp(self):
        self.make_world()
        self.budget.closed = True
        self.budget.save()

    def test_a_request_id_on_a_closed_budget_warns_and_fills_no_line(self):
        found = suggest_all(workday('Velcro, consumables, (4521)', '-40.00'))
        self.assertIsNone(found['fr_line_target'])
        self.assertIsNone(found['fr_request'])
        self.assertEqual(found['warning_label'], 'FY%s budget closed' % YY)
        self.assertIn('4521 Gaff tape', found['warning'])
        self.assertIn('is closed', found['warning'])

    def test_tracked_to_a_closed_budget_warns(self):
        found = suggest_all(workday('Tape, consumables', '-40.00', tracking='SGA Budget'))
        self.assertIsNone(found['fr_line_target'])
        self.assertEqual(found['warning_label'], 'FY%s budget closed' % YY)

    def test_sgas_money_still_finds_a_closed_budget(self):
        found = suggest_all(workday('FY%s budget' % YY, '2300.00', journal=True,
                                    tracking='SGA Budget'))
        self.assertEqual(found['funding_request'].value, self.budget.pk)


class MoneyGoingBackInReportsTests(BudgetWorld, TestCase):
    """ Money going back to SGA undoes what it came in as, whichever that was. """

    def setUp(self):
        self.make_world()
        self.baseline = revenue_source('sga_baseline')
        self.reimbursement = revenue_source('sga_fr_reimbursement')
        ParsedTransaction.objects.create(
            parent_transaction=workday('Deposit', '900.00', journal=True),
            amount=Decimal('900.00'), effective_date=DAY, fund_source=fund('sga_budget'),
            funding_request=self.budget, non_event_revenue_type=self.baseline)
        ParsedTransaction.objects.create(
            parent_transaction=workday('Unspent', '-200.00', journal=True),
            amount=Decimal('-200.00'), effective_date=DAY, fund_source=fund('sga_budget'),
            funding_request=self.budget)

    def take_back_from_the_request(self):
        ParsedTransaction.objects.create(
            parent_transaction=workday('Paid twice', '-50.00', journal=True),
            amount=Decimal('-50.00'), effective_date=DAY, fund_source=fund('sga_fr'),
            funding_request=self.request)

    def test_revenue_by_source(self):
        rows = {row['label']: row for row in revenue_by_source(YEAR)}
        self.assertEqual(rows[self.baseline.name]['amount'], Decimal('700.00'))
        self.assertEqual(rows[self.baseline.name]['taken_back'], Decimal('200.00'))
        self.assertNotIn(self.reimbursement.name, rows)

    def test_income_and_spending(self):
        out, taken = _money_in(ParsedTransaction.objects.all())
        self.assertEqual(out[('source', self.baseline.pk)], Decimal('700.00'))
        self.assertEqual(out[('source', self.reimbursement.pk)], Decimal('0.00'))
        self.assertEqual(taken, Decimal('200.00'))

    def test_each_kind_comes_off_its_own_line(self):
        self.take_back_from_the_request()
        rows = {row['label']: row for row in revenue_by_source(YEAR)}
        self.assertEqual(rows[self.baseline.name]['amount'], Decimal('700.00'))
        self.assertEqual(rows[self.reimbursement.name]['amount'], Decimal('-50.00'))
        out, taken = _money_in(ParsedTransaction.objects.all())
        self.assertEqual(out[('source', self.reimbursement.pk)], Decimal('-50.00'))
        self.assertEqual(taken, Decimal('250.00'))


class BudgetDashboardTests(BudgetWorld, FinanceViewTestCase):

    def setUp(self):
        super(BudgetDashboardTests, self).setUp()
        self.grant('view_subledger', 'view_fundingrequest')
        self.make_world()

    def test_the_budget_comes_after_the_requests(self):
        html = self.client.get(reverse('finance:dashboard') + '?fy=%s' % YEAR).content.decode()
        self.assertLess(html.index('<strong>Truss</strong>'),
                        html.index('<strong>%s</strong>' % self.budget.name))

    def test_nothing_decided_is_unknown_rather_than_zero(self):
        pending = make_budget(year=YEAR + 1)
        FRLineItem.objects.create(funding_request=pending, name='Later', number='9001')
        html = self.client.get(reverse('finance:dashboard')
                               + '?fy=%s' % (YEAR + 1)).content.decode()
        figures = html[html.index('fin-fr-figures'):]
        figures = ' '.join(figures[:figures.index('</span>')].split())
        self.assertIn('$0 of ?', figures)


class BudgetWordingTests(BudgetWorld, FinanceViewTestCase):

    def setUp(self):
        super(BudgetWordingTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.make_world()

    def test_the_ledger_download_says_sga_line_and_the_request_id(self):
        entry = self.entry(self.gaff)
        entry.save()
        columns = dict(LEDGER_CSV_COLUMNS)
        self.assertNotIn('FR line', columns)
        self.assertEqual(columns['SGA line'](entry), '4521 Gaff tape')

    def test_a_bulk_refusal_across_years_calls_a_budget_a_budget(self):
        txn = workday('Tape', '-10.00', date=DAY - datetime.timedelta(days=366))
        response = self.client.post(reverse('finance:bulk-reconcile'), {
            'selected': str(txn.pk), 'fund_source': fund('sga_budget').pk,
            'lnl_spend_category': category('consumables').pk,
            'fr_line_target': self.gaff.pk}, follow=True)
        self.assertContains(response, 'is an FY%s budget' % YY)


class UnapprovedLineTests(BudgetWorld, TestCase):
    """ Nothing is charged to a pending or denied line, whichever form saves it. """

    def setUp(self):
        self.make_world()
        self.denied = FRLineItem.objects.create(funding_request=self.budget, name='Denied',
                                                number='4523', amount_awarded=Decimal('0.00'))

    def refused(self, line):
        with self.assertRaises(ValidationError) as caught:
            self.entry(line).full_clean()
        return caught.exception.message_dict['fr_line_target'][0]

    def test_a_pending_line_is_refused(self):
        self.assertIn('4522 Batteries is pending SGA approval', self.refused(self.pending))

    def test_a_denied_line_is_refused(self):
        self.assertIn('4523 Denied is denied by SGA', self.refused(self.denied))

    def test_moving_an_entry_onto_one_is_refused(self):
        entry = self.entry(self.gaff)
        entry.save()
        entry.fr_line_target = self.pending
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_an_entry_already_on_a_line_since_denied_stays_editable(self):
        entry = self.entry(self.gaff)
        entry.save()
        FRLineItem.objects.filter(pk=self.gaff.pk).update(amount_awarded=Decimal('0.00'))
        entry = ParsedTransaction.objects.get(pk=entry.pk)
        entry.description = 'Corrected'
        entry.full_clean()

    def test_a_refund_follows_its_purchase_onto_a_line_since_denied(self):
        purchase = self.entry(self.gaff)
        purchase.save()
        FRLineItem.objects.filter(pk=self.gaff.pk).update(amount_awarded=Decimal('0.00'))
        refund = ParsedTransaction(parent_transaction=workday('Credit', '20.00'),
                                   amount=Decimal('20.00'), effective_date=DAY,
                                   refund_of=ParsedTransaction.objects.get(pk=purchase.pk))
        refund.full_clean()


class RequestIdInAdminTests(BudgetWorld, TestCase):
    """ The admin holds a budget to one Request ID a line, and swapping two is fine. """

    def setUp(self):
        self.make_world()
        self.request_ = RequestFactory().post('/')
        self.request_.user = get_user_model().objects.create_superuser(
            'budget-admin', 'budget-admin@example.com', 'x')

    def formset(self, parent, rows):
        request = self.request_
        request._finance_admin_parent = parent
        formset_class = FRLineItemInline(FundingRequest, admin.site).get_formset(request, parent)
        data = {'line_items-TOTAL_FORMS': str(len(rows)),
                'line_items-INITIAL_FORMS': str(sum(1 for row in rows if row.get('id'))),
                'line_items-MIN_NUM_FORMS': '0', 'line_items-MAX_NUM_FORMS': '1000'}
        for index, row in enumerate(rows):
            data.update({'line_items-%d-%s' % (index, key): value for key, value in row.items()})
        return formset_class(data, instance=parent)

    def line(self, line, number):
        return {'id': line.pk, 'name': line.name, 'number': number, 'sort_order': '0',
                'funding_request': line.funding_request_id}

    def test_a_second_line_with_the_same_id_is_refused(self):
        lines = FRLineItem.objects.filter(funding_request=self.budget).order_by('pk')
        rows = [self.line(lines[0], '4521'), self.line(lines[1], '4541'),
                self.line(lines[2], '4522'), {'name': 'Twin', 'number': '4521', 'sort_order': '0'}]
        formset = self.formset(self.budget, rows)
        self.assertFalse(formset.is_valid())
        self.assertIn('both have the Request ID 4521', str(formset.non_form_errors()))

    def test_swapping_two_ids_is_allowed(self):
        lines = FRLineItem.objects.filter(funding_request=self.budget).order_by('pk')
        rows = [self.line(lines[0], '4541'), self.line(lines[1], '4521'),
                self.line(lines[2], '4522')]
        formset = self.formset(self.budget, rows)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.gaff.refresh_from_db()
        self.assertEqual(self.gaff.number, '4541')

    def test_a_requests_lines_are_left_alone(self):
        formset = self.formset(self.request, [
            {'name': 'A', 'number': '', 'sort_order': '0'},
            {'name': 'B', 'number': '', 'sort_order': '0'}])
        self.assertTrue(formset.is_valid(), formset.errors)


class DeniedLineBarTests(BudgetWorld, FinanceViewTestCase):
    """ A denied line has nothing to burn down, so it has no bar, least of all a red one. """

    def setUp(self):
        super(DeniedLineBarTests, self).setUp()
        self.grant('view_subledger', 'view_fundingrequest')
        self.make_world()

    def test_the_dashboard_and_the_requests_page(self):
        FRLineItem.objects.filter(funding_request=self.request).update(
            amount_awarded=Decimal('0.00'))
        red = 'progress-bar-danger" style="width:100%"'
        dashboard = self.client.get(reverse('finance:dashboard') + '?fy=%s' % YEAR)
        lines = dashboard.content.decode().split('fin-fr-line-head')
        self.assertNotIn(red, next(chunk for chunk in lines[1:] if '>Truss<' in chunk))
        page = self.client.get(reverse('finance:fr-detail', args=[self.request.pk]))
        self.assertContains(page, 'Denied')
        self.assertNotContains(page, 'width:100%')

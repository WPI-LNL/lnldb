"""
The rules each form enforces, and the ones it refuses to let a formset break.

``test_forms`` covers what the fields offer and what gets filled in. This
module covers the arbitration: the split formset's balance mandate, the
direction split that makes revenue and expense routing structurally exclusive,
and the validators that only fire on input nobody would type on purpose.

The split rules matter most. A formset is the one place several rows are
written from one submission, so a rule that lives only in ``Model.clean()`` can
be satisfied row by row and still leave the set as a whole wrong -- a purchase
allocated to $900 of its $1,000, or half an expense turned into revenue.
"""
import datetime
from decimal import Decimal

from django.test import TestCase

from finance.forms import (BulkReconcileForm, EncumbranceForm, FilterBarForm, FRLineItemForm,
                           ReconcileForm, SplitFormSet, WorkdayCSVUploadForm)
from finance.models import FRLineItem, FundingRequest, WorkdayTransaction
from finance.tests.util import category, fund

SEP = datetime.date(2025, 9, 15)


def bank(op='OT-F1', amount='-1000.00'):
    return WorkdayTransaction.objects.create(
        operational_transaction=op, accounting_date=SEP, net_amount=Decimal(amount),
        supplier='B&H Photo',
        worktags_json={'ledger_account': '71100:Supplies', 'spend_category': 'Supplies'})


class SplitFormSetTests(TestCase):
    """
    The split mandate: the slices sum to the bank line, to the cent.

    This is the server-side half of the disabled Save button in the modal, and
    the only half that holds when the script does not run.
    """

    def setUp(self):
        self.txn = bank(amount='-1000.00')

    def _formset(self, *amounts, **kwargs):
        data = {
            'slices-TOTAL_FORMS': str(len(amounts)),
            'slices-INITIAL_FORMS': '0',
            'slices-MIN_NUM_FORMS': '0',
            'slices-MAX_NUM_FORMS': '1000',
        }
        for index, amount in enumerate(amounts):
            data.update({
                'slices-%s-amount' % index: amount,
                'slices-%s-description' % index: 'Slice %s' % index,
                'slices-%s-fund_source' % index: str(fund('sga_budget').pk),
                'slices-%s-lnl_spend_category' % index: str(category('consumables').pk),
            })
        data.update(kwargs)
        return SplitFormSet(data, instance=self.txn, parent_transaction=self.txn)

    def test_a_balancing_split_is_valid(self):
        self.assertTrue(self._formset('-600.00', '-400.00').is_valid())

    def test_an_under_allocated_split_names_the_remainder(self):
        formset = self._formset('-600.00', '-300.00')
        self.assertFalse(formset.is_valid())
        self.assertIn('100.00', ' '.join(formset.non_form_errors()))

    def test_an_over_allocated_split_is_refused_too(self):
        formset = self._formset('-600.00', '-600.00')
        self.assertFalse(formset.is_valid())
        self.assertIn('still unallocated', ' '.join(formset.non_form_errors()))

    def test_a_split_with_no_live_rows_is_refused(self):
        """ Deleting every slice is not a way to reconcile a line to nothing. """
        formset = self._formset()
        self.assertFalse(formset.is_valid())
        self.assertIn('at least one allocation slice', ' '.join(formset.non_form_errors()))

    def test_deleted_rows_do_not_count_toward_the_total(self):
        formset = self._formset('-1000.00', '-999.00',
                                **{'slices-1-DELETE': 'on'})
        self.assertTrue(formset.is_valid(), formset.non_form_errors())

    def test_a_slice_cannot_flip_the_direction_of_the_line(self):
        """
        Splitting an expense into an expense and a credit would let money be
        invented: the halves would still sum to the whole.
        """
        from finance.models import RevenueSource
        # The flipped slice has to be valid *on its own* to reach this rule --
        # otherwise the form-level error fires first and the formset stops
        # before its own clean(). That is the case worth guarding: a
        # well-formed revenue slice hidden inside an expense.
        formset = self._formset(
            '-1400.00', '400.00',
            **{'slices-1-fund_source': '', 'slices-1-lnl_spend_category': '',
               'slices-1-non_event_revenue_type': str(RevenueSource.objects.active().first().pk)})
        self.assertFalse(formset.is_valid())
        self.assertIn('same direction', ' '.join(formset.non_form_errors()))

    def test_a_revenue_line_splits_into_revenue(self):
        self.txn = bank(op='OT-F2', amount='700.00')
        data = {
            'slices-TOTAL_FORMS': '2',
            'slices-INITIAL_FORMS': '0',
            'slices-MIN_NUM_FORMS': '0',
            'slices-MAX_NUM_FORMS': '1000',
        }
        from finance.models import RevenueSource
        source = RevenueSource.objects.active().first()
        for index, amount in enumerate(('400.00', '300.00')):
            data.update({
                'slices-%s-amount' % index: amount,
                'slices-%s-description' % index: 'Slice %s' % index,
                'slices-%s-non_event_revenue_type' % index: str(source.pk),
            })
        formset = SplitFormSet(data, instance=self.txn, parent_transaction=self.txn)
        self.assertTrue(formset.is_valid(), formset.errors or formset.non_form_errors())

    def test_an_untouched_blank_row_is_ignored(self):
        """ The modal ships two spare rows; leaving one alone is the normal case. """
        formset = self._formset('-1000.00', '',
                                **{'slices-1-description': '',
                                   'slices-1-fund_source': '',
                                   'slices-1-lnl_spend_category': ''})
        self.assertTrue(formset.is_valid(),
                        formset.errors or formset.non_form_errors())

    def test_field_errors_stop_the_balance_check_from_also_firing(self):
        """ One problem, one message: the balance is meaningless until it parses. """
        formset = self._formset('not a number')
        self.assertFalse(formset.is_valid())
        self.assertEqual(formset.non_form_errors(), [])


class DirectionRuleTests(TestCase):
    """
    Revenue routing and expense routing are mutually exclusive, and the forms
    make that structural by removing the fields rather than validating them.
    """

    def test_an_expense_form_has_no_revenue_type(self):
        form = ReconcileForm(parent_transaction=bank(amount='-500.00'), prefix='t')
        self.assertNotIn('non_event_revenue_type', form.fields)
        self.assertIn('fund_source', form.fields)

    def test_a_revenue_form_has_no_fund_or_category(self):
        form = ReconcileForm(parent_transaction=bank(op='OT-F3', amount='500.00'), prefix='t')
        self.assertNotIn('fund_source', form.fields)
        self.assertNotIn('lnl_spend_category', form.fields)
        self.assertIn('non_event_revenue_type', form.fields)

    def test_an_event_may_be_named_on_either_side(self):
        """
        On revenue it means "this is what the show earned"; on an expense, "this
        cost was incurred for it" -- a sub-rental billed straight through.
        """
        expense = ReconcileForm(parent_transaction=bank(op='OT-F4', amount='-500.00'),
                                prefix='t')
        revenue = ReconcileForm(parent_transaction=bank(op='OT-F5', amount='500.00'),
                                prefix='t')
        self.assertIn('linked_event', expense.fields)
        self.assertIn('linked_event', revenue.fields)
        self.assertEqual(expense.fields['linked_event'].label, 'Incurred for event')

    def test_the_cross_year_tick_box_goes_with_the_picker_it_widens(self):
        revenue = ReconcileForm(parent_transaction=bank(op='OT-F6', amount='500.00'),
                                prefix='t')
        self.assertNotIn('allow_cross_year_fr', revenue.fields)

    def test_an_encumbrance_is_always_an_expense(self):
        """ It reserves money for a purchase; there is no revenue reading. """
        form = EncumbranceForm()
        self.assertNotIn('non_event_revenue_type', form.fields)
        self.assertIn('fund_source', form.fields)

    def test_an_encumbrance_normalises_the_sign(self):
        form = EncumbranceForm(data={
            'amount': '75.00', 'effective_date': '2025-09-15',
            'description': 'Gaff tape run', 'audit_explanation': 'Restocking',
            'fund_source': str(fund('sga_budget').pk),
            'lnl_spend_category': str(category('consumables').pk)})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['amount'], Decimal('-75.00'))

    def test_a_negative_encumbrance_stays_negative(self):
        form = EncumbranceForm(data={
            'amount': '-75.00', 'effective_date': '2025-09-15',
            'description': 'Gaff tape run', 'audit_explanation': 'Restocking',
            'fund_source': str(fund('sga_budget').pk),
            'lnl_spend_category': str(category('consumables').pk)})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['amount'], Decimal('-75.00'))


class FundAndFundingRequestTests(TestCase):
    """
    A fund drawing on a specific award has to name the line it burns down, and
    no other fund may name one. Said field by field rather than as a model error.
    """

    def setUp(self):
        self.txn = bank(op='OT-F7', amount='-500.00')
        self.request = FundingRequest.objects.create(
            name='A Term Films', reference='F.26.6', fiscal_year=2026)
        self.line = FRLineItem.objects.create(
            funding_request=self.request, name='Film Rights',
            amount_awarded=Decimal('5000.00'))

    def _form(self, **data):
        payload = {'fund_source': str(fund('sga_budget').pk),
                   'lnl_spend_category': str(category('consumables').pk)}
        payload.update(data)
        return ReconcileForm(payload, parent_transaction=self.txn, prefix='t')

    def test_award_money_must_name_its_line(self):
        form = self._form(**{'t-fund_source': str(fund('sga_fr').pk)})
        form = ReconcileForm({'t-fund_source': str(fund('sga_fr').pk),
                              't-lnl_spend_category': str(category('consumables').pk)},
                             parent_transaction=self.txn, prefix='t')
        self.assertFalse(form.is_valid())
        self.assertIn('fr_line_target', form.errors)

    def test_another_fund_may_not_name_a_line(self):
        form = ReconcileForm({'t-fund_source': str(fund('sga_budget').pk),
                              't-lnl_spend_category': str(category('consumables').pk),
                              't-fr_line_target': str(self.line.pk)},
                             parent_transaction=self.txn, prefix='t')
        self.assertFalse(form.is_valid())
        self.assertIn('fr_line_target', form.errors)

    def test_crossing_fiscal_years_needs_the_tick_box(self):
        """ Legal now and then, far more often a mistake, and it corrupts two years. """
        old = FundingRequest.objects.create(name='Last Year', reference='F.25.1',
                                            fiscal_year=2025)
        old_line = FRLineItem.objects.create(funding_request=old, name='Rights',
                                             amount_awarded=Decimal('100.00'))
        form = ReconcileForm({'t-fund_source': str(fund('sga_fr').pk),
                              't-lnl_spend_category': str(category('consumables').pk),
                              't-fr_line_target': str(old_line.pk)},
                             parent_transaction=self.txn, prefix='t')
        self.assertFalse(form.is_valid())
        self.assertIn('FY2025', ' '.join(form.errors['fr_line_target']))

    def test_ticking_the_box_allows_it(self):
        old = FundingRequest.objects.create(name='Last Year', reference='F.25.1',
                                            fiscal_year=2025)
        old_line = FRLineItem.objects.create(funding_request=old, name='Rights',
                                             amount_awarded=Decimal('900.00'))
        form = ReconcileForm({'t-fund_source': str(fund('sga_fr').pk),
                              't-lnl_spend_category': str(category('consumables').pk),
                              't-fr_line_target': str(old_line.pk),
                              't-allow_cross_year_fr': 'on'},
                             parent_transaction=self.txn, prefix='t')
        self.assertTrue(form.is_valid(), form.errors)


class FRLineItemFormTests(TestCase):
    """ The award lines entered when a funding request is recorded. """

    def setUp(self):
        self.request = FundingRequest.objects.create(name='A Term Films', fiscal_year=2026)

    def test_a_line_is_accepted(self):
        form = FRLineItemForm({'name': 'Film Rights', 'amount_awarded': '500.00',
                               'sort_order': '0'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_a_negative_award_is_refused(self):
        """ An award is money granted; a negative one is a typed minus sign. """
        form = FRLineItemForm({'name': 'Film Rights', 'amount_awarded': '-500.00',
                               'sort_order': '0'})
        self.assertFalse(form.is_valid())
        self.assertIn('amount_awarded', form.errors)


class UploadFormTests(TestCase):
    """ What is refused before the importer is asked to read anything. """

    def _file(self, name, size=10):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(name, b'x' * size, content_type='text/csv')

    def test_the_formats_workday_exports_are_accepted(self):
        for name in ('journal.csv', 'journal.tsv', 'journal.txt', 'journal.xlsx',
                     'journal.xlsm'):
            form = WorkdayCSVUploadForm({}, {'csv_file': self._file(name)})
            self.assertTrue(form.is_valid(), name)

    def test_another_kind_of_file_is_named_rather_than_parsed(self):
        form = WorkdayCSVUploadForm({}, {'csv_file': self._file('report.docx')})
        self.assertFalse(form.is_valid())
        self.assertIn('neither a CSV nor an .xlsx', ' '.join(form.errors['csv_file']))

    def test_an_implausibly_large_file_is_refused(self):
        """ A journal export is tens of kilobytes; 15 MB is a different file. """
        form = WorkdayCSVUploadForm({}, {'csv_file': self._file('journal.csv',
                                                                size=16 * 1024 * 1024)})
        self.assertFalse(form.is_valid())
        self.assertIn('larger than 15 MB', ' '.join(form.errors['csv_file']))


class FilterBarFormTests(TestCase):
    """ The persistent top bar, whose two controls every page reads. """

    def test_the_partition_flag_is_a_tri_state(self):
        for value, expected in (('projection', True), ('event', False), ('all', None)):
            form = FilterBarForm({'partition': value})
            self.assertEqual(form.partition_flag, expected, value)

    def test_an_unsubmitted_form_has_no_opinion(self):
        self.assertIsNone(FilterBarForm().partition_flag)
        self.assertIsNone(FilterBarForm().selected_fiscal_year)

    def test_the_year_comes_back_as_an_integer(self):
        form = FilterBarForm({'fiscal_year': '2026', 'partition': 'all'})
        self.assertEqual(form.selected_fiscal_year, 2026)

    def test_all_years_is_no_year(self):
        form = FilterBarForm({'fiscal_year': '', 'partition': 'all'})
        self.assertIsNone(form.selected_fiscal_year)


class BulkReconcileFormTests(TestCase):
    """ The queue's bulk bar. Expense routing only; see the view for why. """

    def test_a_fund_is_required(self):
        form = BulkReconcileForm({'selected': '1'})
        self.assertFalse(form.is_valid())
        self.assertIn('fund_source', form.errors)

    def test_the_category_and_project_are_optional(self):
        form = BulkReconcileForm({'selected': '1',
                                  'fund_source': str(fund('sga_budget').pk)})
        self.assertTrue(form.is_valid(), form.errors)

    def test_the_selection_is_parsed_into_ids(self):
        form = BulkReconcileForm({'selected': '3,1,notanid,,2',
                                  'fund_source': str(fund('sga_budget').pk)})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.selected_ids, [3, 1, 2])

    def test_an_empty_selection_parses_to_nothing(self):
        form = BulkReconcileForm({'selected': '',
                                  'fund_source': str(fund('sga_budget').pk)})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.selected_ids, [])

    def test_every_control_carries_the_bootstrap_class(self):
        """
        The bar is dark and sets a colour; a control that inherits it keeps its
        own light background and comes out white on white.
        """
        form = BulkReconcileForm()
        for name, field in form.fields.items():
            if name == 'selected':
                continue
            self.assertIn('form-control', field.widget.attrs.get('class', ''), name)

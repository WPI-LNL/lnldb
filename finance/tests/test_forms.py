import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from events.tests.generators import Event2019Factory
from finance.forms import (AllocationForm, EncumbranceForm, FRLineItemForm, ProjectTagForm,
                           ReconcileForm, SplitLineForm)
from finance.models import (FRLineItem, FundingRequest, FundSource, ParsedTransaction,
                            ProjectTag, SpendCategory, SuggestionRule, WorkdayTransaction,
                            fund_source_for_workday_fund, reset_finance_cache)
from finance.suggestions import suggest_spend_category, unmapped_spend_categories
from finance.tests.util import category, fund


def bank(op='OT-F1', amount='-500.00', org='226-AG Lens & Light Club',
         line_memo='Gaff tape order', worktags=None):
    tags = {'ledger_account': '71100:Supplies', 'spend_category': 'Supplies'}
    if org:
        tags['student_organization'] = org
    if line_memo:
        tags['journal_line_memo'] = line_memo
    # Passed in at creation rather than assigned afterwards: a saved
    # WorkdayTransaction is immutable, which is the point of the class.
    tags.update(worktags or {})
    worktags = tags
    return WorkdayTransaction.objects.create(
        operational_transaction=op, accounting_date=datetime.date(2025, 9, 15),
        net_amount=Decimal(amount), supplier='B&H Photo',
        memo='%s — September purchases' % line_memo if line_memo else '',
        worktags_json=worktags)


class FundSourceChoiceTests(TestCase):
    def test_only_the_active_rows_are_offered(self):
        form = ReconcileForm(parent_transaction=bank(), prefix='t')
        labels = [str(label) for value, label in form.fields['fund_source'].choices if value]
        self.assertEqual(labels, ['SGA Funding Request', 'SGA Budget', 'Legacy'])

    def test_seeded_rows(self):
        self.assertEqual([f.name for f in FundSource.objects.active()],
                         ['SGA Funding Request', 'SGA Budget', 'Legacy'])

    def test_retiring_a_row_removes_it_from_the_form(self):
        """ The whole point of the table: no deploy needed to change the list. """
        FundSource.objects.filter(slug='legacy').update(is_active=False)
        form = ReconcileForm(parent_transaction=bank(op='OT-RETIRE'), prefix='t')
        labels = [str(label) for value, label in form.fields['fund_source'].choices if value]
        self.assertNotIn('Legacy', labels)

    def test_a_new_row_appears_without_a_deploy(self):
        FundSource.objects.create(name='Departmental Transfer', slug='dept_transfer',
                                  sort_order=9)
        form = ReconcileForm(parent_transaction=bank(op='OT-NEW'), prefix='t')
        labels = [str(label) for value, label in form.fields['fund_source'].choices if value]
        self.assertIn('Departmental Transfer', labels)


class SpendCategoryChoiceTests(TestCase):
    def test_seed_matches_the_requested_list(self):
        """
        The eighteen categories LNL asked for, in the order asked for. 'Event
        Expense' follows them: it was added later for costs billed straight to
        an event, and is filled in automatically rather than chosen.
        """
        self.assertEqual([c.name for c in SpendCategory.objects.active()], [
            'Repairs', 'Consumables', 'New Stuff', 'Radio Things', 'Booth Expenses',
            'Shipping', 'Printing', 'Marketing', 'Spotify', 'Slack', 'Food', 'Merch',
            'Safety', 'Gifts', 'Adjustments', 'Chain Motor Inspection',
            'LNL Internal Events', 'Other', 'Event Expense'])

    def test_exactly_one_category_is_the_event_pass_through(self):
        flagged = SpendCategory.objects.filter(is_event_passthrough=True)
        self.assertEqual([c.name for c in flagged], ['Event Expense'])

    def test_every_category_carries_a_chart_colour(self):
        for c in SpendCategory.objects.all():
            self.assertRegex(c.color, r'^#[0-9A-Fa-f]{6}$', c.name)

    def test_a_category_can_be_added_from_data_alone(self):
        SpendCategory.objects.create(name='Rigging Hardware', slug='rigging',
                                     color='#123456', sort_order=99)
        self.assertIn('Rigging Hardware',
                      [c.name for c in SpendCategory.objects.active()])


class RequiredFieldTests(TestCase):
    """ Required on the expense side only -- revenue may not carry these at all. """

    def test_reconcile_requires_a_fund_on_expenses(self):
        txn = bank(op='OT-R1', amount='-500.00')
        form = ReconcileForm(data={}, parent_transaction=txn, prefix='t')
        self.assertFalse(form.is_valid())
        self.assertIn('fund_source', form.errors)

    def test_reconcile_does_not_demand_a_fund_on_revenue(self):
        txn = bank(op='OT-R2', amount='500.00')
        form = ReconcileForm(parent_transaction=txn, prefix='t')
        # The field is not even rendered for revenue.
        self.assertNotIn('fund_source', form.fields)

    def test_entry_page_requires_the_routing(self):
        """
        Where the money came from and what it was for are structural: reports
        group by them, so a blank makes the line uncountable.
        """
        txn = bank(op='OT-R3')
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), effective_date=txn.accounting_date)
        form = AllocationForm(instance=entry, parent_transaction=txn)
        for name in ('fund_source', 'lnl_spend_category'):
            self.assertTrue(form.fields[name].required, '%s should be required' % name)

    def test_entry_page_does_not_demand_paperwork(self):
        """
        The audit explanation and the receipt are asked for, not insisted on.

        Requiring them made this page unusable for its commonest job: fixing a
        spend category chosen wrong three weeks ago meant first producing a
        receipt for somebody else's purchase. A line missing its paperwork is
        one to chase, not one to lock.
        """
        txn = bank(op='OT-R4')
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), effective_date=txn.accounting_date)
        form = AllocationForm(instance=entry, parent_transaction=txn)
        self.assertFalse(form.fields['audit_explanation'].required)
        self.assertFalse(form.fields['receipt_file'].required)

    def test_entry_page_saves_an_expense_with_neither(self):
        txn = bank(op='OT-R4b')
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), effective_date=txn.accounting_date)
        form = AllocationForm(data={
            'amount': '-500.00', 'effective_date': '2025-09-15', 'description': 'Gaff tape',
            'fund_source': fund('sga_budget').pk,
            'lnl_spend_category': category('consumables').pk,
        }, instance=entry, parent_transaction=txn)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.audit_explanation, '')
        self.assertFalse(saved.receipt_file)

    def test_entry_page_accepts_a_complete_expense(self):
        txn = bank(op='OT-R5')
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), effective_date=txn.accounting_date)
        form = AllocationForm(
            data={
                'amount': '-500.00', 'effective_date': '2025-09-15', 'description': 'Gaff tape',
                'fund_source': fund('sga_budget').pk,
                'lnl_spend_category': category('consumables').pk,
                'audit_explanation': 'Restocking the shop.',
            },
            files={'receipt_file': SimpleUploadedFile('receipt.pdf', b'%PDF-1.4 fake',
                                                      content_type='application/pdf')},
            instance=entry, parent_transaction=txn)
        self.assertTrue(form.is_valid(), form.errors)

    def test_an_existing_receipt_satisfies_the_requirement(self):
        """ Editing an entry that already has proof must not demand a re-upload. """
        txn = bank(op='OT-R6')
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), effective_date=txn.accounting_date,
            audit_explanation='Restocking.',
            receipt_file=SimpleUploadedFile('old.pdf', b'%PDF-1.4 old',
                                            content_type='application/pdf'))
        form = AllocationForm(data={
            'amount': '-500.00', 'effective_date': '2025-09-15', 'description': 'Gaff tape',
            'fund_source': fund('sga_budget').pk,
            'lnl_spend_category': category('consumables').pk,
            'audit_explanation': 'Restocking.',
        }, instance=entry, parent_transaction=txn)
        self.assertTrue(form.is_valid(), form.errors)

    def test_encumbrance_needs_routing_but_not_a_receipt(self):
        form = EncumbranceForm()
        self.assertTrue(form.fields['fund_source'].required)
        self.assertTrue(form.fields['lnl_spend_category'].required)
        self.assertFalse(form.fields['receipt_file'].required)


class DescriptionSeedTests(TestCase):
    def test_new_slice_is_prefilled_from_the_journal_line_memo(self):
        """ Forms that render Description pre-fill it; the queue sets it on save. """
        txn = bank(op='OT-D1', line_memo='NEL26 fixture order')
        form = AllocationForm(parent_transaction=txn)
        self.assertEqual(form.initial.get('description'), 'NEL26 fixture order')

    def test_reconcile_saves_the_journal_line_memo_as_the_description(self):
        txn = bank(op='OT-D2', line_memo='NEL26 fixture order')
        form = ReconcileForm(data={'t-fund_source': fund('sga_budget').pk}, prefix='t',
                             parent_transaction=txn)
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.description, 'NEL26 fixture order')

    def test_an_existing_slice_is_never_overwritten(self):
        txn = bank(op='OT-D3', line_memo='NEL26 fixture order')
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=txn.net_amount, fund_source=fund('sga_budget'),
            description='Hand-written label', effective_date=txn.accounting_date)
        form = AllocationForm(instance=entry, parent_transaction=txn)
        self.assertNotEqual(form.initial.get('description'), 'NEL26 fixture order')


class ProjectDropdownIndentationTests(TestCase):
    def setUp(self):
        self.parent = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        self.child = ProjectTag.objects.create(name='D60 Lustr Fixtures', code='D60-LUSTR',
                                               parent=self.parent)

    def _labels(self, field):
        return [str(label) for value, label in field.choices if value]

    def test_every_project_selector_is_indented(self):
        txn = bank(op='OT-P1')
        forms_to_check = [
            ('ReconcileForm', ReconcileForm(parent_transaction=txn, prefix='t'), 'project_tag'),
            ('EncumbranceForm', EncumbranceForm(), 'project_tag'),
            ('FRLineItemForm', FRLineItemForm(), 'project_tag'),
            ('ProjectTagForm.parent', ProjectTagForm(), 'parent'),
        ]
        for name, form, field_name in forms_to_check:
            labels = self._labels(form.fields[field_name])
            self.assertIn('NEL26 — New Equipment List 2026', labels, name)
            nested = [label for label in labels if '└' in label]
            self.assertEqual(len(nested), 1, '%s should nest exactly one child' % name)
            self.assertTrue(nested[0].startswith(' '), '%s: %r' % (name, nested[0]))

    def test_children_follow_their_parent_in_tree_order(self):
        labels = self._labels(ReconcileForm(parent_transaction=bank(op='OT-P2'),
                                            prefix='t').fields['project_tag'])
        self.assertLess(labels.index('NEL26 — New Equipment List 2026'),
                        [i for i, l in enumerate(labels) if '└' in l][0])

    def test_bulk_action_project_picker_is_indented(self):
        from finance.forms import BulkActionForm
        labels = self._labels(BulkActionForm().fields['project_tag'])
        self.assertTrue(any('└' in label for label in labels))


class FundingRequestLineTests(TestCase):
    """ Line items carry a description and are not capped at three. """

    def _post(self, rows, fr=None):
        from finance.forms import FRLineItemFormSet
        data = {
            'line_items-TOTAL_FORMS': str(len(rows)),
            'line_items-INITIAL_FORMS': str(fr.line_items.count() if fr else 0),
            'line_items-MIN_NUM_FORMS': '0',
            'line_items-MAX_NUM_FORMS': '1000',
        }
        for index, row in enumerate(rows):
            for key, value in row.items():
                data['line_items-%s-%s' % (index, key)] = value
        return FRLineItemFormSet(data, instance=fr)

    def test_description_is_on_the_form(self):
        self.assertIn('description', FRLineItemForm().fields)

    def test_description_is_optional(self):
        from finance.models import FundingRequest
        fr = FundingRequest.objects.create(name='NEL26 Grant')
        formset = self._post([{'name': 'Fixtures', 'amount_awarded': '1000.00'}], fr=fr)
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_description_is_saved(self):
        from finance.models import FundingRequest
        fr = FundingRequest.objects.create(name='NEL26 Grant')
        formset = self._post([{
            'name': 'Fixtures', 'amount_awarded': '9000.00',
            'description': 'Eight D60 Lustr fixtures to replace the 2009 Source Fours.',
        }], fr=fr)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        line = fr.line_items.get()
        self.assertEqual(line.description,
                         'Eight D60 Lustr fixtures to replace the 2009 Source Fours.')

    def test_more_than_three_lines_can_be_submitted(self):
        """ The old form rendered three blanks; nothing should cap the count. """
        from finance.models import FundingRequest
        fr = FundingRequest.objects.create(name='Big Grant')
        rows = [{'name': 'Line %s' % n, 'amount_awarded': '100.00',
                 'description': 'Covers item %s' % n} for n in range(7)]
        formset = self._post(rows, fr=fr)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(fr.line_items.count(), 7)
        self.assertEqual(fr.total_awarded, Decimal('700.00'))

    def test_blank_rows_are_ignored(self):
        from finance.models import FundingRequest
        fr = FundingRequest.objects.create(name='Sparse Grant')
        formset = self._post([
            {'name': 'Real line', 'amount_awarded': '50.00'},
            {'name': '', 'amount_awarded': ''},
            {'name': '', 'amount_awarded': ''},
        ], fr=fr)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(fr.line_items.count(), 1)

    def test_order_is_assigned_from_row_position(self):
        """ Nobody should have to hand-number lines to save them. """
        from finance.models import FundingRequest
        fr = FundingRequest.objects.create(name='Ordered Grant')
        formset = self._post([
            {'name': 'First', 'amount_awarded': '10.00'},
            {'name': 'Second', 'amount_awarded': '20.00'},
            {'name': 'Third', 'amount_awarded': '30.00'},
        ], fr=fr)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(
            [(line.name, line.sort_order) for line in fr.line_items.order_by('sort_order')],
            [('First', 0), ('Second', 1), ('Third', 2)])

    def test_an_explicit_order_is_respected(self):
        from finance.models import FundingRequest
        fr = FundingRequest.objects.create(name='Manual Order')
        formset = self._post([
            {'name': 'Last', 'amount_awarded': '10.00', 'sort_order': '9'},
            {'name': 'First', 'amount_awarded': '20.00', 'sort_order': '1'},
        ], fr=fr)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(
            [line.name for line in fr.line_items.order_by('sort_order')], ['First', 'Last'])


class FundAndFundingRequestPairingTests(TestCase):
    """
    A funding request line may only be named by a fund that draws on one, and
    only ever with the fund's own money. Getting that pairing wrong is silent:
    the request's burndown drifts and nothing on screen says so.
    """

    def setUp(self):
        self.txn = bank(op='OT-FR1', amount='-250.00')
        self.fr = FundingRequest.objects.create(name='NEL26 Grant', fiscal_year=2026)
        self.line = FRLineItem.objects.create(
            funding_request=self.fr, name='Fixtures', amount_awarded=Decimal('1000.00'))

    def _post(self, **overrides):
        data = {
            't-fund_source': str(fund('sga_fr').pk),
            't-lnl_spend_category': str(category('new_stuff').pk),
            't-fr_line_target': str(self.line.pk),
            't-project_tag': '', 't-audit_explanation': '', 't-is_projection': '',
        }
        data.update({'t-%s' % k: v for k, v in overrides.items()})
        return ReconcileForm(data, parent_transaction=self.txn, prefix='t')

    def test_the_fr_fund_requires_a_line(self):
        form = self._post(fr_line_target='')
        self.assertFalse(form.is_valid())
        self.assertIn('has to name the funding request line',
                      str(form.errors['fr_line_target']))

    def test_another_fund_may_not_name_a_line(self):
        form = self._post(fund_source=str(fund('sga_budget').pk))
        self.assertFalse(form.is_valid())
        self.assertIn('Only a fund that draws on a funding request',
                      str(form.errors['fr_line_target']))

    def test_the_pairing_is_accepted(self):
        self.assertTrue(self._post().is_valid())

    def test_the_rule_holds_at_the_model_too(self):
        """ Bulk actions and shell edits never see the form. """
        entry = ParsedTransaction(
            parent_transaction=self.txn, amount=self.txn.net_amount,
            effective_date=self.txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'), fr_line_target=self.line)
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn('fr_line_target', ctx.exception.error_dict)

    def test_a_projection_request_moves_the_entry_to_projection(self):
        """
        This used to be refused. It is how LNL actually funds Projection: the
        purchase leaves the main 226-AG account and SGA reimburses it, so the
        award decides the side rather than colliding with the account.
        """
        projection_fr = FundingRequest.objects.create(
            name='Film Grant', fiscal_year=2026, is_projection=True)
        line = FRLineItem.objects.create(funding_request=projection_fr, name='Prints',
                                         amount_awarded=Decimal('500.00'))
        form = self._post(fr_line_target=str(line.pk))
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertTrue(entry.is_projection)
        self.assertTrue(entry.crosses_partition)

    def test_fund_options_are_tagged_for_the_browser(self):
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        rendered = str(form['fund_source'])
        self.assertIn('data-requires-fr="1"', rendered)
        # ...on exactly the one fund that needs it.
        self.assertEqual(rendered.count('data-requires-fr'), 1)


class CrossFiscalYearTests(TestCase):
    """
    Charging one year's spending to another year's request is legal and
    occasionally right, but it corrupts two burndowns at once when it is not.
    """

    def setUp(self):
        # An FY26 bank line: Sept 2025 falls in FY26 (Jul 2025 - Jun 2026).
        self.txn = bank(op='OT-CY1', amount='-250.00')
        self.this_year = FRLineItem.objects.create(
            funding_request=FundingRequest.objects.create(name='FY26 Grant', fiscal_year=2026),
            name='Fixtures', amount_awarded=Decimal('1000.00'))
        self.last_year = FRLineItem.objects.create(
            funding_request=FundingRequest.objects.create(name='FY25 Grant', fiscal_year=2025),
            name='Cable', amount_awarded=Decimal('1000.00'))

    def _post(self, line, cross=False):
        data = {
            't-fund_source': str(fund('sga_fr').pk),
            't-lnl_spend_category': str(category('new_stuff').pk),
            't-fr_line_target': str(line.pk),
            't-project_tag': '', 't-audit_explanation': '', 't-is_projection': '',
        }
        if cross:
            data['t-allow_cross_year_fr'] = 'on'
        return ReconcileForm(data, parent_transaction=self.txn, prefix='t')

    def test_only_this_years_requests_are_offered(self):
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertEqual(list(form.fields['fr_line_target'].queryset), [self.this_year])

    def test_the_offered_label_carries_the_year_and_the_balance(self):
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        label = form.fields['fr_line_target'].label_from_instance(self.this_year)
        self.assertIn('FY2026', label)
        self.assertIn('$1000.00 left', label)

    def test_same_year_needs_no_ceremony(self):
        self.assertTrue(self._post(self.this_year).is_valid())

    def test_another_year_is_refused_by_default(self):
        form = self._post(self.last_year)
        self.assertFalse(form.is_valid())
        self.assertIn('FY2025 request', str(form.errors['fr_line_target']))

    def test_another_year_goes_through_when_asked_for(self):
        self.assertTrue(self._post(self.last_year, cross=True).is_valid())

    def test_ticking_the_box_widens_the_dropdown(self):
        form = ReconcileForm({'t-allow_cross_year_fr': 'on'},
                             parent_transaction=self.txn, prefix='t')
        self.assertIn(self.last_year, list(form.fields['fr_line_target'].queryset))

    def test_editing_a_deliberate_cross_year_entry_keeps_its_line(self):
        """ Re-opening such an entry must not quietly drop what it points at. """
        entry = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=self.txn.net_amount,
            effective_date=self.txn.accounting_date, fund_source=fund('sga_fr'),
            lnl_spend_category=category('new_stuff'), fr_line_target=self.last_year)
        form = AllocationForm(instance=entry, parent_transaction=self.txn)
        self.assertIn(self.last_year, list(form.fields['fr_line_target'].queryset))
        self.assertTrue(form.initial.get('allow_cross_year_fr'))


class RefundGuardTests(TestCase):
    def setUp(self):
        self.txn = bank(op='OT-RF1', amount='-100.00')
        self.expense = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-100.00'),
            effective_date=datetime.date(2025, 9, 15), fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))

    def _credit(self, op, amount, day=1):
        return ParsedTransaction(
            parent_transaction=bank(op=op, amount=amount), amount=Decimal(amount),
            effective_date=datetime.date(2025, 10, day), refund_of=self.expense,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))

    def test_a_refund_cannot_exceed_the_expense(self):
        with self.assertRaises(ValidationError) as ctx:
            self._credit('OT-RF2', '150.00').full_clean()
        self.assertIn('more than is left to refund', str(ctx.exception))

    def test_repeated_partial_refunds_cannot_overshoot_together(self):
        self._credit('OT-RF3', '60.00').save()
        with self.assertRaises(ValidationError):
            self._credit('OT-RF4', '60.00', day=2).full_clean()

    def test_a_refund_within_the_balance_is_fine(self):
        self._credit('OT-RF5', '40.00').full_clean()

    def test_only_this_years_expenses_are_offered_as_targets(self):
        old = ParsedTransaction.objects.create(
            parent_transaction=bank(op='OT-RF6', amount='-80.00'), amount=Decimal('-80.00'),
            effective_date=datetime.date(2024, 9, 15), fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        offered = list(AllocationForm(parent_transaction=self.txn).fields['refund_of'].queryset)
        self.assertIn(self.expense, offered)
        self.assertNotIn(old, offered)


class EventLinkedExpenseTests(TestCase):
    """
    Sub-rentals: a cost hired for one show and passed straight through to it.
    Until now linked_event was revenue-only, so there was nowhere to say that.
    """

    def setUp(self):
        self.event = Event2019Factory.create(event_name='Pan Asian Semi Formal')
        self.txn = bank(op='Supplier Invoice: 26050479-SINV', amount='-2105.00',
                        line_memo='Equipment rental for Pan Asian')

    def _form(self, **overrides):
        data = {
            't-fund_source': str(fund('sga_budget').pk),
            't-lnl_spend_category': '',
            't-fr_line_target': '', 't-project_tag': '',
            't-audit_explanation': '', 't-is_projection': '',
            't-linked_event': str(self.event.pk),
        }
        data.update({'t-%s' % k: v for k, v in overrides.items()})
        return ReconcileForm(data, parent_transaction=self.txn, prefix='t')

    def test_the_expense_form_offers_the_event(self):
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertIn('linked_event', form.fields)
        self.assertEqual(form.fields['linked_event'].label, "Incurred for event")

    def test_the_expense_form_still_refuses_non_event_revenue(self):
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertNotIn('non_event_revenue_type', form.fields)

    def test_an_expense_can_be_billed_to_an_event(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.linked_event_id, self.event.pk)
        self.assertEqual(entry.amount, Decimal('-2105.00'))

    def test_the_spend_category_fills_itself_in(self):
        """
        The linked event already says what the money was for, so the category
        is not a question worth asking.
        """
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(entry.lnl_spend_category.slug, 'event_expense')

    def test_an_explicit_category_is_not_overwritten(self):
        form = self._form(lnl_spend_category=str(category('consumables').pk))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().lnl_spend_category, category('consumables'))

    def test_nothing_is_filled_in_without_an_event(self):
        """ The default is for pass-through costs only, not for expenses at large. """
        form = self._form(linked_event='')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().lnl_spend_category)

    def test_the_entry_page_still_demands_a_category_without_an_event(self):
        """
        The Entry page is where an expense gets its auditable shape, so there
        the category is required -- unless an event supplies it.
        """
        data = {
            'amount': '-2105.00', 'effective_date': '2025-09-15', 'description': 'Sub-rental',
            'fund_source': str(fund('sga_budget').pk), 'lnl_spend_category': '',
            'fr_line_target': '', 'project_tag': '', 'refund_of': '',
            'audit_explanation': 'Hired for the show', 'is_projection': '',
            'linked_event': '',
        }
        form = AllocationForm(data, parent_transaction=self.txn)
        self.assertFalse(form.is_valid())
        self.assertIn('lnl_spend_category', form.errors)

        form = AllocationForm(dict(data, linked_event=str(self.event.pk)),
                              parent_transaction=self.txn)
        self.assertNotIn('lnl_spend_category', form.errors)

    def test_the_category_is_found_by_flag_not_by_name(self):
        """ Renaming or retiring it in the admin must not break the fill-in. """
        from finance.models import reset_finance_cache
        SpendCategory.objects.filter(is_event_passthrough=True).update(
            name='Passed Through', is_event_passthrough=False)
        replacement = SpendCategory.objects.create(
            name='Show Costs', slug='show_costs', color='#123456', is_event_passthrough=True)
        reset_finance_cache()
        self.addCleanup(reset_finance_cache)

        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().lnl_spend_category, replacement)

    def test_event_linked_expenses_stay_out_of_the_revenue_charts(self):
        """ A cost billed to an event is not income from it. """
        from finance.calculators import revenue_rows
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(revenue_rows(), [])


class FundingRequestFromMemoTests(TestCase):
    """
    Workday memos carry the SGA request they were approved under. That is the
    Treasurer's own reference, written at the time, so matching it is a lookup.
    """

    def setUp(self):
        self.fr = FundingRequest.objects.create(
            name='A Term Films', reference='F.26.6', fiscal_year=2026)
        self.line = FRLineItem.objects.create(
            funding_request=self.fr, name='Film Rights', amount_awarded=Decimal('5000.00'))

    def _txn(self, memo, op='OT-FRM'):
        return bank(op=op, amount='-1100.00', line_memo=memo)

    def test_the_reference_is_found_in_the_memo(self):
        from finance.suggestions import funding_request_references
        self.assertEqual(funding_request_references('Truman Show Film Rights (F.26.6)'),
                         ['F.26.6'])
        self.assertEqual(funding_request_references('A.26.115 Club Sweatshirts'), ['A.26.115'])
        self.assertEqual(funding_request_references('SGA FR F.25.33 was double paid'),
                         ['F.25.33'])

    def test_a_version_number_is_not_a_reference(self):
        from finance.suggestions import funding_request_references
        self.assertEqual(funding_request_references('Invoice 4.5.6'), [])
        self.assertEqual(funding_request_references('no reference here'), [])

    def test_the_request_is_matched(self):
        from finance.suggestions import suggest_funding_request
        found, line = suggest_funding_request(self._txn('Truman Show Film Rights (F.26.6)'))
        self.assertEqual(found, self.fr)
        self.assertEqual(line, self.line)

    def test_the_line_is_only_offered_when_unambiguous(self):
        from finance.suggestions import suggest_funding_request
        FRLineItem.objects.create(funding_request=self.fr, name='Publicity',
                                  amount_awarded=Decimal('500.00'))
        found, line = suggest_funding_request(self._txn('Rights (F.26.6)'))
        self.assertEqual(found, self.fr)
        self.assertIsNone(line, "nothing in the memo says which of two lines it is")

    def test_an_unknown_reference_matches_nothing(self):
        from finance.suggestions import suggest_funding_request
        found, line = suggest_funding_request(self._txn('Rights (F.26.999)'))
        self.assertIsNone(found)

    def test_a_closed_request_is_not_offered(self):
        from finance.suggestions import suggest_funding_request
        FundingRequest.objects.filter(pk=self.fr.pk).update(closed=True)
        found, _ = suggest_funding_request(self._txn('Rights (F.26.6)'))
        self.assertIsNone(found)

    def test_the_match_drives_the_fund_source(self):
        from finance.suggestions import suggest_all
        payload = suggest_all(self._txn('Truman Show Film Rights (F.26.6)'))
        self.assertEqual(payload['fund_source'].value, fund('sga_fr').pk)
        self.assertEqual(payload['fund_source'].confidence, 'high')
        self.assertIn('F.26.6', payload['fund_source'].reason)

    def test_the_match_drives_the_fr_line(self):
        from finance.suggestions import suggest_all
        payload = suggest_all(self._txn('Truman Show Film Rights (F.26.6)'))
        self.assertEqual(payload['fr_line_target'].value, self.line.pk)
        self.assertEqual(payload['fr_line_target'].confidence, 'high')

    def test_without_a_reference_810_answers_nothing(self):
        """
        There is no fallback to fall back to. 810-FD is the fund every LNL line
        is spent out of, so a line with no request number in its memo is simply
        one whose funding source nobody has stated yet.
        """
        from finance.suggestions import suggest_all
        txn = bank(op='OT-NOFR', amount='-50.00', line_memo='Gaff tape')
        txn.worktags_json['fund'] = '810-FD Agency'
        payload = suggest_all(txn)
        self.assertIsNone(payload['fund_source'])

    def test_a_reference_lnldb_does_not_know_is_still_flagged(self):
        """
        A quoted request number we cannot find is a question worth raising even
        though nothing would have been filled in anyway: either the award has
        not been entered yet or the memo is wrong, and both matter.
        """
        from finance.suggestions import suggest_all
        txn = bank(op='OT-GHOST', amount='-50.00', line_memo='Lamps (F.26.999)',
                   worktags={'fund': '810-FD Agency'})
        payload = suggest_all(txn)
        self.assertIsNone(payload['fund_source'])
        self.assertIn('F.26.999', payload['warning'])


class VendorGuessworkRemovedTests(TestCase):
    """
    "Supplier contains barbizon -> Consumables" was a guess about what a vendor
    usually sells. The rules that map Workday's own accounting codes remain.
    """

    def test_no_supplier_or_memo_rules_are_seeded(self):
        from finance.models import SuggestionRule
        self.assertEqual(
            list(SuggestionRule.objects.filter(match_field__in=('supplier', 'memo'))), [])

    def test_the_accounting_code_rules_remain(self):
        from finance.models import SuggestionRule
        self.assertTrue(SuggestionRule.objects.filter(match_field='ledger_account').exists())
        self.assertTrue(SuggestionRule.objects.filter(match_field='spend_category').exists())

    def test_a_known_supplier_no_longer_decides_the_category(self):
        from finance.suggestions import suggest_spend_category
        txn = bank(op='OT-BARB', amount='-100.00', line_memo='')
        txn.supplier = 'Barbizon Lighting'
        txn.worktags_json = {}
        self.assertIsNone(suggest_spend_category(txn))

    def test_the_ledger_account_still_does(self):
        from finance.suggestions import suggest_spend_category
        txn = bank(op='OT-GL', amount='-100.00', line_memo='')
        txn.supplier = 'Anyone At All'
        txn.worktags_json = {'ledger_account': '74100:Repairs & Maintenance'}
        self.assertEqual(suggest_spend_category(txn).value, category('repairs').pk)

    def test_a_treasurer_may_still_add_one_deliberately(self):
        """ The capability stays; only the shipped guesses are gone. """
        from finance.models import SuggestionRule
        from finance.suggestions import suggest_spend_category
        SuggestionRule.objects.create(
            match_field='supplier', match_mode='contains', pattern='barbizon',
            spend_category=category('consumables'), confidence='high', priority=1)
        txn = bank(op='OT-BARB2', amount='-100.00', line_memo='')
        txn.supplier = 'Barbizon Lighting'
        txn.worktags_json = {}
        self.assertEqual(suggest_spend_category(txn).value, category('consumables').pk)


class InternalServiceDeliveryPayeeTests(TestCase):
    """
    An ISD is WPI billing WPI, so it carries neither Supplier nor Employee.
    "(no payee)" told the Treasurer nothing about what the line was.
    """

    def _isd(self, memo='Lens and Lights services for MOTQ: The Lorax FW25'):
        return WorkdayTransaction.objects.create(
            operational_transaction='Internal Service Delivery: 25090179-ISD',
            accounting_date=datetime.date(2025, 9, 15), net_amount=Decimal('886.45'),
            memo=memo, worktags_json={'journal_line_memo': memo})

    def test_the_document_type_names_the_movement(self):
        self.assertEqual(self._isd().document_type, 'Internal Service Delivery')

    def test_the_payee_is_no_longer_blank(self):
        self.assertEqual(self._isd().payee, 'Internal Service Delivery')

    def test_a_supplier_still_wins(self):
        txn = bank(op='Supplier Invoice: 1-SINV', amount='-50.00')
        self.assertEqual(txn.payee, 'B&H Photo')

    def test_an_employee_reimbursement_names_the_employee(self):
        txn = WorkdayTransaction.objects.create(
            operational_transaction='Expense Report: 25061136-EXP',
            accounting_date=datetime.date(2025, 9, 15), net_amount=Decimal('-36.71'),
            employee='Dillan Agarwalla', memo='Mic stand parts')
        self.assertEqual(txn.payee, 'Dillan Agarwalla')

    def test_a_journal_entry_says_so(self):
        txn = WorkdayTransaction.objects.create(
            operational_transaction='', accounting_date=datetime.date(2025, 9, 15),
            net_amount=Decimal('-176.26'), memo='306711: 11x17 posters for LNL',
            worktags_json={'journal': '25090054-JE - Worcester Polytechnic Institute - WPI'})
        self.assertEqual(txn.payee, 'Journal Entry')
        self.assertEqual(txn.reference, '25090054-JE')

    def test_the_description_falls_back_to_the_memo_when_nothing_is_named(self):
        txn = WorkdayTransaction.objects.create(
            operational_transaction='', accounting_date=datetime.date(2025, 9, 15),
            net_amount=Decimal('-10.00'), memo='Something with no document type')
        self.assertEqual(txn.description, 'Something with no document type')


class MatchModeTests(TestCase):
    """
    A rule now states how it compares, which is what separates "the export says
    so" from "a word turned up in some prose".
    """

    def _rule(self, mode, pattern, field='spend_category'):
        return SuggestionRule(match_field=field, match_mode=mode, pattern=pattern,
                              spend_category=category('printing'))

    def test_exact_matches_the_whole_value(self):
        txn = bank(op='OT-EX')
        txn.worktags_json['spend_category'] = 'Printing'
        self.assertTrue(self._rule('exact', 'Printing').matches(txn))
        self.assertTrue(self._rule('exact', '  printing ').matches(txn),
                        "case and surrounding space are noise")

    def test_exact_refuses_a_near_miss(self):
        txn = bank(op='OT-EX2')
        txn.worktags_json['spend_category'] = 'Printing IDT'
        self.assertFalse(self._rule('exact', 'Printing').matches(txn))

    def test_starts_with_matches_an_account_number(self):
        txn = bank(op='OT-GL')
        txn.worktags_json['ledger_account'] = '71100:Supplies'
        self.assertTrue(self._rule('starts', '71100', field='ledger_account').matches(txn))
        self.assertFalse(self._rule('starts', '711000', field='ledger_account').matches(txn))

    def test_contains_matches_anywhere(self):
        txn = bank(op='OT-C')
        txn.worktags_json['spend_category'] = 'Supplies - Office'
        self.assertTrue(self._rule('contains', 'office').matches(txn))

    def test_word_matches_whole_words_only(self):
        txn = bank(op='OT-W', line_memo='Angela signed for the delivery')
        self.assertFalse(self._rule('word', 'gel', field='memo').matches(txn))

    def test_only_code_matches_count_as_lookups(self):
        self.assertTrue(self._rule('exact', 'Printing').is_lookup)
        self.assertTrue(self._rule('starts', '71100', field='ledger_account').is_lookup)
        self.assertFalse(self._rule('contains', 'print').is_lookup)
        self.assertFalse(self._rule('word', 'print', field='memo').is_lookup)

    def test_a_blank_column_never_matches(self):
        """ An empty Spend Category is not "exactly nothing"; it is unknown. """
        txn = bank(op='OT-BLANK')
        txn.worktags_json['spend_category'] = ''
        self.assertFalse(self._rule('exact', '').matches(txn))
        self.assertFalse(self._rule('contains', 'supplies').matches(txn))


class SeededChartOfAccountsTests(TestCase):
    """
    The seeded rules come from eleven years of real 226-AG exports. What
    matters is the precedence: Workday's own Spend Category is the finest code
    in the file and has to outrank the ledger account it sits under.
    """

    def _category_for(self, ledger_account, spend_category):
        txn = bank(op='OT-%s-%s' % (ledger_account, spend_category))
        txn.worktags_json['ledger_account'] = ledger_account
        txn.worktags_json['spend_category'] = spend_category
        return suggest_spend_category(txn)

    def test_the_workday_category_outranks_the_ledger_account(self):
        """
        Printing and Supplies - Medical both sit under 71100:Supplies and are
        not remotely the same thing.
        """
        self.assertEqual(self._category_for('71100:Supplies', 'Printing').value,
                         category('printing').pk)
        self.assertEqual(self._category_for('71100:Supplies', 'Supplies - Medical').value,
                         category('safety').pk)
        self.assertEqual(self._category_for('71100:Supplies', 'Supplies').value,
                         category('consumables').pk)

    def test_an_unmapped_workday_category_falls_back_to_the_account(self):
        """ Still a lookup -- a coarser code, but a code. """
        found = self._category_for('74900:Miscellaneous Fees', 'Some New Fee Type')
        self.assertEqual(found.value, category('other').pk)
        self.assertTrue(found.is_lookup)
        self.assertIn('74900', found.reason)

    def test_every_expense_account_in_the_export_is_covered(self):
        """
        Sixteen accounts appear on expense lines across FY18-FY26. A line whose
        account nobody has mapped leaves the Treasurer typing.
        """
        accounts = ['70000', '71050', '71100', '71200', '71500', '72000', '73100', '73200',
                    '73400', '74100', '74600', '74800', '74900', '75000', '79600', '79700']
        for account in accounts:
            found = self._category_for('%s:Whatever' % account, '')
            self.assertIsNotNone(found, "no rule covers ledger account %s" % account)

    def test_no_seeded_rule_guesses_from_wording(self):
        """
        Every rule that fills a box in has to be an exact or starts-with match
        on a code. Anything softer may only be offered.
        """
        for rule in SuggestionRule.objects.filter(is_active=True):
            if rule.match_field in ('supplier', 'memo'):
                self.assertFalse(rule.is_lookup,
                                 "%s would fill the form in from a name or a memo" % rule)


class WorkdayFundCodeTests(TestCase):
    """
    Which Workday Fund code means which LNL bucket used to be an ``if '810' in
    fund``. It is WPI's numbering and LNL's convention, so it is admin data.
    """

    def tearDown(self):
        reset_finance_cache('fund_codes')

    def test_a_seeded_code_finds_its_bucket(self):
        self.assertEqual(fund_source_for_workday_fund('220-FD Gift'), fund('legacy'))

    def test_810_does_not_mean_sga(self):
        """
        All of LNL's spending comes out of 810-FD, so the code is a fact about
        the account, not about who paid. Standing budget, out-of-cycle award and
        legacy money all look like this, and picking one would be a coin flip
        dressed up as a lookup.
        """
        self.assertIsNone(fund_source_for_workday_fund('810-FD Agency'))
        self.assertEqual(fund('sga_budget').workday_fund_codes, '')

    def test_an_unconfigured_code_finds_nothing(self):
        self.assertIsNone(fund_source_for_workday_fund('999-FD Something'))
        self.assertIsNone(fund_source_for_workday_fund(''))

    def test_a_treasurer_can_repoint_a_code_without_a_deploy(self):
        FundSource.objects.filter(slug='legacy').update(workday_fund_codes='')
        FundSource.objects.filter(slug='sga_budget').update(workday_fund_codes='220')
        reset_finance_cache('fund_codes')
        self.assertEqual(fund_source_for_workday_fund('220-FD Gift'), fund('sga_budget'))

    def test_a_fund_with_no_codes_is_never_chosen(self):
        self.assertEqual(fund('sga_fr').workday_fund_codes, '',
                         "an award is identified by its number, not by a fund code")


class AutofillFromExportTests(TestCase):
    """
    Reconciling should be confirming, not typing. Everything the export already
    states is selected when the form is built; everything we merely inferred is
    left as a chip.
    """

    def setUp(self):
        self.txn = bank(op='Supplier Invoice: 1-SINV', amount='-129.00',
                        worktags={'fund': '810-FD Agency',
                                  'ledger_account': '71100:Supplies',
                                  'spend_category': 'Printing'})

    def form(self, **kwargs):
        return ReconcileForm(parent_transaction=self.txn, prefix='t', **kwargs)

    def legacy_txn(self):
        """ A line on a fund code that does name one bucket and nothing else. """
        return bank(op='Supplier Invoice: 2-SINV', amount='-129.00',
                    worktags={'fund': '220-FD Gift',
                              'ledger_account': '71100:Supplies',
                              'spend_category': 'Printing'})

    def test_the_spend_category_is_selected(self):
        form = self.form()
        self.assertEqual(form.initial['lnl_spend_category'], category('printing').pk)
        self.assertIn('lnl_spend_category', form.autofilled)

    def test_the_fund_is_left_blank_on_810(self):
        """
        810-FD is the fund all of LNL's spending comes out of, so it says
        nothing about whose money this was. Blank is the honest answer, and
        pre-filling a bucket would be worse than empty: an autofilled box
        reads as something the export stated, and nobody re-reads it.
        """
        form = self.form()
        self.assertNotIn('fund_source', form.initial)
        self.assertNotIn('fund_source', form.autofilled)

    def test_a_fund_code_naming_one_bucket_is_selected(self):
        self.txn = self.legacy_txn()
        self.assertEqual(self.form().initial['fund_source'], fund('legacy').pk)

    def test_the_badge_says_which_column_answered(self):
        form = self.form()
        self.assertIn('Printing', form.autofilled['lnl_spend_category'].reason)
        self.txn = self.legacy_txn()
        self.assertIn('220-FD', self.form().autofilled['fund_source'].reason)

    def test_a_filled_form_submits_as_it_stands(self):
        """ The point of the exercise: open the queue, press Allocate. """
        self.txn = self.legacy_txn()
        form = self.form()
        data = {'t-%s' % name: str(value) for name, value in form.initial.items()
                if value not in (None, '')}
        bound = ReconcileForm(data, parent_transaction=self.txn, prefix='t')
        self.assertTrue(bound.is_valid(), bound.errors)
        entry = bound.save()
        self.assertEqual(entry.lnl_spend_category, category('printing'))
        self.assertEqual(entry.fund_source, fund('legacy'))

    def test_a_guess_is_never_filled_in(self):
        """
        A supplier rule is a guess about what a vendor usually sells. It may be
        offered; it may not answer the question on the Treasurer's behalf.
        """
        SuggestionRule.objects.filter(match_field='spend_category').delete()
        SuggestionRule.objects.filter(match_field='ledger_account').delete()
        SuggestionRule.objects.create(
            match_field='supplier', match_mode='contains', pattern='b&h',
            spend_category=category('consumables'), confidence='high', priority=1)

        form = self.form()
        self.assertNotIn('lnl_spend_category', form.autofilled)
        self.assertIsNone(form.initial.get('lnl_spend_category'))
        # ...but the suggestion is still there for the chip to offer.
        self.assertEqual(form.suggestions()['spend_category'].value, category('consumables').pk)

    def test_a_bound_form_is_left_alone(self):
        """ Whatever the Treasurer submitted wins, including a deliberate blank. """
        form = ReconcileForm({'t-fund_source': str(fund('legacy').pk),
                              't-lnl_spend_category': str(category('food').pk)},
                             parent_transaction=self.txn, prefix='t')
        self.assertEqual(form.autofilled, {})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().lnl_spend_category, category('food'))

    def test_a_saved_entry_is_left_alone(self):
        entry = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-129.00'),
            effective_date=self.txn.accounting_date, description='Posters',
            fund_source=fund('legacy'), lnl_spend_category=category('food'))
        form = ReconcileForm(instance=entry, prefix='t')
        self.assertEqual(form.autofilled, {})

    def test_an_explicit_initial_is_not_overwritten(self):
        form = self.form(initial={'lnl_spend_category': category('food').pk})
        self.assertEqual(form.initial['lnl_spend_category'], category('food').pk)
        self.assertNotIn('lnl_spend_category', form.autofilled)

    def test_nothing_is_filled_in_for_revenue(self):
        """ Which event a deposit belongs to is a guess, and stays one. """
        deposit = bank(op='OT-REV', amount='886.45')
        form = ReconcileForm(parent_transaction=deposit, prefix='t')
        self.assertEqual(form.autofilled, {})

    def test_the_project_code_is_filled_from_the_export(self):
        tag = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        self.txn = bank(op='OT-NEL', amount='-129.00',
                        worktags={'fund': '810-FD Agency', 'program': 'NEL26 build'})
        form = self.form()
        self.assertEqual(form.initial['project_tag'], tag.pk)
        self.assertIn('NEL26', form.autofilled['project_tag'].reason)


class AutofillFundingRequestTests(TestCase):
    """ A request number written into the memo is the Treasurer's own record. """

    def setUp(self):
        self.fr = FundingRequest.objects.create(
            name='A Term Films', reference='F.26.6', fiscal_year=2026)
        self.line = FRLineItem.objects.create(
            funding_request=self.fr, name='Film Rights', amount_awarded=Decimal('5000.00'))
        self.txn = bank(op='OT-FR', amount='-1100.00', line_memo='Truman Show rights (F.26.6)',
                        worktags={'fund': '810-FD Agency'})

    def test_the_fund_and_the_line_are_both_selected(self):
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertEqual(form.initial['fund_source'], fund('sga_fr').pk)
        self.assertEqual(form.initial['fr_line_target'], self.line.pk)

    def test_the_award_beats_the_fund_worktag(self):
        """
        Every LNL line carries the same Fund code, so the memo is the only
        thing that can tell an award from the standing budget.
        """
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertNotEqual(form.initial['fund_source'], fund('sga_budget').pk)

    def test_an_ambiguous_request_fills_the_fund_but_not_the_line(self):
        FRLineItem.objects.create(funding_request=self.fr, name='Publicity',
                                  amount_awarded=Decimal('500.00'))
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertEqual(form.initial['fund_source'], fund('sga_fr').pk)
        self.assertIsNone(form.initial.get('fr_line_target'),
                          "nothing in the memo says which of two lines it is")

    def test_a_line_from_another_year_is_not_filled_in(self):
        """
        Cross-year charging is deliberate, behind a tick box. Selecting a value
        the picker does not offer would show an empty box contradicting the
        badge beside it.
        """
        FundingRequest.objects.filter(pk=self.fr.pk).update(fiscal_year=2025)
        form = ReconcileForm(parent_transaction=self.txn, prefix='t')
        self.assertIsNone(form.initial.get('fr_line_target'))
        self.assertNotIn('fr_line_target', form.autofilled)

    def test_a_request_lnldb_has_never_heard_of_fills_in_nothing(self):
        txn = bank(op='OT-GHOST', amount='-40.00', line_memo='Lamps (F.26.999)',
                   worktags={'fund': '810-FD Agency'})
        form = ReconcileForm(parent_transaction=txn, prefix='t')
        self.assertNotIn('fund_source', form.autofilled)
        self.assertIn('F.26.999', form.suggestions()['warning'])


class UnmappedCategoryReportTests(TestCase):
    """
    A Workday category nothing covers is a question the Treasurer answers by
    hand on every line carrying it, forever. Worth naming at import time.
    """

    def _txn(self, op, workday_category, ledger='71100:Supplies'):
        return bank(op=op, amount='-10.00',
                    worktags={'spend_category': workday_category, 'ledger_account': ledger})

    def test_a_covered_category_is_not_reported(self):
        txn = self._txn('OT-OK', 'Printing')
        self.assertEqual(unmapped_spend_categories([txn]), [])

    def test_the_ledger_account_counts_as_coverage(self):
        """ Not ideal, but not unanswered either. """
        txn = self._txn('OT-FALLBACK', 'Newly Invented Category')
        self.assertEqual(unmapped_spend_categories([txn]), [])

    def test_a_genuinely_unknown_line_is_reported_with_a_count(self):
        rows = [self._txn('OT-N%s' % i, 'Drone Insurance', ledger='88888:New Account')
                for i in range(3)]
        self.assertEqual(unmapped_spend_categories(rows), [('Drone Insurance', 3)])

    def test_a_line_with_no_workday_category_is_not_a_gap(self):
        txn = self._txn('OT-BLANK2', '', ledger='88888:New Account')
        self.assertEqual(unmapped_spend_categories([txn]), [])


class PartitionDefaultOnFormsTests(TestCase):
    """
    Dropping the lock left one trap: a form that never shows the tick box would
    file everything as Event Production. Whether anyone was actually asked is
    what decides between "they said no" and "nobody said".
    """

    def _projection_line(self):
        return WorkdayTransaction.objects.create(
            operational_transaction='OT-315', accounting_date=datetime.date(2025, 9, 15),
            net_amount=Decimal('-400.00'), supplier='Christie Digital',
            memo='Projector lamp',
            worktags_json={'student_organization': '315-AG Projection'})

    def test_the_queue_form_starts_on_the_accounts_side(self):
        form = ReconcileForm(parent_transaction=self._projection_line(), prefix='t')
        self.assertTrue(form.fields['is_projection'].initial)
        self.assertFalse(form.fields['is_projection'].disabled,
                         "it is a starting position, not a lock")

    def test_a_split_slice_inherits_the_side_it_was_never_asked_about(self):
        from finance.forms import SplitFormSet
        parent = self._projection_line()
        data = {
            'slices-TOTAL_FORMS': '1', 'slices-INITIAL_FORMS': '0',
            'slices-MIN_NUM_FORMS': '0', 'slices-MAX_NUM_FORMS': '1000',
            'slices-0-amount': '-400.00',
            'slices-0-description': 'Lamp',
            'slices-0-fund_source': str(fund('sga_budget').pk),
            'slices-0-lnl_spend_category': str(category('repairs').pk),
        }
        formset = SplitFormSet(data, instance=parent, parent_transaction=parent,
                               prefix='slices')
        self.assertNotIn('is_projection', formset.forms[0].fields,
                         "the split modal has no room for a column nobody changes")
        self.assertTrue(formset.is_valid(), formset.errors)
        entry = formset.save()[0]
        self.assertTrue(entry.is_projection)

    def test_a_deliberate_no_survives(self):
        parent = self._projection_line()
        form = ReconcileForm({'t-fund_source': str(fund('sga_budget').pk),
                              't-lnl_spend_category': str(category('repairs').pk),
                              't-audit_explanation': 'Recharged to Event Production.'},
                             parent_transaction=parent, prefix='t')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.save().is_projection)

    def test_the_reason_is_demanded_by_name(self):
        parent = self._projection_line()
        form = ReconcileForm({'t-fund_source': str(fund('sga_budget').pk),
                              't-lnl_spend_category': str(category('repairs').pk)},
                             parent_transaction=parent, prefix='t')
        self.assertFalse(form.is_valid())
        self.assertIn('audit_explanation', form.errors)
        self.assertIn('315-AG', str(form.errors['audit_explanation']))


class RefundPickerTests(TestCase):
    """
    What the Refund-of dropdown actually offers, and how each option reads.

    An option that can only ever fail validation is worse than no option: it
    reads as a bug in the ledger rather than as a rule.
    """

    def setUp(self):
        self.txn = bank(op='OT-RF1', amount='-129.00', line_memo='Gaff tape')
        self.expense = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-129.00'),
            effective_date=datetime.date(2025, 9, 15), description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        self.credit = bank(op='OT-RF2', amount='129.00')

    def _form(self, **kwargs):
        kwargs.setdefault('parent_transaction', self.credit)
        return AllocationForm(prefix='t', **kwargs)

    def _labels(self):
        return [label for value, label in self._form().fields['refund_of'].choices if value]

    def test_each_option_says_which_purchase_it_was(self):
        labels = self._labels()
        self.assertEqual(len(labels), 1)
        self.assertIn('Gaff tape', labels[0])
        self.assertIn('129.00', labels[0])
        self.assertNotEqual(str(labels[0]), 'Expense -129.00')

    def test_the_empty_option_explains_itself(self):
        field = self._form().fields['refund_of']
        self.assertIn('Not a refund', str(field.empty_label))

    def test_an_encumbrance_is_not_offered(self):
        """ No money has left the account, so there is none to come back. """
        ParsedTransaction.objects.create(
            amount=Decimal('-400.00'), effective_date=datetime.date(2025, 9, 15),
            description='Deposit on a console', fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'))
        self.assertEqual(len(self._labels()), 1)

    def test_a_fully_refunded_purchase_is_not_offered(self):
        ParsedTransaction.objects.create(
            parent_transaction=bank(op='OT-RF3', amount='129.00'),
            amount=Decimal('129.00'), effective_date=datetime.date(2025, 9, 20),
            refund_of=self.expense, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self.assertEqual(self._labels(), [])

    def test_a_part_refunded_purchase_is_offered_and_says_what_is_left(self):
        ParsedTransaction.objects.create(
            parent_transaction=bank(op='OT-RF4', amount='29.00'),
            amount=Decimal('29.00'), effective_date=datetime.date(2025, 9, 20),
            refund_of=self.expense, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        labels = self._labels()
        self.assertEqual(len(labels), 1)
        self.assertIn('$100.00 left to refund', labels[0])

    def test_only_the_entry_page_offers_the_field_at_all(self):
        """
        A declared form field lands on every subclass whatever its
        ``Meta.fields`` says. Three of them leave ``refund_of`` out on purpose,
        and the queue's routing-only form accepting a refund target would undo
        the mutual exclusion the base class makes structural.
        """
        for cls in (ReconcileForm, EncumbranceForm, SplitLineForm):
            form = cls(parent_transaction=self.txn)
            self.assertNotIn('refund_of', form.fields, cls.__name__)
        self.assertIn('refund_of', self._form().fields)

    def test_an_entry_is_not_offered_as_its_own_refund(self):
        form = AllocationForm(instance=self.expense,
                              parent_transaction=self.txn, prefix='t')
        values = [value for value, label in form.fields['refund_of'].choices if value]
        self.assertNotIn(self.expense.pk, [int(v) for v in values])

    def test_the_picker_costs_no_query_per_option(self):
        """ Every label reads the payee off the bank line; that is one join. """
        for index in range(6):
            other = bank(op='OT-RFN%s' % index, amount='-50.00')
            ParsedTransaction.objects.create(
                parent_transaction=other, amount=Decimal('-50.00'),
                effective_date=datetime.date(2025, 9, 15), description='Thing %s' % index,
                fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        form = self._form()
        with self.assertNumQueries(1):
            [label for value, label in form.fields['refund_of'].choices if value]

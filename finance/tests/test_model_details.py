"""
The smaller surfaces of the models: labels, caches, and defensive branches.

The accounting rules live in ``test_models``; what is here is everything around
them. Two kinds of thing, both easy to leave untested and both load-bearing:

**How a row reads.** ``__str__`` and the picker labels are what a Treasurer
actually chooses between, and a dropdown of near-identical strings is a wrong
answer waiting to be clicked.

**What happens when something is missing.** A configuration row that does not
exist yet, a fiscal year that starts in January, a project node whose cached
tree bounds have gone stale. Each of these has a guard, and a guard nothing
exercises is a guess.
"""
import datetime
from decimal import Decimal

from django.test import TestCase

from events.tests.generators import CategoryFactory, Event2019Factory, OrgFactory
from finance.models import (ClientType, ColumnAlias, FinanceSettings, FRLineItem,
                            FundingRequest, ParsedTransaction, PartitionCode, ProjectTag,
                            ServiceColor, SuggestionRule, WorkdayTransaction, fiscal_year_bounds,
                            fiscal_year_for, money, reset_finance_cache)
from finance.tests.util import category, fund

SEP = datetime.date(2025, 9, 15)


class MoneyHelperTests(TestCase):
    """ Everything monetary crosses back into cents here; see ``money``. """

    def test_it_quantizes_to_cents(self):
        self.assertEqual(str(money(Decimal('2808.24000000000'))), '2808.24')

    def test_scientific_zero_becomes_plain_zero(self):
        self.assertEqual(str(money(Decimal('0E-11'))), '0.00')

    def test_nothing_is_zero(self):
        self.assertEqual(money(None), Decimal('0.00'))
        self.assertEqual(money(''), Decimal('0.00'))

    def test_a_float_or_string_is_accepted(self):
        self.assertEqual(money(12.5), Decimal('12.50'))
        self.assertEqual(money('12.5'), Decimal('12.50'))

    def test_something_unparseable_is_zero_rather_than_an_exception(self):
        """ These run while rendering a page; raising blanks it. """
        self.assertEqual(money('elephant'), Decimal('0.00'))
        self.assertEqual(money(object()), Decimal('0.00'))

    def test_a_non_finite_value_is_zero(self):
        """ Division inside an aggregate can yield these; they are not money. """
        self.assertEqual(money(Decimal('NaN')), Decimal('0.00'))
        self.assertEqual(money(Decimal('Infinity')), Decimal('0.00'))

    def test_it_rounds_half_away_from_zero(self):
        self.assertEqual(money(Decimal('0.125')), Decimal('0.13'))
        self.assertEqual(money(Decimal('-0.125')), Decimal('-0.13'))


class FiscalYearTests(TestCase):
    """
    WPI's year runs July to June and is named for the year it ends in. Which
    month it starts in is a settings row, not a constant -- it has changed once.
    """

    def tearDown(self):
        reset_finance_cache()

    def test_a_date_in_the_second_half_belongs_to_the_next_year(self):
        self.assertEqual(fiscal_year_for(datetime.date(2025, 9, 15)), 2026)

    def test_a_date_before_the_start_month_belongs_to_this_one(self):
        self.assertEqual(fiscal_year_for(datetime.date(2025, 3, 15)), 2025)

    def test_no_date_has_no_fiscal_year(self):
        self.assertIsNone(fiscal_year_for(None))

    def test_the_bounds_span_exactly_one_year(self):
        start, end = fiscal_year_bounds(2026)
        self.assertEqual(start, datetime.date(2025, 7, 1))
        self.assertEqual(end, datetime.date(2026, 6, 30))

    def test_a_january_start_makes_the_year_a_calendar_one(self):
        """
        The one case the general formula gets wrong: stepping back a day from
        the next year's first month would land in the wrong December.
        """
        settings_row = FinanceSettings.load()
        settings_row.fiscal_year_start_month = 1
        settings_row.save()
        reset_finance_cache()
        start, end = fiscal_year_bounds(2026)
        self.assertEqual(start, datetime.date(2025, 1, 1))
        self.assertEqual(end, datetime.date(2025, 12, 31))

    def test_the_start_month_is_read_from_the_settings_row(self):
        settings_row = FinanceSettings.load()
        settings_row.fiscal_year_start_month = 9
        settings_row.save()
        reset_finance_cache()
        self.assertEqual(fiscal_year_for(datetime.date(2025, 8, 31)), 2025)
        self.assertEqual(fiscal_year_for(datetime.date(2025, 9, 1)), 2026)


class SettingsCacheTests(TestCase):
    """
    The configuration is cached because it is read on nearly every request, and
    falls back to defaults when it cannot be read at all.
    """

    def tearDown(self):
        reset_finance_cache()

    def test_the_defaults_answer_before_the_table_exists(self):
        """
        Read during migrations and at import time, when the row -- and on a
        fresh database the table -- is not there yet. Raising there would make
        the first ``migrate`` impossible.
        """
        from finance.models import _cached
        sentinel = object()

        def explode():
            raise RuntimeError('no such table')

        self.assertIs(_cached('never-built', explode, sentinel), sentinel)

    def test_a_built_value_is_reused(self):
        from finance.models import _cached
        calls = []

        def build():
            calls.append(1)
            return 'value'

        _cached('counted', build, None)
        _cached('counted', build, None)
        self.assertEqual(len(calls), 1)

    def test_resetting_one_key_leaves_the_others(self):
        from finance.models import _CACHE, _cached
        _cached('keep-me', lambda: 'a', None)
        _cached('drop-me', lambda: 'b', None)
        reset_finance_cache('drop-me')
        self.assertIn('keep-me', _CACHE)
        self.assertNotIn('drop-me', _CACHE)

    def test_resetting_everything_clears_the_lot(self):
        from finance.models import _CACHE, _cached
        _cached('anything', lambda: 'a', None)
        reset_finance_cache()
        self.assertNotIn('anything', _CACHE)

    def test_editing_a_partition_code_invalidates_the_cache(self):
        """ Otherwise an admin edit takes effect only after a restart. """
        from finance.models import partition_codes
        before = {entry['code'] for entry in partition_codes()}
        PartitionCode.objects.create(code='999-AG', is_projection=True,
                                     worktag='student_organization')
        after = {entry['code'] for entry in partition_codes()}
        self.assertNotIn('999-AG', before)
        self.assertIn('999-AG', after)


class LabelTests(TestCase):
    """ How each row reads where a person has to choose between them. """

    def setUp(self):
        self.txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-L1', accounting_date=SEP,
            net_amount=Decimal('-129.00'), supplier='B&H Photo')

    def test_a_bank_line_reads_as_reference_description_and_amount(self):
        self.assertIn('OT-L1', str(self.txn))
        self.assertIn('129', str(self.txn))

    def test_a_partition_code_says_which_side_it_locks_to(self):
        code = PartitionCode.objects.get(code='315-AG')
        self.assertIn('315-AG', str(code))
        self.assertIn('Projection', str(code))

    def test_a_column_alias_reads_as_a_mapping(self):
        alias = ColumnAlias.objects.create(canonical='student_organization',
                                           alias='Student Org Code')
        self.assertIn('Student Org Code', str(alias))
        self.assertIn('student_organization', str(alias))

    def test_a_service_colour_names_its_category(self):
        colour = ServiceColor.objects.create(category=CategoryFactory(name='Lighting'),
                                             color='#4E79A7')
        self.assertIn('Lighting', str(colour))
        self.assertIn('#4E79A7', str(colour))

    def test_a_suggestion_rule_reads_as_the_sentence_it_is(self):
        rule = SuggestionRule.objects.create(
            match_field='memo', match_mode='word', pattern='gaff',
            spend_category=category('consumables'))
        text = str(rule)
        self.assertIn('gaff', text)
        self.assertIn('Consumables', text)

    def test_a_project_tag_links_to_its_own_page(self):
        tag = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        self.assertIn(str(tag.pk), tag.get_absolute_url())

    def test_a_funding_request_links_to_its_own_page(self):
        request = FundingRequest.objects.create(name='A Term Films', fiscal_year=2026)
        self.assertIn(str(request.pk), request.get_absolute_url())

    def test_an_fr_line_names_the_year_the_request_and_what_is_left(self):
        """ Both are things you can get wrong without noticing. """
        request = FundingRequest.objects.create(name='A Term Films', reference='F.26.6',
                                                fiscal_year=2026)
        line = FRLineItem.objects.create(funding_request=request, name='Film Rights',
                                         amount_awarded=Decimal('5000.00'))
        label = line.picker_label
        self.assertIn('FY2026', label)
        self.assertIn('F.26.6', label)
        self.assertIn('$5000.00 left', label)

    def test_an_overspent_fr_line_says_so_rather_than_showing_a_negative(self):
        request = FundingRequest.objects.create(name='A Term Films', fiscal_year=2026)
        line = FRLineItem.objects.create(funding_request=request, name='Film Rights',
                                         amount_awarded=Decimal('100.00'))
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-129.00'), effective_date=SEP,
            fund_source=fund('sga_fr'), fr_line_target=line)
        self.assertIn('OVER by $29.00', line.picker_label)

    def test_a_project_tag_indents_by_depth(self):
        parent = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        child = ProjectTag.objects.create(name='D60 Lustrs', code='D60', parent=parent)
        self.assertNotIn(' ', parent.indented_label)
        self.assertIn(' ', ProjectTag.objects.get(pk=child.pk).indented_label)


class ProjectRollupTests(TestCase):
    """ What a project really cost, across fiscal years and funding sources. """

    def setUp(self):
        self.parent = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        self.child = ProjectTag.objects.create(name='D60 Lustrs', code='D60',
                                               parent=self.parent)
        self.txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-R1', accounting_date=SEP,
            net_amount=Decimal('-500.00'))

    def _spend(self, tag, amount, date=SEP):
        return ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal(amount), effective_date=date,
            project_tag=tag, fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'))

    def test_cost_rolls_up_from_the_children(self):
        self._spend(self.child, '-300.00')
        self._spend(self.parent, '-100.00')
        self.assertEqual(self.parent.total_cost(), Decimal('400.00'))

    def test_it_can_be_asked_for_the_node_alone(self):
        self._spend(self.child, '-300.00')
        self._spend(self.parent, '-100.00')
        self.assertEqual(self.parent.total_cost(include_descendants=False),
                         Decimal('100.00'))

    def test_a_refund_reduces_what_the_project_cost(self):
        purchase = self._spend(self.child, '-300.00')
        credit_txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-R2', accounting_date=SEP,
            net_amount=Decimal('50.00'))
        ParsedTransaction.objects.create(
            parent_transaction=credit_txn, amount=Decimal('50.00'), effective_date=SEP,
            project_tag=self.child, refund_of=purchase,
            fund_source=fund('sga_budget'), lnl_spend_category=category('new_stuff'))
        self.assertEqual(self.parent.total_cost(), Decimal('250.00'))

    def test_it_can_be_narrowed_to_one_fiscal_year(self):
        self._spend(self.child, '-300.00')
        self._spend(self.child, '-100.00', date=datetime.date(2024, 9, 15))
        self.assertEqual(self.parent.total_cost(fiscal_year=2026), Decimal('300.00'))
        self.assertEqual(self.parent.total_cost(), Decimal('400.00'))

    def test_the_rollup_survives_stale_cached_tree_bounds(self):
        """
        MPTT caches ``lft``/``rght`` on the instance and they go stale the
        moment anything else in the forest is written -- adding an unrelated
        root is enough. Walking stale bounds silently reports the wrong cost,
        on a figure people make purchasing decisions from.
        """
        stale = ProjectTag.objects.get(pk=self.parent.pk)
        ProjectTag.objects.create(name='Unrelated', code='UNREL')
        self._spend(self.child, '-300.00')
        self.assertEqual(stale.total_cost(), Decimal('300.00'))

    def test_a_leaf_with_nothing_filed_against_it_costs_nothing(self):
        self.assertEqual(self.child.total_cost(), Decimal('0.00'))


class ClientTypeTests(TestCase):
    """ Student org or department, inherited from the event rather than re-keyed. """

    def setUp(self):
        self.txn = WorkdayTransaction.objects.create(
            operational_transaction='OT-C1', accounting_date=SEP,
            net_amount=Decimal('500.00'))

    def _entry(self, event=None):
        from finance.models import RevenueSource
        return ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('500.00'), effective_date=SEP,
            linked_event=event,
            non_event_revenue_type=None if event else RevenueSource.objects.active().first())

    def test_revenue_with_no_event_has_no_client(self):
        """ Excluded from the client charts rather than bucketed as Unknown. """
        self.assertEqual(self._entry().client_type, ClientType.UNKNOWN)

    def test_an_event_on_the_student_org_fund_is_a_student_org(self):
        event = Event2019Factory(event_name='Fall Concert')
        event.workday_fund = 810
        event.save()
        self.assertEqual(self._entry(event).client_type, ClientType.STUDENT_ORG)

    def test_an_event_on_any_other_fund_is_a_department(self):
        event = Event2019Factory(event_name='Faculty Lecture')
        event.workday_fund = 110
        event.save()
        self.assertEqual(self._entry(event).client_type, ClientType.DEPARTMENT)

    def test_an_event_with_no_fund_at_all_is_unknown(self):
        event = Event2019Factory(event_name='Unfunded')
        event.workday_fund = None
        event.save()
        self.assertEqual(self._entry(event).client_type, ClientType.UNKNOWN)

    def test_the_fund_falls_back_to_the_billing_organisation(self):
        """ Older events carry no fund of their own; the client's is the answer. """
        org = OrgFactory(name='Alpha Club')
        org.workday_fund = 810
        org.save()
        event = Event2019Factory(event_name='Older Show', billing_org=org)
        event.workday_fund = None
        event.save()
        self.assertEqual(self._entry(event).client_type, ClientType.STUDENT_ORG)

    def test_the_display_form_is_the_readable_label(self):
        self.assertEqual(self._entry().client_type_display, ClientType.UNKNOWN.label)


class PartitionCrossingTests(TestCase):
    """ Which account paid, versus which activity the money was for. """

    def _txn(self, org):
        return WorkdayTransaction.objects.create(
            operational_transaction='OT-P%s' % org[:3], accounting_date=SEP,
            net_amount=Decimal('-100.00'),
            worktags_json={'student_organization': org})

    def _entry(self, txn, is_projection):
        return ParsedTransaction(
            parent_transaction=txn, amount=Decimal('-100.00'), effective_date=SEP,
            is_projection=is_projection, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))

    def test_an_entry_filed_on_its_own_side_does_not_cross(self):
        txn = self._txn('315-AG Projection')
        self.assertFalse(self._entry(txn, True).crosses_partition)

    def test_an_entry_filed_on_the_other_side_crosses(self):
        txn = self._txn('315-AG Projection')
        self.assertTrue(self._entry(txn, False).crosses_partition)

    def test_a_line_from_an_unrecognised_account_never_crosses(self):
        """ With no side to start from there is nothing to cross. """
        txn = self._txn('999-ZZ Unknown')
        self.assertFalse(self._entry(txn, True).crosses_partition)

    def test_an_encumbrance_never_crosses(self):
        """ No bank line, so no account to have come out of. """
        entry = ParsedTransaction(amount=Decimal('-100.00'), effective_date=SEP,
                                  is_projection=True)
        self.assertFalse(entry.crosses_partition)

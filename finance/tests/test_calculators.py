import datetime
from decimal import Decimal

from django.test import TestCase

from events.tests.generators import (CategoryFactory, Event2019Factory, OrgFactory, ServiceFactory,
                                     ServiceInstanceFactory)
from finance.calculators import (cash_flow_by_month, client_type_breakdown, project_composition,
                                 revenue_by_client, revenue_rows, service_mix, spend_by_category)
from finance.models import ClientType, ParsedTransaction, ProjectTag, WorkdayTransaction
from finance.tests.util import category, fund, revenue_source


FY26 = 2026
SEP = datetime.date(2025, 9, 15)
OCT = datetime.date(2025, 10, 15)


def bank(op, amount, date=SEP, org=None):
    """ ``org`` is the Student Organization worktag, which drives the partition. """
    worktags = {'ledger_account': '71100:Supplies'}
    if org:
        worktags['student_organization'] = org
    return WorkdayTransaction.objects.create(
        operational_transaction=op, accounting_date=date, net_amount=Decimal(amount),
        supplier='Test Supplier', worktags_json=worktags)


def slice_(parent, amount, date=None, **kwargs):
    return ParsedTransaction.objects.create(
        parent_transaction=parent, amount=Decimal(amount),
        effective_date=date or parent.accounting_date, **kwargs)


class SpendByCategoryTests(TestCase):
    def test_groups_and_ranks(self):
        slice_(bank('C1', '-100.00'), '-100.00', fund_source=fund('sga_budget'),
               lnl_spend_category=category('consumables'))
        slice_(bank('C2', '-400.00'), '-400.00', fund_source=fund('sga_budget'),
               lnl_spend_category=category('new_stuff'))
        rows = spend_by_category(fiscal_year=FY26)
        self.assertEqual([r['label'] for r in rows],
                         ['New Stuff', 'Consumables'])
        self.assertEqual(rows[0]['amount'], Decimal('400.00'))
        self.assertEqual(rows[0]['percent'], Decimal('80.0'))
        self.assertTrue(rows[0]['color'].startswith('#'))

    def test_refund_reduces_its_category(self):
        purchase = slice_(bank('C3', '-500.00'), '-500.00', fund_source=fund('sga_budget'),
                          lnl_spend_category=category('consumables'))
        slice_(bank('C4', '200.00'), '200.00', refund_of=purchase, fund_source=fund('sga_budget'),
               lnl_spend_category=category('consumables'))
        rows = spend_by_category(fiscal_year=FY26)
        self.assertEqual(rows[0]['amount'], Decimal('300.00'))

    def test_respects_the_projection_partition(self):
        slice_(bank('C5', '-100.00', org='315-AG'), '-100.00', fund_source=fund('sga_budget'),
               lnl_spend_category=category('repairs'))
        slice_(bank('C6', '-700.00'), '-700.00', fund_source=fund('sga_budget'),
               lnl_spend_category=category('consumables'))
        self.assertEqual([r['label'] for r in spend_by_category(FY26, is_projection=True)],
                         ['Repairs'])
        self.assertEqual([r['label'] for r in spend_by_category(FY26, is_projection=False)],
                         ['Consumables'])


class CashFlowTests(TestCase):
    def test_separates_money_in_from_money_out(self):
        slice_(bank('F1', '500.00', SEP), '500.00', non_event_revenue_type=revenue_source('alumni'))
        slice_(bank('F2', '-200.00', SEP), '-200.00', fund_source=fund('sga_budget'))
        rows = cash_flow_by_month(fiscal_year=FY26)
        sept = [r for r in rows if r['label'] == 'Sep 25'][0]
        self.assertEqual(sept['revenue'], Decimal('500.00'))
        self.assertEqual(sept['expense'], Decimal('200.00'))
        self.assertEqual(sept['net'], Decimal('300.00'))

    def test_covers_the_whole_fiscal_year(self):
        rows = cash_flow_by_month(fiscal_year=FY26)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0]['label'], 'Jul 25')
        self.assertEqual(rows[-1]['label'], 'Jun 26')

    def test_rolling_window_has_exactly_the_months_asked_for(self):
        for months in (3, 6, 12):
            rows = cash_flow_by_month(months=months)
            self.assertEqual(len(rows), months, '%s months requested' % months)
        # ...and ends on the current month.
        self.assertEqual(cash_flow_by_month(months=6)[-1]['label'],
                         datetime.date.today().strftime('%b %y'))

    def test_quiet_months_are_still_present(self):
        slice_(bank('F3', '500.00', OCT), '500.00', non_event_revenue_type=revenue_source('alumni'))
        rows = cash_flow_by_month(fiscal_year=FY26)
        july = [r for r in rows if r['label'] == 'Jul 25'][0]
        self.assertEqual(july['revenue'], Decimal('0.00'))
        self.assertEqual(july['expense'], Decimal('0.00'))


class RevenueBreakdownTests(TestCase):
    def setUp(self):
        self.lighting = CategoryFactory.create(name='Lighting')
        self.sound = CategoryFactory.create(name='Sound')

        self.student_org = OrgFactory.create(name='Student Activities Board', shortname='SAB',
                                             workday_fund=810)
        self.dept = OrgFactory.create(name='Office of Student Life', shortname='OSL',
                                      workday_fund=110)

        self.show_a = Event2019Factory.create(event_name='Fall Concert', billing_org=self.student_org)
        self.show_b = Event2019Factory.create(event_name='Dept Gala', billing_org=self.dept)

        # Lighting is priced at 3x sound, so revenue splits 75/25.
        ServiceInstanceFactory.create(
            event=self.show_a,
            service=ServiceFactory.create(category=self.lighting, base_cost=Decimal('300.00')))
        ServiceInstanceFactory.create(
            event=self.show_a,
            service=ServiceFactory.create(category=self.sound, base_cost=Decimal('100.00')))
        ServiceInstanceFactory.create(
            event=self.show_b,
            service=ServiceFactory.create(category=self.lighting, base_cost=Decimal('500.00')))

        slice_(bank('R1', '800.00'), '800.00', linked_event=self.show_a)
        slice_(bank('R2', '600.00'), '600.00', linked_event=self.show_b)
        slice_(bank('R3', '250.00'), '250.00', non_event_revenue_type=revenue_source('sga_baseline'))

    def test_revenue_rows_resolve_polymorphic_events(self):
        rows = revenue_rows(fiscal_year=FY26)
        self.assertEqual(len(rows), 3)
        linked = [r for r in rows if r['event'] is not None]
        self.assertEqual(len(linked), 2)
        # Must come back as Event2019, not a bare BaseEvent, or workday_fund
        # would be invisible.
        self.assertTrue(all(hasattr(r['event'], 'workday_fund') for r in linked))

    def test_revenue_by_client_ranks_and_includes_non_event(self):
        rows = revenue_by_client(fiscal_year=FY26)
        labels = [r['label'] for r in rows]
        self.assertEqual(labels[0], 'SAB')             # 800, biggest
        self.assertEqual(rows[0]['amount'], Decimal('800.00'))
        self.assertIn('OSL', labels)
        self.assertIn('SGA Baseline', labels)          # non-event kept, labelled

    def test_revenue_by_client_rolls_up_the_tail(self):
        for index in range(6):
            org = OrgFactory.create(name='Tiny Org %s' % index, workday_fund=810)
            event = Event2019Factory.create(billing_org=org)
            slice_(bank('T%s' % index, '10.00'), '10.00', linked_event=event)
        rows = revenue_by_client(fiscal_year=FY26, limit=3)
        self.assertEqual(len(rows), 4)                  # 3 + an "others" row
        self.assertIn('others', rows[-1]['label'])

    def test_client_type_breakdown(self):
        rows = {r['key']: r for r in client_type_breakdown(fiscal_year=FY26)}
        self.assertEqual(rows[ClientType.STUDENT_ORG]['amount'], Decimal('800.00'))
        self.assertEqual(rows[ClientType.DEPARTMENT]['amount'], Decimal('600.00'))
        self.assertEqual(rows[ClientType.STUDENT_ORG]['shows'], 1)
        # Non-event revenue has no client and must not be bucketed as Unknown.
        self.assertEqual(sum(r['amount'] for r in rows.values()), Decimal('1400.00'))

    def test_service_mix_splits_revenue_by_list_price(self):
        rows = {r['label']: r for r in service_mix(fiscal_year=FY26)}
        # Show A: 800 split 300:100 -> 600 lighting / 200 sound.
        # Show B: 600 all lighting.
        self.assertEqual(rows['Lighting']['amount'], Decimal('1200.00'))
        self.assertEqual(rows['Sound']['amount'], Decimal('200.00'))
        self.assertEqual(rows['Lighting']['shows'], 2)
        self.assertEqual(rows['Sound']['shows'], 1)

    def test_service_mix_totals_match_linked_revenue(self):
        total = sum(r['amount'] for r in service_mix(fiscal_year=FY26))
        self.assertEqual(total, Decimal('1400.00'))

    def test_shows_without_services_are_grouped_not_dropped(self):
        bare = Event2019Factory.create(event_name='No services', billing_org=self.dept)
        slice_(bank('R4', '90.00'), '90.00', linked_event=bare)
        rows = {r['label']: r for r in service_mix(fiscal_year=FY26)}
        self.assertEqual(rows['Unspecified']['amount'], Decimal('90.00'))

    def test_one_revenue_pass_can_be_shared(self):
        """ The view resolves events once and hands the rows to each widget. """
        rows = revenue_rows(fiscal_year=FY26)
        self.assertEqual(revenue_by_client(rows=rows), revenue_by_client(fiscal_year=FY26))
        self.assertEqual(client_type_breakdown(rows=rows), client_type_breakdown(fiscal_year=FY26))
        self.assertEqual(service_mix(rows=rows), service_mix(fiscal_year=FY26))


class ProjectCompositionTests(TestCase):
    def setUp(self):
        self.nel = ProjectTag.objects.create(name='New Equipment List', code='NEL26')
        self.lustr = ProjectTag.objects.create(name='D60 Lustrs', code='D60', parent=self.nel)
        self.cable = ProjectTag.objects.create(name='Cable', code='CBL', parent=self.nel)
        self.booth = ProjectTag.objects.create(name='Booth Refit', code='BOOTH', is_projection=True)

    def _spend(self, tag, amount, op, **kwargs):
        return slice_(bank(op, amount), amount, fund_source=fund('sga_budget'),
                      lnl_spend_category=category('new_stuff'), project_tag=tag, **kwargs)

    def test_segments_are_child_assets_biggest_first(self):
        self._spend(self.lustr, '-8000.00', 'P1')
        self._spend(self.cable, '-1000.00', 'P2')
        rows = project_composition(fiscal_year=FY26)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['total'], Decimal('9000.00'))
        self.assertEqual([s['label'] for s in rows[0]['segments']], ['D60 Lustrs', 'Cable'])
        self.assertEqual(rows[0]['segments'][0]['percent'], Decimal('88.9'))

    def test_spending_tagged_to_the_parent_becomes_a_direct_segment(self):
        self._spend(self.lustr, '-1000.00', 'P3')
        self._spend(self.nel, '-500.00', 'P4')
        rows = project_composition(fiscal_year=FY26)
        labels = [s['label'] for s in rows[0]['segments']]
        self.assertIn('Direct', labels)
        # The bar total still equals the project's fully-loaded cost.
        self.assertEqual(rows[0]['total'], Decimal('1500.00'))
        self.assertEqual(rows[0]['total'], self.nel.total_cost(fiscal_year=FY26))

    def test_empty_projects_are_omitted(self):
        self.assertEqual(project_composition(fiscal_year=FY26), [])

    def test_partition_filter_selects_projection_projects(self):
        self._spend(self.lustr, '-100.00', 'P5')
        self._spend(self.booth, '-200.00', 'P6', is_projection=True)
        event_side = project_composition(fiscal_year=FY26, is_projection=False)
        proj_side = project_composition(fiscal_year=FY26, is_projection=True)
        self.assertEqual([p['code'] for p in event_side], ['NEL26'])
        self.assertEqual([p['code'] for p in proj_side], ['BOOTH'])

    def test_only_top_level_projects_get_their_own_bar(self):
        self._spend(self.lustr, '-100.00', 'P7')
        rows = project_composition(fiscal_year=FY26)
        self.assertEqual([p['code'] for p in rows], ['NEL26'])

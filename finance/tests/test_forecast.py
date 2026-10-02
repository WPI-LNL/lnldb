"""
The forecast: today's balances carried forward to the end of next fiscal
year, and the pages built on it.

Five layers, tested from the bottom up:

* **A typical year.** The median of the most recent whole years, spread over
  the months the way they spread it; billing from before FY27 scaled to the
  departments' share, or left out when nobody knows it.
* **How long money takes.** SGA's repayment and a client's payment, measured
  from the ledger once it has enough cases.
* **The projection**, against a ledger small enough to add up by hand: what
  is reserved, owed, booked and planned, a typical year on top without
  counting anything twice, a budget going back at year end, and the verdict
  against the reserve.
* **How a typical year would have done**, asked of the past.
* **The pages**: the Forecast tab, "Can we afford it?", planned purchases,
  the printable forecast, the draft budget and the dashboard's panel.
"""
import datetime
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from events.models import Billing, Rental
from events.tests.generators import Event2019Factory, OrgFactory
from finance import forecast, history, reports
from finance.history import Flow
from finance.models import (FinanceSettings, FRLineItem, FundingRequest, HistoryKind,
                            HistoryOverride, ParsedTransaction, PlannedPurchase,
                            TransactionStatus, reset_finance_cache)
from finance.tests.test_balances import checkpoint, filed, line
from finance.tests.test_history import old, start_books
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund, revenue_source

TODAY = datetime.date(2026, 10, 1)
ZERO = Decimal('0.00')


def flow(day, amount, kind=HistoryKind.SPENDING, slug='consumables', **extra):
    """ One flow on 226-AG, without a database line behind it. """
    return Flow(day, Decimal(amount), kind,
                category=category(slug).pk if kind == HistoryKind.SPENDING else None,
                account='226-AG', **extra)


def share(fraction):
    return history.DepartmentShare(Decimal(fraction), 'set')


def set_config(**values):
    config = FinanceSettings.load()
    for name, value in values.items():
        setattr(config, name, value)
    config.save()
    reset_finance_cache()


class ForecastTestCase(TestCase):
    """ Clean caches either side of every test. """

    def setUp(self):
        super(ForecastTestCase, self).setUp()
        reset_finance_cache()
        self.addCleanup(reset_finance_cache)
        self.categories = history.spending_categories()


# ---------------------------------------------------------------------------
# A typical year
# ---------------------------------------------------------------------------

class TypicalYearTests(ForecastTestCase):
    """ The median of recent whole years, spread over the months they spread it. """

    def typical(self, flows, target=2027, years=(2024, 2025, 2026), share_=None, count=3):
        return forecast.TypicalYear(flows, self.categories, target, list(years),
                                    share=share_, count=count)

    def test_the_median_year_spread_as_the_years_spread_it(self):
        flows = [flow(datetime.date(2023, 9, 1), '-300.00'),       # FY24
                 flow(datetime.date(2024, 9, 1), '-100.00'),       # FY25
                 flow(datetime.date(2025, 3, 1), '-200.00'),       # FY25
                 flow(datetime.date(2025, 9, 1), '-1000.00')]      # FY26
        typical = self.typical(flows)
        stream = ('category', category('consumables').pk)
        self.assertEqual(typical.annual[stream], Decimal('-300.00'))
        # Of $1,600 over the three years, $1,400 went out in September.
        self.assertEqual(typical.month(stream, 9), Decimal('-262.50'))
        self.assertEqual(typical.month(stream, 3), Decimal('-37.50'))
        self.assertEqual(typical.month(stream, 1), ZERO)
        self.assertEqual(typical.in_year(stream, 2026, 9), Decimal('-1000.00'))
        self.assertEqual(typical.span, 'FY24-FY26')

    def test_only_the_newest_whole_years_count(self):
        flows = [flow(datetime.date(2020, 9, 1), '-9000.00'),
                 flow(datetime.date(2024, 9, 1), '-100.00')]
        typical = self.typical(flows, years=(2021, 2023, 2024, 2025))
        self.assertEqual(typical.years, [2025, 2024, 2023])
        self.assertEqual(typical.annual[('category', category('consumables').pk)],
                         ZERO)

    def test_billing_before_fy27_counts_at_the_departments_share(self):
        flows = [flow(datetime.date(2025, 8, 1), '1000.00', HistoryKind.BILLING),
                 flow(datetime.date(2025, 8, 2), '-400.00', slug='event_subrental')]
        typical = self.typical(flows, years=(2026,), share_=share('0.6'))
        self.assertEqual(typical.annual[forecast.BILLING], Decimal('600.00'))
        self.assertEqual(typical.annual[forecast.PASSTHROUGH], Decimal('-240.00'))
        self.assertTrue(typical.scaled)

    def test_left_out_when_nobody_knows_the_share(self):
        flows = [flow(datetime.date(2025, 8, 1), '1000.00', HistoryKind.BILLING),
                 flow(datetime.date(2025, 8, 2), '-400.00', slug='event_subrental'),
                 flow(datetime.date(2025, 9, 1), '-50.00')]
        typical = self.typical(flows, years=(2026,))
        self.assertEqual(typical.dropped, {forecast.BILLING, forecast.PASSTHROUGH})
        self.assertEqual(typical.streams, [('category', category('consumables').pk)])

    def test_nothing_is_scaled_for_a_year_before_fy27(self):
        flows = [flow(datetime.date(2024, 8, 1), '1000.00', HistoryKind.BILLING)]
        typical = self.typical(flows, target=2026, years=(2025,))
        self.assertEqual(typical.annual[forecast.BILLING], Decimal('1000.00'))
        self.assertFalse(typical.dropped or typical.scaled)

    def test_what_a_typical_year_leaves_out(self):
        day = datetime.date(2025, 9, 1)
        left_out = [flow(day, '500.00', HistoryKind.SGA),
                    flow(day, '500.00', HistoryKind.OTHER),
                    flow(day, '-500.00', sga_paid=True),
                    flow(day, '-500.00', left_out=True),
                    flow(day, '-500.00', slug='equipment_capital'),
                    flow(day, '-500.00', slug='equipment_noncapital')]
        for item in left_out:
            self.assertIsNone(forecast.stream_for(item, self.categories), item)
        self.assertEqual(forecast.stream_for(flow(day, '-5.00'), self.categories),
                         ('category', category('consumables').pk))


# ---------------------------------------------------------------------------
# How long money takes
# ---------------------------------------------------------------------------

def request_line(reference):
    request = FundingRequest.objects.create(name=reference, reference=reference,
                                            fiscal_year=2026)
    return FRLineItem.objects.create(funding_request=request, name='Things',
                                     amount_awarded=Decimal('5000.00'))


def spend_on(fr_line, day, amount):
    txn = line(day, '-%s' % amount, 'Spending on %s' % fr_line.funding_request.reference)
    return filed(txn, 'sga_fr', lnl_spend_category=category('consumables'),
                 fr_line_target=fr_line)


def repaid(fr_line, day, amount):
    txn = line(day, amount, '%s repaid' % fr_line.funding_request.reference)
    return filed(txn, 'sga_fr', non_event_revenue_type=revenue_source('sga_fr_reimbursement'),
                 funding_request=fr_line.funding_request)


class WaitTests(ForecastTestCase):
    """ Measured once the ledger has two cases; assumed until then. """

    def setUp(self):
        super(WaitTests, self).setUp()
        start_books()

    def test_sga_is_assumed_to_take_thirty_days_until_measured(self):
        wait = forecast.sga_wait()
        self.assertEqual((wait.days, wait.is_measured), (forecast.DEFAULT_SGA_DAYS, False))
        self.assertEqual(wait.after('the spending'),
                         '30 days after the spending (assumed until the ledger has 2 to measure)')

    def test_sga_measured_from_the_last_spending_before_each_payment(self):
        first, second = request_line('F.26.1'), request_line('F.26.2')
        spend_on(first, datetime.date(2025, 9, 1), '100.00')
        spend_on(first, datetime.date(2025, 9, 10), '100.00')
        repaid(first, datetime.date(2025, 10, 10), '200.00')          # 30 days
        spend_on(second, datetime.date(2025, 11, 1), '100.00')
        repaid(second, datetime.date(2025, 12, 21), '100.00')         # 50 days
        wait = forecast.sga_wait()
        self.assertEqual((wait.days, wait.measured, wait.is_measured), (40, 2, True))
        self.assertIn('median of 2', wait.after('the spending'))

    def test_clients_measured_from_the_show_to_the_payment(self):
        for name, ran, paid in (('A', datetime.date(2025, 9, 1), datetime.date(2025, 9, 21)),
                                ('B', datetime.date(2025, 10, 1), datetime.date(2025, 11, 10))):
            event = Event2019Factory.create(event_name=name)
            event.datetime_start = datetime.datetime(ran.year, ran.month, ran.day, 19,
                                                     tzinfo=datetime.timezone.utc)
            event.save()
            filed(line(paid, '300.00', 'LNL Services for %s' % name), 'legacy',
                  linked_event=event)
        self.assertEqual(forecast.bill_wait().days, 30)


# ---------------------------------------------------------------------------
# The projection
# ---------------------------------------------------------------------------

class ProjectionFixture(object):
    """
    Three whole years and a little of a fourth, on 226-AG.

    Each month of FY24, FY25 and FY26 buys tape -- $300 a month in FY24 and
    $100 a month since -- and each August brings in $1,000 of billing. FY27 so
    far is one $50 line on Sep 30, and Workday says the account held $20,000
    that night. The books start on Jul 1, 2025, so FY24 and FY25 are history.

    A typical year is therefore $1,200 of tape, $100 a month, and $1,000 of
    billing in August, at the departments' share once one is set. Today is Oct
    1, 2026: the forecast runs from October 2026 to June 2028, 21 months.
    """

    def build(self):
        start_books()
        for fy, tape in ((2024, '-300.00'), (2025, '-100.00'), (2026, '-100.00')):
            for month in range(1, 13):
                year = fy - 1 if month >= 7 else fy
                old(datetime.date(year, month, 15), tape, 'Gaff tape', supplier='B&H',
                    spend_category='Supplies')
            old(datetime.date(fy - 1, 8, 20), '1000.00', 'LNL Services for Orientation',
                ledger_account='70050:Internal Service Provider Revenue')
        old(datetime.date(2026, 9, 30), '-50.00', 'Gaff tape', supplier='B&H',
            spend_category='Supplies')
        checkpoint('226-AG', datetime.date(2026, 9, 30), '20000.00')

    def project(self, **kwargs):
        kwargs.setdefault('today', TODAY)
        return forecast.project(**kwargs)

    def month(self, result, year, month):
        return next(m for m in result.months if (m.first.year, m.first.month) == (year, month))


class ProjectionTests(ProjectionFixture, ForecastTestCase):
    """ The typical year alone, against figures that add up by hand. """

    def setUp(self):
        super(ProjectionTests, self).setUp()
        self.build()

    def test_no_workday_balance_no_forecast(self):
        from finance.models import BalanceCheckpoint

        BalanceCheckpoint.objects.all().delete()
        result = self.project()
        self.assertFalse(result.available)
        self.assertIn('Enter a Workday balance', result.problem)

    def test_it_starts_from_todays_own_money_and_runs_to_next_june(self):
        result = self.project()
        self.assertTrue(result.available)
        self.assertEqual(result.opening_own, Decimal('20000.00'))
        self.assertEqual(result.opening_cash, Decimal('20000.00'))
        self.assertEqual(result.since, datetime.date(2026, 9, 30))
        self.assertEqual(result.horizon, datetime.date(2028, 6, 30))
        self.assertEqual((len(result.months), result.months[0].label, result.months[-1].label),
                         (21, 'Oct 2026', 'Jun 2028'))

    def test_with_no_share_billing_is_left_out_and_said_so(self):
        result = self.project()
        self.assertEqual(self.month(result, 2027, 6).own, Decimal('19100.00'))
        self.assertEqual(self.month(result, 2028, 6).own, Decimal('17900.00'))
        self.assertTrue(any("departments' share" in w for w in result.warnings))

    def test_billing_counts_at_the_departments_share(self):
        set_config(department_billing_share=50)
        result = self.project()
        august = self.month(result, 2027, 8)
        self.assertEqual(august.flows['typical'], Decimal('400.00'))     # $500 in, $100 tape
        self.assertEqual(self.month(result, 2028, 6).own, Decimal('18400.00'))
        self.assertFalse(result.warnings)
        self.assertTrue(any('50%' in note for note in result.notes))

    def test_the_range_runs_from_the_weakest_year_to_the_strongest(self):
        result = self.project()
        june = self.month(result, 2028, 6)
        # Twenty-one months of FY24's $300 a month, against the typical $100.
        self.assertEqual((june.low, june.high), (Decimal('13700.00'), Decimal('17900.00')))
        self.assertTrue(result.has_band)
        self.assertEqual(result.lowest_in_band, Decimal('13700.00'))

    def test_the_verdict_against_the_reserve(self):
        self.assertEqual(self.project().verdict, 'yes')
        set_config(minimum_reserve=Decimal('15000.00'))
        self.assertEqual(self.project().verdict, 'tight')
        set_config(minimum_reserve=Decimal('19000.00'))
        result = self.project()
        self.assertEqual(result.verdict, 'no')
        # $100 a month from $20,000: $19,000 at the end of July, $18,900 in August.
        self.assertEqual(result.months_below_reserve[0].label, 'Aug 2027')

    def test_room_to_spend_is_the_smallest_gap_to_the_reserve(self):
        result = self.project()
        self.assertEqual(result.low_point.label, 'Jun 2028')
        self.assertEqual(result.room, Decimal('7900.00'))

    def test_a_part_can_be_left_out(self):
        result = self.project(without=['typical'])
        self.assertEqual(self.month(result, 2028, 6).own, Decimal('20000.00'))
        self.assertFalse(result.has_band)
        self.assertIn(('typical', 'A typical year', False), result.components)

    def test_the_typical_rows_say_what_each_part_adds(self):
        result = self.project()
        (row,) = result.typical_rows
        self.assertEqual(row['label'], 'Consumables')
        self.assertEqual(row['annual'], Decimal('-1200.00'))
        self.assertEqual(row['by_year'], {2027: Decimal('-900.00'), 2028: Decimal('-1200.00')})
        self.assertEqual(row['past'][2024], Decimal('-3600.00'))

    def test_the_chart_lines_up_the_past_and_the_forecast(self):
        result = self.project()
        chart = result.chart()
        self.assertEqual(len(chart['labels']), len(chart['actual']))
        self.assertEqual(len(chart['labels']), len(chart['own']))
        self.assertEqual(chart['own'][-1], 17900.0)
        self.assertEqual(chart['reserve'], 10000.0)


class DatedTests(ProjectionFixture, ForecastTestCase):
    """ What is reserved, owed, booked and planned, each on its date. """

    def setUp(self):
        super(DatedTests, self).setUp()
        self.build()

    def items(self, result, component):
        return [(i.day, i.amount, i.fund) for i in result.items_in(component)]

    def test_a_reservation_on_own_money_stands_in_for_its_categorys_year(self):
        ParsedTransaction.objects.create(
            amount=Decimal('-1000.00'), effective_date=datetime.date(2026, 12, 1),
            status=TransactionStatus.PENDING, fund_source=fund('legacy'),
            lnl_spend_category=category('consumables'), description='Tape for the year')
        result = self.project()
        self.assertEqual(self.items(result, 'reserved'),
                         [(datetime.date(2026, 12, 1), Decimal('-1000.00'), forecast.OWN)])
        # The rest of FY27's tape ($900) is inside the $1,000 already reserved.
        self.assertEqual(self.month(result, 2027, 6).own, Decimal('19000.00'))
        self.assertEqual(self.month(result, 2028, 6).own, Decimal('17800.00'))

    def test_a_reservation_on_a_funding_request_comes_back_from_sga(self):
        ParsedTransaction.objects.create(
            amount=Decimal('-500.00'), effective_date=datetime.date(2026, 11, 1),
            status=TransactionStatus.PENDING, fund_source=fund('sga_fr'),
            lnl_spend_category=category('consumables'), description='Gels')
        result = self.project()
        fr = fund('sga_fr').pk
        self.assertEqual(self.items(result, 'reserved'),
                         [(datetime.date(2026, 11, 1), Decimal('-500.00'), fr),
                          (datetime.date(2026, 12, 1), Decimal('500.00'), fr)])
        november = self.month(result, 2026, 11)
        self.assertEqual(november.cash - november.own, Decimal('-500.00'))
        self.assertEqual(self.month(result, 2027, 6).own, Decimal('19100.00'))

    def test_what_sga_owes_arrives_after_the_wait(self):
        spend_on(request_line('F.27.9'), datetime.date(2026, 9, 20), '800.00')
        result = self.project()
        fr = fund('sga_fr').pk
        self.assertEqual(result.opening[fr], Decimal('-800.00'))
        self.assertEqual(self.items(result, 'owed'),
                         [(datetime.date(2026, 10, 20), Decimal('800.00'), fr)])
        self.assertEqual(self.month(result, 2026, 10).funds[fr], ZERO)

    def test_what_sga_owes_long_since_arrives_as_soon_as_it_can(self):
        spend_on(request_line('F.26.9'), datetime.date(2026, 3, 1), '800.00')
        result = self.project()
        self.assertEqual(self.items(result, 'owed')[0][0], datetime.date(2026, 10, 1))

    def booked(self, name, day, workday_fund=None, rentals=(), billed=None):
        org = OrgFactory.create(name='%s client' % name, workday_fund=workday_fund)
        event = Event2019Factory.create(event_name=name, billing_org=org, approved=True)
        event.datetime_start = datetime.datetime(day.year, day.month, day.day, 19,
                                                 tzinfo=datetime.timezone.utc)
        event.datetime_end = event.datetime_start + datetime.timedelta(hours=3)
        event.save()
        for cost in rentals:
            Rental.objects.create(event=event, name='Truss', cost=Decimal(cost))
        if billed:
            Billing.objects.create(event=event, date_billed=day, amount=Decimal(billed))
        return event

    def test_a_departments_show_brings_in_its_quote_and_pays_for_its_gear(self):
        self.booked('Convocation', datetime.date(2027, 2, 10), 110, rentals=['400.00'])
        with mock.patch('finance.forecast._quote', return_value=Decimal('1500.00')):
            result = self.project()
        self.assertEqual(self.items(result, 'events'),
                         [(datetime.date(2027, 2, 10), Decimal('-400.00'), forecast.OWN),
                          (datetime.date(2027, 3, 12), Decimal('1500.00'), forecast.OWN)])
        self.assertEqual((result.events_booked, result.events_counted), (1, 1))
        self.assertEqual(self.month(result, 2027, 6).own, Decimal('20200.00'))

    def test_a_student_organizations_show_is_paid_for_by_a_funding_request(self):
        self.booked('Spring Musical', datetime.date(2027, 3, 5), 810, rentals=['600.00'])
        with mock.patch('finance.forecast._quote', return_value=Decimal('900.00')):
            result = self.project()
        fr = fund('sga_fr').pk
        self.assertEqual(self.items(result, 'events'),
                         [(datetime.date(2027, 3, 5), Decimal('-600.00'), fr),
                          (datetime.date(2027, 4, 4), Decimal('600.00'), fr)])
        self.assertEqual(self.month(result, 2027, 6).own, Decimal('19100.00'))

    def test_a_show_with_no_client_on_file_pays_for_its_own_gear(self):
        self.booked('Mystery', datetime.date(2027, 3, 5), None, rentals=['250.00'])
        result = self.project()
        self.assertEqual(self.items(result, 'events'),
                         [(datetime.date(2027, 3, 5), Decimal('-250.00'), forecast.OWN)])

    def test_a_billed_show_is_owed_rather_than_booked(self):
        self.booked('Gala', datetime.date(2027, 1, 20), 110, rentals=['100.00'], billed='700.00')
        result = self.project()
        self.assertEqual(self.items(result, 'events'), [])
        self.assertEqual(self.items(result, 'owed'),
                         [(datetime.date(2027, 2, 19), Decimal('700.00'), forecast.OWN)])

    def test_booked_billing_counts_instead_of_a_typical_month_not_on_top(self):
        set_config(department_billing_share=50)
        # Paid in August 2027, when a typical year brings in $500.
        self.booked('Orientation', datetime.date(2027, 7, 15), 110)
        with mock.patch('finance.forecast._quote', return_value=Decimal('800.00')):
            result = self.project()
        august = self.month(result, 2027, 8)
        self.assertEqual(august.flows['events'], Decimal('800.00'))
        self.assertEqual(august.flows['typical'], Decimal('-100.00'))

    def test_planned_purchases_count_until_bought_or_dropped(self):
        for status in (PlannedPurchase.PLANNED, PlannedPurchase.DROPPED):
            PlannedPurchase.objects.create(
                name='Console (%s)' % status, amount=Decimal('5000.00'),
                expected_date=datetime.date(2027, 3, 1), fund_source=fund('legacy'),
                spend_category=category('equipment_capital'), status=status)
        result = self.project()
        self.assertEqual(self.items(result, 'planned'),
                         [(datetime.date(2027, 3, 1), Decimal('-5000.00'), forecast.OWN)])
        self.assertEqual(self.month(result, 2027, 6).own, Decimal('14100.00'))
        self.assertEqual(self.project(without=['planned']).months[-1].own, Decimal('17900.00'))

    def test_a_what_if_counts_whatever_the_switches_say(self):
        what_if = PlannedPurchase(name='Moving head', amount=Decimal('3000.00'),
                                  expected_date=datetime.date(2027, 1, 15),
                                  fund_source=fund('legacy'))
        result = self.project(without=['planned'], extra=[what_if])
        (item,) = result.items_in('planned')
        self.assertEqual((item.amount, item.label), (Decimal('-3000.00'), 'What if: Moving head'))

    def test_a_budget_left_unspent_goes_back_on_june_30(self):
        deposit = line(datetime.date(2026, 8, 1), '1000.00', 'SGA budget')
        filed(deposit, 'sga_budget', non_event_revenue_type=revenue_source('sga_baseline'))
        result = self.project()
        budget = fund('sga_budget').pk
        self.assertEqual(result.opening[budget], Decimal('1000.00'))
        self.assertEqual(self.items(result, 'year_end'),
                         [(datetime.date(2027, 6, 30), Decimal('-1000.00'), budget)])
        self.assertEqual(self.month(result, 2027, 6).funds[budget], ZERO)


class BackTestTests(ProjectionFixture, ForecastTestCase):
    """ What a typical year from the years before said, beside what happened. """

    def setUp(self):
        super(BackTestTests, self).setUp()
        self.build()

    def test_each_year_with_two_whole_years_before_it(self):
        rows = forecast.back_test(history.Ledger(), '226-AG', today=datetime.date(2026, 9, 30))
        self.assertEqual(len(rows), 1)
        (row,) = rows
        # From FY24 and FY25: a median $2,400 of tape, nine months of it left
        # after Sep 30, 2025; FY26 then spent $900, its August billing already in.
        self.assertEqual((row['year'], row['as_of'], row['from']),
                         (2026, datetime.date(2025, 9, 30), 'FY24-FY25'))
        self.assertEqual((row['predicted'], row['actual'], row['difference']),
                         (Decimal('-1800.00'), Decimal('-900.00'), Decimal('-900.00')))
        summary = forecast.back_test_summary(rows)
        self.assertEqual((summary['miss'], summary['percent'], summary['years']),
                         (Decimal('900.00'), 100, 1))

    def test_nothing_to_test_without_history(self):
        self.assertIsNone(forecast.back_test_summary([]))


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class ForecastPageTests(ProjectionFixture, FinanceViewTestCase):
    """ The Forecast tab and the pages built on it. """

    def setUp(self):
        super(ForecastPageTests, self).setUp()
        reset_finance_cache()
        self.addCleanup(reset_finance_cache)
        self.build()
        self.grant('view_subledger')

    def test_the_forecast_page(self):
        response = self.client.get(reverse('finance:forecast'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LNL's own money now")
        self.assertContains(response, 'A typical year')
        self.assertContains(response, 'fin-forecast-data')
        self.assertContains(response, 'How a typical year would have done')
        switch = next(s for s in response.context['switches'] if s['key'] == 'typical')
        self.assertIn('without=typical', switch['url'])
        left_out = self.client.get(reverse('finance:forecast') + '?without=typical')
        switch = next(s for s in left_out.context['switches'] if s['key'] == 'typical')
        self.assertFalse(switch['included'])
        self.assertNotIn('without=typical', switch['url'])

    def test_without_a_balance_the_page_says_what_to_do(self):
        from finance.models import BalanceCheckpoint

        BalanceCheckpoint.objects.all().delete()
        response = self.client.get(reverse('finance:forecast'))
        self.assertContains(response, 'Enter a Workday balance')

    def test_can_we_afford_it(self):
        self.assertContains(self.client.get(reverse('finance:afford')), 'What would you buy?')
        response = self.client.get(reverse('finance:afford'), {
            'name': 'Console', 'amount': '2000.00', 'expected_date': '2027-01-15',
            'fund_source': fund('legacy').pk})
        self.assertEqual(response.status_code, 200)
        answer = response.context['answer']
        self.assertEqual(answer['after'].room + Decimal('2000.00'), answer['before'].room)
        self.assertContains(response, 'Without it, and with it')
        # Only someone who can edit is offered to save it.
        self.assertNotContains(response, 'Add to planned purchases')

    def test_planning_a_purchase_needs_the_edit_permission(self):
        self.assertEqual(self.client.get(reverse('finance:plan-new')).status_code, 403)
        self.assertContains(self.client.get(reverse('finance:plans')), 'Nothing planned')

    def test_planning_changing_and_removing_a_purchase(self):
        self.grant('edit_subledger')
        response = self.client.post(reverse('finance:plan-new'), {
            'name': 'Console', 'amount': '5000.00', 'expected_date': '2027-03-01',
            'fund_source': fund('legacy').pk, 'status': 'planned', 'notes': ''})
        self.assertRedirects(response, reverse('finance:plans'), fetch_redirect_response=False)
        purchase = PlannedPurchase.objects.get()
        self.assertEqual((purchase.created_by, purchase.amount), (self.user, Decimal('5000.00')))
        self.assertContains(self.client.get(reverse('finance:plans')), 'Console')
        self.client.post(reverse('finance:plan-edit', args=[purchase.pk]), {
            'name': 'Console', 'amount': '5000.00', 'expected_date': '2027-03-01',
            'fund_source': fund('legacy').pk, 'status': 'bought', 'notes': ''})
        purchase.refresh_from_db()
        self.assertFalse(purchase.is_counted)
        self.client.post(reverse('finance:plan-delete', args=[purchase.pk]))
        self.assertFalse(PlannedPurchase.objects.exists())

    def test_saving_an_answer_from_can_we_afford_it(self):
        self.grant('edit_subledger')
        response = self.client.get(reverse('finance:afford'), {
            'name': 'Hazer', 'amount': '800.00', 'expected_date': '2027-01-15',
            'fund_source': fund('legacy').pk})
        self.assertContains(response, 'Add to planned purchases')
        saves = dict(response.context['answer']['saves'])
        saves.update({'status': 'planned', 'next': reverse('finance:plans')})
        self.client.post(reverse('finance:plan-new'), saves)
        self.assertEqual(PlannedPurchase.objects.get().name, 'Hazer')

    def test_the_forecast_prints_and_downloads(self):
        url = reverse('finance:report', args=['forecast'])
        self.assertContains(self.client.get(url), 'Forecast for 226-AG')
        response = self.client.get(url + '?format=csv')
        # Named for the June the forecast runs to, which depends on today.
        self.assertRegex(response['Content-Disposition'],
                         r'^attachment; filename="lnl-forecast-to-fy\d\d\.csv"$')
        self.assertIn("LNL's own money", response.content.decode('utf-8-sig'))

    def test_the_dashboard_shows_where_the_money_is_heading(self):
        response = self.client.get(reverse('finance:dashboard'))
        self.assertContains(response, "Where LNL's Own Money Is Heading")

    def test_the_tab_needs_the_view_permission(self):
        self.user.user_permissions.clear()
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        for name in ('forecast', 'afford', 'plans', 'history'):
            self.assertEqual(self.client.get(reverse('finance:%s' % name)).status_code, 403,
                             name)


class BudgetDraftTests(ProjectionFixture, ForecastTestCase):
    """ Next year's budget request, from three whole years of spending. """

    def setUp(self):
        super(BudgetDraftTests, self).setUp()
        self.build()
        capital = old(datetime.date(2025, 3, 1), '-1234.01', 'Moving head', supplier='Vendor')
        HistoryOverride.objects.create(line=capital, spend_category=category('equipment_capital'))
        old(datetime.date(2024, 3, 1), '-500.00', 'Cables', supplier='Vendor',
            spend_category='Audio Visual Equipment')

    def test_rounding_up_to_the_next_fifty(self):
        self.assertEqual(reports._round_up(Decimal('1234.01')), Decimal('1250'))
        self.assertEqual(reports._round_up(Decimal('1200.00')), Decimal('1200'))
        self.assertEqual(reports._round_up(ZERO), ZERO)

    def test_each_line_is_the_median_of_three_years(self):
        built = reports.budget_draft(today=TODAY)
        self.assertEqual(built.title, 'Draft budget request for FY28')
        (section,) = built.sections
        rows = {row.cells['line']: row.cells for row in section.rows}
        tape = rows['Consumables']
        self.assertEqual((tape['fy2024'], tape['fy2025'], tape['fy2026'], tape['so_far']),
                         (Decimal('3600.00'), Decimal('1200.00'), Decimal('1200.00'),
                          Decimal('50.00')))
        self.assertEqual((tape['median'], tape['proposed']),
                         (Decimal('1200.00'), Decimal('1200')))
        # Capital and the rest of equipment are one line: history cannot tell them apart.
        equipment = rows['Equipment - Capital and Equipment - Non Capital']
        self.assertEqual((equipment['fy2024'], equipment['fy2025'], equipment['median'],
                          equipment['proposed']),
                         (Decimal('500.00'), Decimal('1234.01'), Decimal('500.00'),
                          Decimal('500')))
        self.assertEqual(section.total.cells['proposed'], Decimal('1700'))

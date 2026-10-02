"""
Reports, and what an event's costs mean when SGA pays for them.

Five layers, tested from the bottom up:

* **Costs SGA pays for.** A cost filed to a funding request or the SGA budget
  is still the event's cost, but not LNL's: it does not count against the
  margin, cannot make an event a loss, and is not set against event billing.
* **The period.** A fiscal year, the part of one so far, any dates, or every
  year -- and the same dates a year earlier to compare against.
* **The reports.** Income and spending year over year, fund balances, events,
  and what LNL is owed, each checked against figures small enough to add up
  by hand.
* **The CSV**, which a spreadsheet has to be able to sum.
* **The pages**: the Reports tab, each report, and the ledger's download.
"""
import csv
import datetime
import io
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from events.models import Billing
from events.tests.generators import Event2019Factory, OrgFactory
from finance import balances
from finance.calculators import event_billing_kept, event_financials, event_pnl_rows
from finance.models import FiscalYearClose, FRLineItem, FundingRequest, ParsedTransaction
from finance.reports import (AGE_BANDS, Column, Period, Report, Row, Section, age_band,
                             as_csv, event_report, fund_balances, income_and_spending,
                             owed_to_lnl, parse_period)
from finance.tests.test_balances import LedgerFixture, checkpoint, filed, line
from finance.tests.test_revenue_sources import (CacheResetMixin, make_request, reimburse,
                                                spend, take_back)
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund, revenue_source

TODAY = datetime.date(2026, 10, 1)


def when(year, month, day):
    return datetime.datetime(year, month, day, 19, 0, tzinfo=datetime.timezone.utc)


def client(name, student=False):
    """ A client: a student organization pays from Workday fund 810. """
    return OrgFactory.create(name=name, workday_fund=810 if student else 110)


def show(name, start, billing_org):
    """ An event that ran on ``start``, billed to ``billing_org``. """
    event = Event2019Factory.create(event_name=name, billing_org=billing_org)
    event.datetime_start = start
    event.datetime_end = start + datetime.timedelta(hours=3)
    event.save()
    return event


def bill(event, amount, date):
    return Billing.objects.create(event=event, date_billed=date, amount=Decimal(amount))


def income(event, amount, date):
    """ A deposit on 226-AG filed against an event. """
    txn = line(date, amount, 'Lens and Lights Services for %s' % event.event_name)
    return filed(txn, 'legacy', linked_event=event)


def cost(amount, date, fund_slug='legacy', slug='consumables', **extra):
    """ Spending on 226-AG, filed to a fund and a category. """
    txn = line(date, '-%s' % amount, 'Spending')
    return filed(txn, fund_slug, lnl_spend_category=category(slug), **extra)


def request_line(reference='F.27.4', name='Student shows'):
    """ A funding request's one line, to charge spending to. """
    request = FundingRequest.objects.create(name=name, reference=reference, fiscal_year=2027)
    return FRLineItem.objects.create(funding_request=request, name='Rentals',
                                     amount_awarded=Decimal('10000.00'))


def cells(section, label, key='line'):
    """ The cells of the row whose first column reads ``label``. """
    for row in section.rows:
        if row.cells.get(key) == label:
            return row.cells
    raise AssertionError("No row %r in %s" % (label, section.title))


def section(report, title):
    for item in report.sections:
        if item.title == title:
            return item
    raise AssertionError("No section %r" % title)


def column_keys(report):
    return [column.key for column in report.columns]


# ---------------------------------------------------------------------------
# Costs SGA pays for
# ---------------------------------------------------------------------------

class SGAPaidCostTests(TestCase):
    """
    From FY27 LNL bills only departments, and a student organization's show is
    funded through LNL's funding requests. Its costs are real, but they are not
    LNL's, and the event must not read as a loss.
    """

    def setUp(self):
        self.event = show('Spring Fling', when(2026, 9, 12), client('SAB', student=True))
        self.line = request_line()

    def test_a_cost_on_a_funding_request_is_paid_by_sga(self):
        cost('2000.00', datetime.date(2026, 9, 14), 'sga_fr', 'event_subrental',
             linked_event=self.event, fr_line_target=self.line)
        figures = event_financials(self.event)
        self.assertEqual(figures['costs'], Decimal('2000.00'))
        self.assertEqual(figures['sga_funded'], Decimal('2000.00'))
        self.assertEqual(figures['lnl_costs'], Decimal('0.00'))
        self.assertEqual(figures['margin'], Decimal('0.00'))
        self.assertNotIn('loss', figures['flag_keys'])

    def test_a_hire_sga_paid_for_is_not_under_billed(self):
        from events.models import Rental
        cost('2000.00', datetime.date(2026, 9, 14), 'sga_fr', 'event_subrental',
             linked_event=self.event, fr_line_target=self.line)
        Rental.objects.create(event=self.event, name='LED wall', cost=Decimal('0.00'))
        self.assertNotIn('rental_under_billed', event_financials(self.event)['flag_keys'])

    def test_a_cost_on_the_budget_is_paid_by_sga_too(self):
        cost('300.00', datetime.date(2026, 9, 14), 'sga_budget', linked_event=self.event)
        self.assertEqual(event_financials(self.event)['sga_funded'], Decimal('300.00'))

    def test_lnls_own_money_spent_on_an_unbilled_show_is_still_a_loss(self):
        cost('150.00', datetime.date(2026, 9, 14), 'legacy', linked_event=self.event)
        figures = event_financials(self.event)
        self.assertEqual(figures['lnl_costs'], Decimal('150.00'))
        self.assertIn('loss', figures['flag_keys'])

    def test_the_two_are_told_apart_on_one_event(self):
        cost('2000.00', datetime.date(2026, 9, 14), 'sga_fr', linked_event=self.event,
             fr_line_target=self.line)
        cost('150.00', datetime.date(2026, 9, 15), 'legacy', linked_event=self.event)
        figures = event_financials(self.event)
        self.assertEqual((figures['costs'], figures['sga_funded'], figures['lnl_costs'],
                          figures['margin']),
                         (Decimal('2150.00'), Decimal('2000.00'), Decimal('150.00'),
                          Decimal('-150.00')))

    def test_the_whole_year_agrees_with_the_single_event(self):
        cost('2000.00', datetime.date(2026, 9, 14), 'sga_fr', linked_event=self.event,
             fr_line_target=self.line)
        row = event_pnl_rows(2027)[0]
        self.assertEqual((row['sga_funded'], row['lnl_costs']),
                         (Decimal('2000.00'), Decimal('0.00')))

    def test_billing_kept_leaves_out_a_hire_sga_paid_for(self):
        department = show('Gala', when(2026, 9, 20), client('Admissions'))
        income(department, '1000.00', datetime.date(2026, 9, 25))
        cost('400.00', datetime.date(2026, 9, 21), 'legacy', 'event_subrental',
             linked_event=department)
        cost('2000.00', datetime.date(2026, 9, 14), 'sga_fr', 'event_subrental',
             linked_event=self.event, fr_line_target=self.line)
        kept = event_billing_kept(2027)
        self.assertEqual((kept['gross'], kept['passthrough'], kept['kept']),
                         (Decimal('1000.00'), Decimal('400.00'), Decimal('600.00')))


# ---------------------------------------------------------------------------
# The period
# ---------------------------------------------------------------------------

class PeriodTests(TestCase):
    """ What a report covers, and what it is compared with. """

    def test_a_finished_year_is_the_whole_year(self):
        period = Period.for_fiscal_year(2026, TODAY)
        self.assertEqual((period.first, period.last),
                         (datetime.date(2025, 7, 1), datetime.date(2026, 6, 30)))
        self.assertEqual((period.label, period.file_part), ('FY26', 'fy26'))

    def test_a_running_year_stops_at_today(self):
        period = Period.for_fiscal_year(2027, TODAY)
        self.assertEqual(period.last, TODAY)
        self.assertEqual((period.label, period.file_part), ('FY27 to date', 'fy27-to-date'))
        self.assertEqual(period.dates, 'Jul 1, 2026 – Oct 1, 2026')

    def test_a_running_year_is_compared_with_the_same_dates_and_the_whole_last_year(self):
        period = Period.for_fiscal_year(2027, TODAY)
        earlier, full = period.year_earlier(), period.previous_full_year()
        self.assertEqual((earlier.first, earlier.last),
                         (datetime.date(2025, 7, 1), datetime.date(2025, 10, 1)))
        self.assertEqual(earlier.label, 'FY26, same dates')
        self.assertEqual((full.first, full.last),
                         (datetime.date(2025, 7, 1), datetime.date(2026, 6, 30)))
        self.assertEqual(full.label, 'FY26 in full')

    def test_a_finished_year_is_compared_with_the_last(self):
        period = Period.for_fiscal_year(2026, TODAY)
        self.assertEqual(period.year_earlier().label, 'FY25')
        self.assertIsNone(period.previous_full_year())

    def test_a_leap_day_goes_back_to_the_28th(self):
        period = Period(datetime.date(2028, 2, 29), datetime.date(2028, 3, 31))
        self.assertEqual(period.year_earlier().first, datetime.date(2027, 2, 28))

    def test_every_year_has_nothing_to_compare_with(self):
        period = Period()
        self.assertEqual((period.label, period.file_part), ('All years', 'all-years'))
        self.assertIsNone(period.year_earlier())

    def test_a_stretch_longer_than_a_year_is_not_compared(self):
        self.assertIsNone(Period(datetime.date(2024, 1, 1),
                                 datetime.date(2026, 1, 1)).year_earlier())

    def test_dates_win_over_the_year(self):
        period, error = parse_period(2027, '2026-03-01', '2026-03-31', TODAY)
        self.assertEqual((period.first, period.last, period.fiscal_year, error),
                         (datetime.date(2026, 3, 1), datetime.date(2026, 3, 31), None, ''))
        self.assertEqual(period.file_part, '2026-03-01-to-2026-03-31')

    def test_bad_dates_fall_back_to_the_year_and_say_so(self):
        period, error = parse_period(2027, 'March', '2026-03-31', TODAY)
        self.assertEqual(period.fiscal_year, 2027)
        self.assertIn('YYYY-MM-DD', error)

    def test_dates_the_wrong_way_round_say_so(self):
        period, error = parse_period(2027, '2026-04-01', '2026-03-01', TODAY)
        self.assertEqual(period.fiscal_year, 2027)
        self.assertIn('comes after', error)

    def test_no_year_and_no_dates_is_every_year(self):
        period, error = parse_period(None, '', '', TODAY)
        self.assertFalse(period.is_bounded)
        self.assertEqual(error, '')


# ---------------------------------------------------------------------------
# Income and spending
# ---------------------------------------------------------------------------

class IncomeAndSpendingTests(CacheResetMixin, TestCase):
    """
    FY26, which is where the books start:

    ===========  =========  =======================================
    Sep 10       -400       consumables
    Oct 10        +50       refund of the consumables
    Oct 20     +1,000       billing, a department
    Nov 5        +300       billing, a student organization
    Dec 1        +200       a gift
    Jan 15       -500       film rights, on F.26.86
    Feb 1        +500       SGA repays F.26.86
    Mar 1        -100       SGA takes back money for F.26.86
    ===========  =========  =======================================

    and FY27 so far: -700 on food on Aug 20, +250 billing a department on
    Sep 20, and a reservation of 999 that has not been charged.
    """

    def setUp(self):
        super(IncomeAndSpendingTests, self).setUp()
        department, student = client('Admissions'), client('SAB', student=True)
        self.consumables = cost('400.00', datetime.date(2025, 9, 10))
        refund_line = line(datetime.date(2025, 10, 10), '50.00', 'Credit')
        filed(refund_line, 'legacy', refund_of=self.consumables,
              lnl_spend_category=category('consumables'))
        income(show('Gala', when(2025, 10, 18), department), '1000.00',
               datetime.date(2025, 10, 20))
        income(show('Fling', when(2025, 11, 1), student), '300.00', datetime.date(2025, 11, 5))
        gift = line(datetime.date(2025, 12, 1), '200.00', 'Alumni gift')
        filed(gift, 'legacy', non_event_revenue_type=revenue_source('alumni'))
        self.request = make_request()
        line_item = self.request.line_items.first()
        rights = line(datetime.date(2026, 1, 15), '-500.00', 'Film rights')
        filed(rights, 'sga_fr', fr_line_target=line_item,
              lnl_spend_category=category('film_rights'))
        reimburse(self.request, '500.00', datetime.date(2026, 2, 1))
        take_back(self.request, '100.00', datetime.date(2026, 3, 1))

        cost('700.00', datetime.date(2026, 8, 20), slug='food')
        income(show('Open House', when(2026, 9, 18), department), '250.00',
               datetime.date(2026, 9, 20))
        ParsedTransaction.objects.create(
            amount=Decimal('-999.00'), effective_date=datetime.date(2026, 9, 1),
            fund_source=fund('legacy'), lnl_spend_category=category('food'))

    def report(self, fiscal_year=2027, **kwargs):
        return income_and_spending(Period.for_fiscal_year(fiscal_year, TODAY), **kwargs)

    def test_a_running_year_has_four_figures_a_line(self):
        self.assertEqual(column_keys(self.report()),
                         ['line', 'current', 'earlier', 'change', 'full'])

    def test_billing_is_split_by_who_was_billed(self):
        money_in = section(self.report(), 'Money in')
        self.assertEqual(cells(money_in, 'Event billing: departments')['full'],
                         Decimal('1000.00'))
        self.assertEqual(cells(money_in, 'Event billing: departments')['current'],
                         Decimal('250.00'))
        self.assertEqual(cells(money_in, 'Event billing: student organizations')['full'],
                         Decimal('300.00'))

    def test_money_sga_took_back_is_netted_off_the_reimbursements(self):
        report = self.report()
        repaid = cells(section(report, 'Money in'), 'SGA Funding Request Reimbursement')
        self.assertEqual(repaid['full'], Decimal('400.00'))
        self.assertEqual(section(report, 'Money in').total.cells['full'], Decimal('1900.00'))

    def test_spending_is_net_of_refunds_and_leaves_out_what_sga_took_back(self):
        money_out = section(self.report(), 'Money out')
        self.assertEqual(cells(money_out, 'Consumables')['full'], Decimal('350.00'))
        self.assertEqual(cells(money_out, 'Films Rights and Shipping')['full'],
                         Decimal('500.00'))
        self.assertEqual(money_out.total.cells['full'], Decimal('850.00'))

    def test_a_reservation_is_not_spending(self):
        self.assertEqual(cells(section(self.report(), 'Money out'), 'Food')['current'],
                         Decimal('700.00'))

    def test_the_same_dates_a_year_earlier(self):
        """ Jul 1 - Oct 1, 2025 holds the consumables, but not their Oct 10 refund. """
        money_out = section(self.report(), 'Money out')
        consumables = cells(money_out, 'Consumables')
        self.assertEqual((consumables['current'], consumables['earlier'], consumables['change']),
                         (Decimal('0.00'), Decimal('400.00'), Decimal('-400.00')))

    def test_the_net_is_money_in_less_money_out_in_every_column(self):
        net = section(self.report(), 'Net').total.cells
        self.assertEqual((net['current'], net['earlier'], net['full']),
                         (Decimal('-450.00'), Decimal('-400.00'), Decimal('1050.00')))
        self.assertEqual(net['change'], Decimal('-50.00'))

    def test_a_line_with_nothing_in_any_column_is_left_out(self):
        labels = [row.cells['line'] for row in section(self.report(), 'Money out').rows]
        self.assertNotIn('Merch', labels)

    def test_it_says_what_sga_took_back(self):
        report = self.report(2026)
        self.assertTrue(any('$100.00 SGA took back' in note for note in report.notes))

    def test_one_fund_only(self):
        report = self.report(fund=fund('sga_fr'))
        money_in = section(report, 'Money in')
        self.assertEqual([row.cells['line'] for row in money_in.rows],
                         ['SGA Funding Request Reimbursement'])
        self.assertEqual(section(report, 'Money out').total.cells['full'], Decimal('500.00'))
        self.assertTrue(report.filename.endswith('-sga_fr.csv'))

    def test_one_side_of_the_partition_only(self):
        report = self.report(is_projection=True)
        self.assertEqual(section(report, 'Net').total.cells['full'], Decimal('0.00'))

    def test_a_year_before_the_books_is_not_compared_against(self):
        """ FY25 ended before the ledger began: a column of zeros would mislead. """
        report = self.report(2026)
        self.assertEqual(column_keys(report), ['line', 'current'])
        self.assertTrue(any('Nothing is compared with FY25' in note for note in report.notes))

    def test_a_comparison_partly_before_the_books_says_so(self):
        report = income_and_spending(Period(datetime.date(2026, 5, 1),
                                            datetime.date(2026, 7, 31)))
        self.assertIn('earlier', column_keys(report))
        self.assertTrue(any('The ledger starts on Jul 1, 2025' in w for w in report.warnings))

    def test_lines_still_in_the_queue_are_counted_and_named(self):
        line(datetime.date(2026, 9, 2), '-75.00', 'Not yet filed')
        report = self.report()
        self.assertTrue(any('1 Workday line' in w and '-$75.00' in w for w in report.warnings))

    def test_any_dates(self):
        report = income_and_spending(Period(datetime.date(2025, 10, 1),
                                            datetime.date(2025, 10, 31)))
        money_in = section(report, 'Money in')
        self.assertEqual(money_in.total.cells['current'], Decimal('1000.00'))
        self.assertEqual(cells(section(report, 'Money out'), 'Consumables')['current'],
                         Decimal('-50.00'))


# ---------------------------------------------------------------------------
# Fund balances
# ---------------------------------------------------------------------------

class FundBalanceReportTests(LedgerFixture, TestCase):
    """ The balance page's year, laid out to hand over. See LedgerFixture. """

    def setUp(self):
        self.build_year()
        self.report = fund_balances(2026, TODAY)
        self.main = section(self.report, '226-AG: Event Production account')

    def test_each_fund_is_a_row(self):
        legacy = cells(self.main, 'Legacy', 'fund')
        self.assertEqual((legacy['opening'], legacy['received'], legacy['closing']),
                         (Decimal('10000.00'), Decimal('1000.00'), Decimal('11000.00')))
        self.assertEqual(legacy['kind'], 'Carries forward')
        budget = cells(self.main, 'SGA Budget', 'fund')
        self.assertEqual(budget['closing'], Decimal('-1000.00'))
        self.assertIn('Overspent', budget['status'])

    def test_what_is_unfiled_is_its_own_row_and_the_total_is_the_cash(self):
        self.assertEqual(cells(self.main, 'Not yet filed', 'fund')['closing'],
                         Decimal('-200.00'))
        total = self.main.total.cells
        self.assertEqual((total['opening'], total['closing']),
                         (Decimal('10000.00'), Decimal('9500.00')))

    def test_the_headlines(self):
        stats = {stat.label: stat.value for stat in self.report.stats}
        self.assertEqual(stats['226-AG cash'], Decimal('9500.00'))
        self.assertEqual(stats['Carries forward'], Decimal('11000.00'))
        self.assertEqual(stats['Awaiting SGA'], Decimal('300.00'))

    def test_a_workday_balance_that_agrees_is_noted(self):
        self.assertTrue(any('Workday said $9,500.00 on Jun 30, 2026, and the ledger agrees'
                            in note for note in self.report.notes))

    def test_one_that_does_not_is_a_warning(self):
        """ The earliest balance anchors the rest, so the June one now disagrees. """
        checkpoint('226-AG', datetime.date(2026, 3, 31), '1.00')
        report = fund_balances(2026, TODAY)
        self.assertTrue(any('Workday said $9,500.00 on Jun 30, 2026, but the ledger makes it'
                            in w for w in report.warnings))

    def test_unfiled_lines_are_a_warning(self):
        self.assertTrue(any("226-AG's lines (net) are still in the queue" in w
                            for w in self.report.warnings))

    def test_a_year_changed_since_it_was_closed_says_what_changed(self):
        year = balances.statement(2026, today=TODAY)
        FiscalYearClose.objects.create(fiscal_year=2026, snapshot=balances.snapshot(year))
        filed(self.unfiled, 'legacy', lnl_spend_category=category('consumables'))
        report = fund_balances(2026, TODAY)
        self.assertTrue(any(note.startswith('FY26 was closed') for note in report.notes))
        self.assertTrue(any('Changed since FY26 was closed' in w for w in report.warnings))

    def test_an_account_with_no_workday_balance_says_so(self):
        self.assertTrue(any('No Workday balance has been entered for 315-AG' in w
                            for w in self.report.warnings))


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class EventReportTests(TestCase):
    """ FY27's shows, by who they were for. """

    def setUp(self):
        line(datetime.date(2025, 7, 2), '-1.00', 'Opens the books')
        self.gala = show('Gala', when(2026, 9, 20), client('Admissions'))
        bill(self.gala, '1000.00', datetime.date(2026, 9, 22))
        income(self.gala, '1000.00', datetime.date(2026, 9, 28))
        cost('300.00', datetime.date(2026, 9, 21), linked_event=self.gala)
        self.fling = show('Fling', when(2026, 9, 12), client('SAB', student=True))
        cost('2000.00', datetime.date(2026, 9, 14), 'sga_fr', linked_event=self.fling,
             fr_line_target=request_line())
        self.report = event_report(Period.for_fiscal_year(2027, TODAY), today=TODAY)

    def test_events_are_grouped_by_who_they_were_for(self):
        self.assertEqual([item.title for item in self.report.sections],
                         ['Departments', 'Student organizations'])

    def test_a_billed_event(self):
        gala = cells(section(self.report, 'Departments'), 'Gala', 'event')
        self.assertEqual((gala['billed'], gala['received'], gala['costs'], gala['margin'],
                          gala['margin_percent']),
                         (Decimal('1000.00'), Decimal('1000.00'), Decimal('300.00'),
                          Decimal('700.00'), Decimal('70.0')))

    def test_a_show_sga_paid_for_is_not_a_loss(self):
        fling = cells(section(self.report, 'Student organizations'), 'Fling', 'event')
        self.assertEqual((fling['billed'], fling['sga'], fling['margin']),
                         (None, Decimal('2000.00'), Decimal('0.00')))
        self.assertEqual(fling['flags'], '')

    def test_each_group_has_a_total(self):
        total = section(self.report, 'Student organizations').total.cells
        self.assertEqual((total['event'], total['costs'], total['sga']),
                         ('Total, 1 event', Decimal('2000.00'), Decimal('2000.00')))

    def test_pricing_is_judged_on_billed_events_only(self):
        stats = {stat.label: stat.value for stat in self.report.stats}
        self.assertEqual(stats['Margin on billed events'], Decimal('70.0'))
        self.assertEqual(stats["LNL's costs"], Decimal('300.00'))

    def test_shows_before_the_books_start_are_left_out(self):
        old = show('Old Gala', when(2025, 3, 1), self.gala.billing_org)
        bill(old, '500.00', datetime.date(2025, 3, 2))
        report = event_report(Period(), today=TODAY)
        names = [row.cells['event'] for item in report.sections for row in item.rows]
        self.assertNotIn('Old Gala', names)
        self.assertIn('Gala', names)

    def test_any_dates(self):
        report = event_report(Period(datetime.date(2026, 9, 15), datetime.date(2026, 9, 30)),
                              today=TODAY)
        self.assertEqual([item.title for item in report.sections], ['Departments'])


# ---------------------------------------------------------------------------
# What LNL is owed
# ---------------------------------------------------------------------------

class AgeBandTests(TestCase):

    def test_bands(self):
        self.assertEqual([age_band(days) for days in (0, 30, 31, 60, 61, 90, 91, 400)],
                         ['0-30 days', '0-30 days', '31-60 days', '31-60 days', '61-90 days',
                          '61-90 days', 'Over 90 days', 'Over 90 days'])
        self.assertIsNone(age_band(None))


class OwedToLNLTests(CacheResetMixin, TestCase):
    """ SGA owes $600 on F.26.86, since June; Admissions owes $500 on a bill. """

    def setUp(self):
        super(OwedToLNLTests, self).setUp()
        self.request = make_request()
        spend(self.request, '1000.00', datetime.date(2026, 6, 1))
        reimburse(self.request, '400.00', datetime.date(2026, 7, 1))
        self.gala = show('Gala', when(2026, 9, 10), client('Admissions'))
        bill(self.gala, '500.00', datetime.date(2026, 9, 15))
        self.report = owed_to_lnl(today=TODAY)

    def test_sga_is_owed_per_request_aged_from_the_oldest_unpaid_spending(self):
        row = section(self.report, 'SGA: funding requests').rows[0].cells
        self.assertEqual((row['who'], row['what'], row['charged'], row['paid'], row['owed']),
                         ('SGA', 'F.26.86 Film Posters and Concessions', Decimal('1000.00'),
                          Decimal('400.00'), Decimal('600.00')))
        self.assertEqual((row['since'], row['days'], row['age']),
                         (datetime.date(2026, 6, 1), 122, 'Over 90 days'))

    def test_a_client_is_owed_per_bill_aged_from_the_bill(self):
        row = section(self.report, 'Clients: event bills').rows[0].cells
        self.assertEqual((row['who'], row['what'], row['owed'], row['days'], row['age']),
                         ('Admissions', 'Gala', Decimal('500.00'), 16, '0-30 days'))

    def test_the_headlines_add_up_by_age(self):
        stats = {stat.label: stat.value for stat in self.report.stats}
        self.assertEqual(stats['Owed to LNL'], Decimal('1100.00'))
        self.assertEqual(stats['0-30 days'], Decimal('500.00'))
        self.assertEqual(stats['Over 90 days'], Decimal('600.00'))
        self.assertEqual(len([s for s in self.report.stats
                              if s.label in dict((label, 1) for _, label in AGE_BANDS)]), 4)

    def test_an_overpaid_request_is_a_warning_not_a_debt(self):
        other = make_request('F.26.6', 'Film rights')
        reimburse(other, '50.00', datetime.date(2026, 7, 1))
        report = owed_to_lnl(today=TODAY)
        self.assertEqual(len(section(report, 'SGA: funding requests').rows), 1)
        self.assertTrue(any('SGA has paid $50.00 more than was spent on F.26.6' in w
                            for w in report.warnings))

    def test_one_side_of_the_partition(self):
        report = owed_to_lnl(is_projection=True, today=TODAY)
        self.assertEqual(section(report, 'SGA: funding requests').rows, [])

    def test_a_request_repaid_in_full_is_not_listed(self):
        reimburse(self.request, '600.00', datetime.date(2026, 8, 1))
        report = owed_to_lnl(today=TODAY)
        self.assertEqual(section(report, 'SGA: funding requests').rows, [])


# ---------------------------------------------------------------------------
# The CSV
# ---------------------------------------------------------------------------

class CSVTests(TestCase):

    def build(self, sections):
        columns = [Column('name', 'Name'), Column('when', 'When', Column.DATE),
                   Column('amount', 'Amount', Column.MONEY)]
        return Report('test', 'Test', 'FY27', '', 'fy27', columns, sections)

    def read(self, report):
        text = as_csv(report)
        self.assertTrue(text.startswith('﻿'), "Excel needs the byte-order mark")
        return list(csv.reader(io.StringIO(text[1:])))

    def test_figures_a_spreadsheet_can_sum(self):
        report = self.build([Section('Only', [
            Row({'name': 'Console', 'when': datetime.date(2026, 9, 1),
                 'amount': Decimal('-1234.5')}),
            Row({'name': 'Gap'}),
        ], Row({'name': 'Total', 'amount': Decimal('-1234.50')}))])
        self.assertEqual(self.read(report), [
            ['Name', 'When', 'Amount'],
            ['Console', '2026-09-01', '-1234.50'],
            ['Gap', '', ''],
            ['Total', '', '-1234.50'],
        ])

    def test_several_tables_say_which_each_line_is_from(self):
        report = self.build([Section('In', [Row({'name': 'A'})]),
                             Section('Out', [Row({'name': 'B'})])])
        rows = self.read(report)
        self.assertEqual(rows[0], ['Section', 'Name', 'When', 'Amount'])
        self.assertEqual([row[0] for row in rows[1:]], ['In', 'Out'])

    def test_the_file_is_named_for_the_report_and_the_period(self):
        self.assertEqual(self.build([]).filename, 'lnl-test-fy27.csv')


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class ReportPageTests(FinanceViewTestCase):

    def setUp(self):
        super(ReportPageTests, self).setUp()
        self.grant('view_subledger')

    def test_the_reports_tab_needs_the_view_permission(self):
        self.user.user_permissions.clear()
        self.client.force_login(type(self.user).objects.get(pk=self.user.pk))
        self.assertEqual(self.client.get(reverse('finance:reports')).status_code, 403)
        self.assertEqual(self.client.get(reverse('finance:report', args=['events'])).status_code,
                         403)

    def test_the_tab_lists_every_report_and_the_ledger(self):
        response = self.client.get(reverse('finance:reports'), {'fy': '2027'})
        self.assertOk(response)
        for title in ('Income and spending', 'Fund balances', 'Events', 'Owed to LNL',
                      'Ledger'):
            self.assertContains(response, title)
        self.assertContains(response, 'format=csv')

    def test_every_report_draws(self):
        for slug in ('income-and-spending', 'fund-balances', 'events', 'owed-to-lnl'):
            response = self.client.get(reverse('finance:report', args=[slug]),
                                       {'fy': '2027', 'partition': 'all'})
            self.assertOk(response)
            self.assertContains(response, 'Download CSV')
            self.assertContains(response, 'fin-print-header')

    def test_every_report_downloads(self):
        for slug in ('income-and-spending', 'fund-balances', 'events', 'owed-to-lnl'):
            response = self.client.get(reverse('finance:report', args=[slug]),
                                       {'fy': '2027', 'format': 'csv'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response['Content-Type'].startswith('text/csv'))
            self.assertIn('attachment; filename="lnl-%s-' % slug,
                          response['Content-Disposition'])

    def test_an_unknown_report_is_not_found(self):
        self.assertEqual(self.client.get(reverse('finance:report', args=['nope'])).status_code,
                         404)

    def test_dates_cover_any_range(self):
        response = self.client.get(reverse('finance:report', args=['income-and-spending']),
                                   {'fy': '2027', 'from': '2026-03-01', 'to': '2026-03-31'})
        self.assertContains(response, 'Mar 1, 2026 – Mar 31, 2026')

    def test_bad_dates_say_so(self):
        response = self.client.get(reverse('finance:report', args=['income-and-spending']),
                                   {'fy': '2027', 'from': 'soon', 'to': '2026-03-31'})
        self.assertContains(response, 'Showing the fiscal year instead')

    def test_one_fund(self):
        response = self.client.get(reverse('finance:report', args=['income-and-spending']),
                                   {'fy': '2027', 'fund': 'sga_fr'})
        self.assertContains(response, 'Only money filed to SGA Funding Request.')

    def test_the_tab_is_in_the_nav(self):
        response = self.client.get(reverse('finance:dashboard'))
        self.assertContains(response, reverse('finance:reports'))


class LedgerDownloadTests(FinanceViewTestCase):
    """ The ledger's CSV: every row the filters select, every column. """

    def setUp(self):
        super(LedgerDownloadTests, self).setUp()
        self.grant('view_subledger')

    def download(self, **params):
        params.setdefault('fy', '2027')
        params['format'] = 'csv'
        response = self.client.get(reverse('finance:ledger'), params)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        return response, list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))

    def test_every_row_not_only_the_first_page(self):
        for day in range(105):
            ParsedTransaction.objects.create(
                amount=Decimal('-1.00'), effective_date=datetime.date(2026, 8, 1) +
                datetime.timedelta(days=day % 28), fund_source=fund('legacy'),
                lnl_spend_category=category('consumables'), description='Tape %s' % day)
        response, rows = self.download()
        self.assertEqual(len(rows), 106)
        self.assertIn('filename="lnl-ledger-fy27.csv"', response['Content-Disposition'])

    def test_the_columns(self):
        txn = line(datetime.date(2026, 8, 3), '-42.50', 'Gaff tape', ledger_account='71100:Supplies')
        filed(txn, 'legacy', lnl_spend_category=category('consumables'), description='Gaff tape',
              audit_explanation='For the fall show')
        _, rows = self.download()
        header, row = rows[0], dict(zip(rows[0], rows[1]))
        self.assertEqual(header[:4], ['Date', 'Description', 'Payee', 'Amount'])
        self.assertEqual((row['Date'], row['Amount'], row['Type'], row['Fund'],
                          row['Spend category'], row['Ledger account'], row['Memo'],
                          row['Note']),
                         ('2026-08-03', '-42.50', 'Expense', 'Legacy', 'Consumables',
                          '71100:Supplies', 'Gaff tape', 'For the fall show'))

    def test_the_filters_apply(self):
        filed(line(datetime.date(2026, 8, 3), '-10.00'), 'legacy',
              lnl_spend_category=category('consumables'))
        filed(line(datetime.date(2026, 8, 4), '-20.00'), 'legacy',
              lnl_spend_category=category('food'))
        _, rows = self.download(category='food')
        self.assertEqual([row[3] for row in rows[1:]], ['-20.00'])

    def test_a_request_is_named_whichever_way_the_entry_names_it(self):
        request = make_request(reference='F.27.9', name='Film rights', fiscal_year=2027)
        spend(request, '30.00', datetime.date(2026, 8, 5))
        _, rows = self.download()
        row = dict(zip(rows[0], rows[1]))
        self.assertEqual((row['Funding request'], row['FR line']),
                         ('F.27.9 Film rights', 'Posters'))

    def test_the_ledger_offers_it(self):
        response = self.client.get(reverse('finance:ledger'), {'fy': '2027'})
        self.assertContains(response, 'format=csv')

    def test_it_needs_the_view_permission(self):
        self.user.user_permissions.clear()
        self.client.force_login(type(self.user).objects.get(pk=self.user.pk))
        response = self.client.get(reverse('finance:ledger'), {'format': 'csv'})
        self.assertEqual(response.status_code, 403)

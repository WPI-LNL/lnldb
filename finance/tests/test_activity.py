"""
What LNL's work was worth and who it was for, read from the events app.

Four layers, tested from the bottom up:

* **Terms.** WPI's A-E terms, each starting on a fixed day in the break
  before it.
* **Pricing.** A show's service value, worked out in bulk, has to equal what
  the events app says, ``lnl_services_subtotal``, for every pricing path -- price
  lists, the original discount, the newer discounts and fees, and 2012 events.
  Shared out across the services, it has to add back up to the cent.
* **The reports.** Student organizations against departments with the
  external wear percentage, and activity term over term and year over year.
* **The pages.**
"""
import csv
import datetime
import io
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from events.models import (Billing, Discount, DiscountPrice, Event, EventArbitrary, Extra,
                           ExtraInstance, ExtraPrice, Fee, FeePrice, Lighting, Pricelist, Rental,
                           Service, ServiceInstance, ServicePrice, Sound)
from events.tests.generators import CategoryFactory, Event2019Factory, EventFactory, OrgFactory
from finance import activity, reports
from finance.activity import _allocate, load_work, term_for, terms_between
from finance.reports import Period, activity_trends, as_csv, work_split
from finance.tests.test_views import FinanceViewTestCase

TODAY = datetime.date(2026, 10, 2)


def when(year, month, day):
    return datetime.datetime(year, month, day, 19, 0, tzinfo=datetime.timezone.utc)


def show(name, start, client=None, model=Event2019Factory, **fields):
    """ An approved event that ran on ``start``. """
    fields.setdefault('approved', True)
    event = model.create(event_name=name, billing_org=client, **fields)
    event.datetime_start = start
    event.datetime_end = start + datetime.timedelta(hours=3)
    event.save()
    return event


class Catalogue(object):
    """ The events app's categories and a few services, priced in round numbers. """

    def build_catalogue(self):
        self.lighting = CategoryFactory.create(name='Lighting')
        self.sound = CategoryFactory.create(name='Sound')
        self.projection = CategoryFactory.create(name='Projection')
        self.power = CategoryFactory.create(name='Power')
        self.l2 = Service.objects.create(shortname='L2', longname='L2: Basic Dynamic Lighting',
                                         base_cost=Decimal('400.00'), addtl_cost=0,
                                         category=self.lighting)
        self.s2 = Service.objects.create(shortname='S2', longname='S2: Basic Sound Event',
                                         base_cost=Decimal('300.00'), addtl_cost=0,
                                         category=self.sound)
        self.dp = Service.objects.create(shortname='DP', longname='Digital Projection',
                                         base_cost=Decimal('100.00'), addtl_cost=0,
                                         category=self.projection)
        self.pd = Service.objects.create(shortname='PD', longname='Power Distribution',
                                         base_cost=Decimal('50.00'), addtl_cost=0,
                                         category=self.power)
        self.haze = Extra.objects.create(name='Hazer', cost=Decimal('25.00'), desc='Haze',
                                         category=self.lighting)
        self.student = OrgFactory.create(name='Masque', workday_fund=810)
        self.department = OrgFactory.create(name='Music Department', workday_fund=110)

    def book(self, event, *services, **extras):
        for service in services:
            ServiceInstance.objects.create(event=event, service=service)
        for extra, quantity in extras.items():
            ExtraInstance.objects.create(event=event, extra=getattr(self, extra), quant=quantity)
        return event


def priced(event):
    """ The one show, as load_work prices it. """
    return [work for work in load_work(today=TODAY) if work.event.pk == event.pk][0]


# ---------------------------------------------------------------------------
# Terms
# ---------------------------------------------------------------------------

class TermTests(TestCase):

    def test_each_term_starts_on_its_day(self):
        cases = [((2026, 1, 1), 'C26'), ((2026, 3, 9), 'C26'), ((2026, 3, 10), 'D26'),
                 ((2026, 5, 19), 'D26'), ((2026, 5, 20), 'E26'), ((2026, 8, 14), 'E26'),
                 ((2026, 8, 15), 'A26'), ((2026, 10, 14), 'A26'), ((2026, 10, 15), 'B26'),
                 ((2026, 12, 31), 'B26')]
        for day, code in cases:
            self.assertEqual(term_for(datetime.date(*day)).code, code, day)

    def test_a_term_knows_its_dates(self):
        term = term_for(datetime.date(2025, 9, 3))
        self.assertEqual((term.code, term.first, term.last),
                         ('A25', datetime.date(2025, 8, 15), datetime.date(2025, 10, 14)))
        self.assertEqual(term_for(datetime.date(2025, 11, 1)).last, datetime.date(2025, 12, 31))

    def test_the_terms_over_a_stretch(self):
        codes = [t.code for t in terms_between(datetime.date(2025, 7, 1),
                                               datetime.date(2026, 1, 5))]
        self.assertEqual(codes, ['E25', 'A25', 'B25', 'C26'])


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------

class AllocateTests(TestCase):

    def test_parts_add_up_to_the_cent(self):
        parts = _allocate(Decimal('10.00'), [Decimal('1'), Decimal('1'), Decimal('1')])
        self.assertEqual(sum(parts), Decimal('10.00'))
        self.assertEqual(sorted(parts), [Decimal('3.33'), Decimal('3.33'), Decimal('3.34')])

    def test_in_proportion(self):
        self.assertEqual(_allocate(Decimal('60.00'), [Decimal('400'), Decimal('200')]),
                         [Decimal('40.00'), Decimal('20.00')])

    def test_nothing_to_share_by(self):
        self.assertEqual(_allocate(Decimal('5.00'), [Decimal('0')]), [Decimal('0')])


class PricingTests(Catalogue, TestCase):
    """ Every pricing path agrees with the events app's own arithmetic. """

    def setUp(self):
        self.build_catalogue()

    def assertAgrees(self, event):
        """ The bulk figure is the model's, and its lines add up to it exactly. """
        work = priced(event)
        model = type(event).objects.get(pk=event.pk)
        self.assertEqual(work.value, model.lnl_services_subtotal)
        self.assertEqual(sum(line.net for line in work.lines), work.value)
        return work

    def test_list_prices_and_the_original_discount(self):
        """ Lighting and sound together: 15% off them, power and every extra; not projection. """
        event = self.book(show('Gala', when(2026, 3, 1)), self.l2, self.s2, self.dp, self.pd,
                          haze=2)
        work = self.assertAgrees(event)
        # 900 in all; (400 + 300 + 50 + 2 x 25) x 15% = 120 off, projection's 100 untouched.
        self.assertEqual(work.value, Decimal('780.00'))
        self.assertEqual(work.value_in('Projection'), Decimal('100.00'))
        self.assertEqual(work.value_in('Lighting'), Decimal('382.50'))

    def test_no_discount_without_both_lighting_and_sound(self):
        work = self.assertAgrees(self.book(show('Talk', when(2026, 3, 1)), self.s2, haze=1))
        self.assertEqual(work.value, Decimal('325.00'))

    def test_a_price_list_overrides_the_list_price(self):
        pricelist = Pricelist.objects.create(name='2026')
        ServicePrice.objects.create(service=self.l2, pricelist=pricelist, cost=Decimal('333.33'))
        ExtraPrice.objects.create(extra=self.haze, pricelist=pricelist, cost=Decimal('19.99'))
        event = show('Recital', when(2026, 3, 1), pricelist=pricelist)
        work = self.assertAgrees(self.book(event, self.l2, self.s2, haze=3))
        self.assertEqual(sum(line.amount for line in work.lines),
                         Decimal('333.33') + Decimal('300.00') + 3 * Decimal('19.99'))

    def test_the_newer_discounts_and_fees(self):
        pricelist = Pricelist.objects.create(name='2027')
        package = Discount.objects.create(name='Package')
        package.categories.set([self.lighting, self.sound])
        DiscountPrice.objects.create(discount=package, pricelist=pricelist, percent=Decimal('10'))
        late = Fee.objects.create(name='Late booking')
        late.categories.set([self.sound, self.power])
        FeePrice.objects.create(fee=late, pricelist=pricelist, percent=Decimal('7.5'))
        unpriced = Discount.objects.create(name='Not on this price list')
        unpriced.categories.set([self.projection])
        event = show('Formal', when(2026, 3, 1), pricelist=pricelist, uses_new_discounts=True)
        event.applied_discounts.set([package, unpriced])
        event.applied_fees.set([late])
        work = self.assertAgrees(self.book(event, self.l2, self.s2, self.dp, self.pd, haze=1))
        # Discount: 10% of 400 + 300 + 25 = 72.50. Fee: 7.5% of 300 + 50 = 26.25.
        self.assertEqual(work.value, Decimal('875.00') - Decimal('72.50') + Decimal('26.25'))

    def test_a_category_split_that_needs_rounding_still_adds_up(self):
        pricelist = Pricelist.objects.create(name='Odd')
        ServicePrice.objects.create(service=self.l2, pricelist=pricelist, cost=Decimal('333.33'))
        ServicePrice.objects.create(service=self.s2, pricelist=pricelist, cost=Decimal('333.33'))
        ServicePrice.objects.create(service=self.pd, pricelist=pricelist, cost=Decimal('333.34'))
        event = show('Odd', when(2026, 3, 1), pricelist=pricelist)
        work = self.assertAgrees(self.book(event, self.l2, self.s2, self.pd))
        self.assertEqual(sum(work.value_in(name) for name in ('Lighting', 'Sound', 'Power')),
                         work.value)

    def test_a_2012_event(self):
        legacy_l = Lighting.objects.create(shortname='L2', longname='L2', base_cost=Decimal('200'),
                                           addtl_cost=0, category=self.lighting)
        legacy_s = Sound.objects.create(shortname='S2', longname='S2', base_cost=Decimal('100'),
                                        addtl_cost=0, category=self.sound)
        event = show('Old Gala', when(2026, 3, 1), model=EventFactory, lighting=legacy_l,
                     sound=legacy_s)
        event.otherservices.set([self.dp])
        ExtraInstance.objects.create(event=event, extra=self.haze, quant=2)
        work = priced(event)
        model = Event.objects.get(pk=event.pk)
        self.assertEqual(work.value, model.cost_total - model.oneoff_total)
        self.assertEqual(work.value, Decimal('200') + 100 + 100 + 50 - 45)

    def test_hired_in_gear_and_one_off_charges_are_not_service_value(self):
        event = self.book(show('Concert', when(2026, 3, 1)), self.s2)
        Rental.objects.create(event=event, name='Line array', cost=Decimal('2000.00'), quantity=2)
        EventArbitrary.objects.create(event=event, key_name='Damage', key_value=Decimal('80.00'),
                                      key_quantity=1)
        work = priced(event)
        self.assertEqual(work.value, Decimal('300.00'))
        self.assertEqual((work.rental_items, work.rental_cost), (2, Decimal('4000.00')))


class LoadWorkTests(Catalogue, TestCase):
    """ Which shows count. """

    def setUp(self):
        self.build_catalogue()
        self.ran = show('Ran', when(2026, 3, 1), self.student)

    def names(self, **kwargs):
        return [work.event.event_name for work in load_work(today=TODAY, **kwargs)]

    def test_only_approved_shows_that_ran(self):
        show('Cancelled', when(2026, 3, 2), cancelled=True)
        show('Test', when(2026, 3, 3), test_event=True)
        show('Not approved', when(2026, 3, 4), approved=False)
        show('Still to come', when(2026, 11, 1))
        self.assertEqual(self.names(), ['Ran'])

    def test_between_dates(self):
        show('Earlier', when(2025, 9, 1))
        self.assertEqual(self.names(first=datetime.date(2026, 1, 1)), ['Ran'])
        self.assertEqual(self.names(last=datetime.date(2025, 12, 31)), ['Earlier'])

    def test_who_it_was_for_and_what_was_billed(self):
        Billing.objects.create(event=self.ran, date_billed=datetime.date(2026, 3, 5),
                               amount=Decimal('450.00'))
        work = load_work(today=TODAY)[0]
        self.assertEqual((work.client, work.client_type, work.billed),
                         (self.student, 'student_org', Decimal('450.00')))


# ---------------------------------------------------------------------------
# Student organizations and departments
# ---------------------------------------------------------------------------

class WorkSplitTests(Catalogue, TestCase):
    """
    FY26: Masque's show with lighting and sound ($595 after the 15% discount),
    the Music Department's sound-only show ($300, billed $300), and a show with
    no client and a projector ($100).
    """

    def setUp(self):
        self.build_catalogue()
        self.book(show('Masque Show', when(2026, 2, 1), self.student), self.l2, self.s2)
        concert = self.book(show('Concert', when(2026, 3, 1), self.department), self.s2)
        Billing.objects.create(event=concert, date_billed=datetime.date(2026, 3, 3),
                               amount=Decimal('300.00'))
        self.book(show('Movie', when(2026, 4, 1)), self.dp)
        self.report = work_split(Period.for_fiscal_year(2026, TODAY), TODAY)

    def stats(self):
        return {stat.label: stat.value for stat in self.report.stats}

    def table(self, title):
        return [s for s in self.report.sections if s.title == title][0]

    def test_the_value_of_each_side(self):
        stats = self.stats()
        self.assertEqual(stats['Student organizations'], Decimal('595.00'))
        self.assertEqual(stats['Departments and external'], Decimal('300.00'))
        self.assertEqual(stats['Service value'], Decimal('995.00'))

    def test_the_external_wear_percentage(self):
        """ 300 / (595 + 300), over the work that can be placed. """
        self.assertEqual(self.stats()['External wear percentage'], Decimal('33.5'))

    def test_who_the_work_was_for(self):
        rows = {row.cells['group']: row.cells for row in self.table('Who the work was for').rows}
        self.assertEqual((rows['Student organizations']['events'],
                          rows['Student organizations']['billed']), (1, Decimal('0.00')))
        self.assertEqual(rows['Departments and external']['billed'], Decimal('300.00'))
        self.assertEqual(rows['Not classified']['value'], Decimal('100.00'))

    def test_service_by_service(self):
        rows = {row.cells['category']: row.cells for row in self.table('By service').rows}
        # Masque's lighting: 400 less 15% = 340; sound 300 less 15% = 255.
        self.assertEqual((rows['Lighting']['student'], rows['Lighting']['wear']),
                         (Decimal('340.00'), Decimal('0.0')))
        self.assertEqual((rows['Sound']['student'], rows['Sound']['external'],
                          rows['Sound']['wear']),
                         (Decimal('255.00'), Decimal('300.00'), Decimal('54.1')))
        self.assertEqual(rows['Projection']['unplaced'], Decimal('100.00'))
        self.assertEqual(self.table('By service').total.cells['total'], Decimal('995.00'))

    def test_clients_by_value(self):
        clients = [row.cells['client'] for row in self.table('Clients').rows]
        self.assertEqual(clients, ['Masque', 'Music Department', 'No client on file'])

    def test_unplaced_work_is_a_warning_with_the_range_it_could_make(self):
        warning = self.report.warnings[0]
        self.assertIn('1 event worth $100.00 cannot be placed', warning)
        # (300 + 100) / 995 and 300 / 995.
        self.assertIn('make it 40.2%', warning)
        self.assertIn('student organizations, 30.2%', warning)

    def test_the_csv_writes_each_table_as_a_block(self):
        rows = list(csv.reader(io.StringIO(as_csv(self.report)[1:])))
        self.assertEqual(rows[0], ['Who the work was for'])
        self.assertEqual(rows[1][:3], ['Client type', 'Events', 'Share of events'])
        self.assertIn(['By service'], rows)


# ---------------------------------------------------------------------------
# Activity, term over term and year over year
# ---------------------------------------------------------------------------

class ActivityTrendTests(Catalogue, TestCase):
    """
    A25 (Sep 2025): Masque with L2 and S2, and two hazers.
    C26 (Feb 2026): the Music Department with S2, and a hired line array.
    A26 (Sep 2026): Masque with L2.
    """

    def setUp(self):
        self.build_catalogue()
        self.book(show('Fall Show', when(2025, 9, 10), self.student), self.l2, self.s2, haze=2)
        concert = self.book(show('Concert', when(2026, 2, 10), self.department), self.s2)
        Rental.objects.create(event=concert, name='Line array', cost=Decimal('500.00'),
                              quantity=3)
        self.book(show('Fall Show 2', when(2026, 9, 10), self.student), self.l2)

    def section(self, report, title):
        return [s for s in report.sections if s.title == title][0]

    def cells(self, report, title, line):
        for row in self.section(report, title).rows:
            if row.cells['line'] == line:
                return [row.cells[c.key] for c in report.columns[1:]]
        raise AssertionError('No %r under %s' % (line, title))

    def test_the_columns_are_the_terms_since_the_first_show(self):
        report = activity_trends(2027, 'term', 'events', TODAY)
        self.assertEqual([c.label for c in report.columns],
                         ['Line', 'A25', 'B25', 'C26', 'D26', 'E26', 'A26 to date',
                          'Change from A25, same dates'])

    def test_who_it_was_for_by_term(self):
        report = activity_trends(2027, 'term', 'events', TODAY)
        self.assertEqual(self.cells(report, 'Who it was for', 'Student organizations'),
                         [1, 0, 0, 0, 0, 1, 0])
        self.assertEqual(self.cells(report, 'Who it was for', 'Departments and external'),
                         [0, 0, 1, 0, 0, 0, 0])

    def test_services_count_the_events_that_used_them(self):
        report = activity_trends(2027, 'term', 'events', TODAY)
        self.assertEqual(self.cells(report, 'Services', 'Sound'), [1, 0, 1, 0, 0, 0, -1])

    def test_tiers_and_add_ons_count_what_was_booked(self):
        report = activity_trends(2027, 'term', 'events', TODAY)
        self.assertEqual(self.cells(report, 'Service tiers and add-ons', 'Hazer (add-on)'),
                         [2, 0, 0, 0, 0, 0, -2])
        self.assertEqual(self.cells(report, 'Service tiers and add-ons', 'Hired-in gear (items)'),
                         [0, 0, 3, 0, 0, 0, 0])

    def test_service_value_year_over_year(self):
        report = activity_trends(2027, 'year', 'value', TODAY)
        self.assertEqual([c.label for c in report.columns],
                         ['Line', 'FY26', 'FY27 to date', 'Change from FY26, same dates'])
        # FY26: (400 + 300 + 50) less 15% = 637.50, and 300. FY27: 400.
        self.assertEqual(self.cells(report, 'Who it was for', 'Student organizations'),
                         [Decimal('637.50'), Decimal('400.00'), Decimal('-237.50')])
        self.assertEqual(self.cells(report, 'Services', 'Lighting'),
                         [Decimal('382.50'), Decimal('400.00'), Decimal('17.50')])

    def test_clients_beyond_the_top_are_rolled_up(self):
        original = reports.TREND_CLIENTS
        reports.TREND_CLIENTS = 1
        self.addCleanup(setattr, reports, 'TREND_CLIENTS', original)
        report = activity_trends(2027, 'term', 'events', TODAY)
        lines = [row.cells['line'] for row in self.section(report, 'Clients').rows]
        self.assertEqual(lines, ['Masque', '1 other clients'])

    def test_the_headlines_are_the_latest_column(self):
        report = activity_trends(2027, 'term', 'events', TODAY)
        stats = {stat.label: (stat.value, stat.sub) for stat in report.stats}
        self.assertEqual(stats['Events, A26 to date'], (1, '1 in A25, same dates'))
        self.assertEqual(stats['External wear percentage, A26 to date'][0], Decimal('0.0'))


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class ActivityPageTests(Catalogue, FinanceViewTestCase):

    def setUp(self):
        super(ActivityPageTests, self).setUp()
        self.build_catalogue()
        self.grant('view_subledger')
        self.book(show('Fall Show', when(2025, 9, 10), self.student), self.l2)

    def test_both_reports_draw_and_download(self):
        for slug, params in (('work-split', {'fy': '2026'}),
                             ('activity', {'fy': '2026', 'by': 'year', 'measure': 'value'}),
                             ('activity', {'fy': '2026'})):
            url = reverse('finance:report', args=[slug])
            self.assertOk(self.client.get(url, params))
            response = self.client.get(url, dict(params, format='csv'))
            self.assertIn('attachment; filename="lnl-%s-' % slug,
                          response['Content-Disposition'])

    def test_the_external_wear_percentage_is_on_the_page(self):
        response = self.client.get(reverse('finance:report', args=['work-split']), {'fy': '2026'})
        self.assertContains(response, 'External wear percentage')

    def test_an_unknown_grouping_falls_back_to_terms(self):
        response = self.client.get(reverse('finance:report', args=['activity']),
                                   {'fy': '2026', 'by': 'decade', 'measure': 'vibes'})
        self.assertContains(response, 'Term over term')

    def test_they_are_on_the_reports_tab(self):
        response = self.client.get(reverse('finance:reports'))
        self.assertContains(response, 'Student organizations and departments')
        self.assertContains(response, 'Event activity')

    def test_the_grouping_names_the_file(self):
        response = self.client.get(reverse('finance:report', args=['activity']),
                                   {'fy': '2026', 'by': 'year', 'measure': 'value',
                                    'format': 'csv'})
        self.assertIn('lnl-activity-year-value-fy26.csv', response['Content-Disposition'])
        self.assertTrue(activity.CLIENT_GROUPS)

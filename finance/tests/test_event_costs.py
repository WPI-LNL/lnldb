"""
Costs that belong to one event, and what each event made or lost.

Three layers, tested from the bottom up:

* **Suggesting the event on an expense.** A rental memo that names its show
  exactly fills the box in, the way an ISD memo does for revenue. One that only
  resembles a show offers a single chip -- and only when one event leads
  outright, because several guesses under a box is a puzzle, not a shortcut.
* **The figures.** Billed, received, direct costs, reserved and margin, with
  the three decisions inside them: the year is the year the event ran, billed
  is the latest bill (a multi-bill split by price), and an encumbrance is
  reserved rather than spent.
* **The pages** that show them: the event P&L, the ledger's event filter, the
  dashboard panel, the event's own Billing tab, and the queue row that asks
  for the event.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from events.models import Billing, EventArbitrary, MultiBilling, Rental
from events.tests.generators import Event2019Factory, OrgFactory
from finance.calculators import (event_billed, event_financials, event_pnl_rows,
                                 event_pnl_totals)
from finance.models import ParsedTransaction, TransactionStatus, WorkdayTransaction
from finance.suggestions import (EXPORT, GUESS, HIGH, MEMO, Suggestion, lookups_for_form,
                                 suggest_all, suggest_expense_event)
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund

FY26 = 2026


def when(year, month, day):
    return datetime.datetime(year, month, day, 19, 0, tzinfo=datetime.timezone.utc)


def make_event(name, start, **kwargs):
    """ An Event2019 that ran on ``start``. The factory's own date is import time. """
    event = Event2019Factory(event_name=name, **kwargs)
    event.datetime_start = start
    event.datetime_end = start + datetime.timedelta(hours=3)
    event.save()
    return event


def expense_line(memo, amount='-100.00', date=datetime.date(2025, 10, 10), **worktags):
    """ An unsaved bank line, which is all the suggesters read. """
    return WorkdayTransaction(
        operational_transaction='Supplier Invoice: 25100001-SIN', accounting_date=date,
        net_amount=Decimal(amount), supplier='Gateway Productions', memo=memo,
        worktags_json=dict(worktags))


def passthrough_suggestion():
    """ What suggest_spend_category says for a line on Rent - Equipment. """
    return Suggestion(category('event_subrental').pk, HIGH, 'Ledger account 71500', source=EXPORT)


# ---------------------------------------------------------------------------
# Suggesting the event on an expense
# ---------------------------------------------------------------------------

class ExactExpenseEventTests(TestCase):
    """ A memo that names the show outright is somebody's answer, read back. """

    def setUp(self):
        self.drag = make_event('Drag Show', when(2025, 10, 4))

    def test_a_bracketed_name_fills_the_box_in(self):
        suggestion = suggest_expense_event(expense_line('DT projector rental (Drag Show A25)'))
        self.assertEqual(suggestion.value, self.drag.pk)
        self.assertEqual(suggestion.source, MEMO)
        self.assertTrue(suggestion.is_lookup)

    def test_the_term_code_is_not_part_of_the_name(self):
        """ lnldb names the show; the memo names the show and the term. """
        self.assertIsNotNone(suggest_expense_event(expense_line('(Drag Show A25)')))

    def test_a_memo_that_is_the_name_matches(self):
        suggestion = suggest_expense_event(expense_line('drag show'))
        self.assertEqual(suggestion.value, self.drag.pk)

    def test_the_house_format_description_matches(self):
        """ ``{description}, {FR line}, {FR code}`` -- the description is the name. """
        suggestion = suggest_expense_event(
            expense_line('Drag Show, Event - Sub-Rental, (A.26.16)'))
        self.assertEqual(suggestion.value, self.drag.pk)

    def test_the_reason_names_the_date(self):
        """ A filled box is the one nobody re-reads, so it says which year. """
        suggestion = suggest_expense_event(expense_line('(Drag Show)'))
        self.assertIn('2025', suggestion.reason)
        self.assertIn('Drag Show', suggestion.label)

    def test_the_nearest_years_show_wins(self):
        last_year = make_event('Drag Show', when(2024, 10, 5))
        suggestion = suggest_expense_event(
            expense_line('(Drag Show)', date=datetime.date(2024, 10, 20)))
        self.assertEqual(suggestion.value, last_year.pk)

    def test_a_show_far_from_the_charge_is_not_offered(self):
        """ Two years apart, an exact name is a coincidence, not an answer. """
        suggestion = suggest_expense_event(
            expense_line('(Drag Show)', date=datetime.date(2027, 10, 10)))
        self.assertIsNone(suggestion)

    def test_a_cancelled_show_is_not_offered(self):
        self.drag.cancelled = True
        self.drag.save()
        self.assertIsNone(suggest_expense_event(expense_line('(Drag Show)')))

    def test_money_coming_in_is_left_to_the_revenue_matcher(self):
        self.assertIsNone(suggest_expense_event(expense_line('(Drag Show)', amount='100.00')))

    def test_a_partial_name_is_not_an_exact_match(self):
        """ "Drag" is not "Drag Show"; without "rental" there is no guess either. """
        self.assertIsNone(suggest_expense_event(expense_line('Drag queen makeup')))

    def test_an_event_named_with_its_term_matches_too(self):
        """ lnldb names some shows "Goat Talent C26" and some "Pan Asian Festival". """
        goat = make_event('Goat Talent C26', when(2026, 1, 31))
        suggestion = suggest_expense_event(
            expense_line('DT projector rental (Goat Talent C26)', date=datetime.date(2026, 2, 10)))
        self.assertEqual(suggestion.value, goat.pk)


class TermCodeYearTests(TestCase):
    """
    A term code in the memo says which year's show it was.

    The Theatre department bills projector hire in batches, so a spring show's
    charge can arrive the following autumn -- nearer to *next* spring's show of
    the same name than to the one it paid for.
    """

    def setUp(self):
        self.this_spring = make_event('Drag Show', when(2025, 4, 10))
        self.next_spring = make_event('Drag Show', when(2026, 4, 10))
        self.october = datetime.date(2025, 10, 10)

    def test_the_term_decides_the_year(self):
        suggestion = suggest_expense_event(
            expense_line('DT projector rental (Drag Show D25)', date=self.october))
        self.assertEqual(suggestion.value, self.this_spring.pk)

    def test_a_show_from_another_term_is_not_filled_in(self):
        """ Better an empty box than next year's show in a box nobody re-reads. """
        self.this_spring.delete()
        self.assertIsNone(suggest_expense_event(
            expense_line('DT projector rental (Drag Show D25)', date=self.october)))

    def test_the_term_also_bounds_a_guess(self):
        self.this_spring.delete()
        self.assertIsNone(suggest_expense_event(
            expense_line('Drag Show D25 lighting rental', date=self.october)))


class GuessedExpenseEventTests(TestCase):
    """ A rental memo written as prose can only be guessed against an event. """

    def setUp(self):
        self.festival = make_event('Pan Asian Festival', when(2026, 4, 25))
        self.memo = 'WPI Pan Asian Festival lighting and sound rental'
        self.date = datetime.date(2026, 5, 1)

    def _suggest(self, memo=None, amount='-26242.55', spend_category=None):
        return suggest_expense_event(
            expense_line(memo or self.memo, amount=amount, date=self.date),
            spend_category=spend_category)

    def test_one_leading_event_is_offered_as_a_chip(self):
        suggestion = self._suggest()
        self.assertEqual(suggestion.value, self.festival.pk)
        self.assertEqual(suggestion.source, GUESS)
        self.assertFalse(suggestion.is_lookup)

    def test_a_guess_never_reaches_the_form(self):
        """ lookups_for_form() is everything the form may pre-select. """
        txn = expense_line(self.memo, amount='-26242.55', date=self.date,
                           spend_category='Rent - Equipment')
        self.assertNotIn('linked_event', lookups_for_form(suggest_all(txn)))

    def test_the_reason_says_what_matched_and_to_check_it(self):
        suggestion = self._suggest()
        self.assertIn('festival', suggestion.reason)
        self.assertIn('check', suggestion.reason)

    def test_a_tie_is_a_question_and_offers_nothing(self):
        """ Two festivals that weekend: nearer in date is not evidence of which. """
        make_event('Spring Festival', when(2026, 4, 26))
        self.assertIsNone(self._suggest('Festival rental'))

    def test_a_rental_billed_at_this_price_breaks_the_tie(self):
        """ A pass-through is exactly a hire the client was billed for at cost. """
        make_event('Spring Festival', when(2026, 4, 26))
        Rental.objects.create(event=self.festival, name='Lighting rig',
                              cost=Decimal('26000.00'), quantity=1)
        suggestion = self._suggest('Festival rental')
        self.assertEqual(suggestion.value, self.festival.pk)

    def test_an_ordinary_purchase_is_not_guessed_at(self):
        """ No "rental" and no pass-through category: nothing says it was one show's. """
        self.assertIsNone(self._suggest('Gaff tape for Pan Asian Festival'))

    def test_the_pass_through_category_is_enough_to_guess(self):
        suggestion = self._suggest('Gateway Productions Pan Asian Festival',
                                   spend_category=passthrough_suggestion())
        self.assertEqual(suggestion.value, self.festival.pk)

    def test_generic_words_alone_match_nothing(self):
        """ "Lighting and sound rental" describes half the events in lnldb. """
        make_event('Lighting Showcase', when(2026, 4, 28))
        self.assertIsNone(self._suggest('Lighting and sound equipment rental'))

    def test_events_outside_the_window_are_not_guessed(self):
        self.festival.datetime_start = when(2025, 10, 1)
        self.festival.save()
        self.assertIsNone(self._suggest())


class SuggestAllExpenseEventTests(TestCase):
    """ How the event suggestion sits alongside the rest of an expense row. """

    def setUp(self):
        self.drag = make_event('Drag Show', when(2025, 10, 4))

    def test_an_exact_name_is_handed_to_the_form(self):
        txn = expense_line('DT projector rental (Drag Show A25)',
                           spend_category='Rent - Equipment')
        suggestions = suggest_all(txn)
        self.assertEqual(lookups_for_form(suggestions)['linked_event'].value, self.drag.pk)
        self.assertFalse(suggestions['needs_event'])

    def test_a_pass_through_cost_with_no_event_says_so(self):
        txn = expense_line('Truck rental', spend_category='Rent - Equipment')
        self.assertTrue(suggest_all(txn)['needs_event'])

    def test_an_ordinary_category_does_not_ask_for_an_event(self):
        txn = expense_line('Gaff tape', spend_category='Supplies')
        self.assertFalse(suggest_all(txn)['needs_event'])


# ---------------------------------------------------------------------------
# The figures
# ---------------------------------------------------------------------------

def bank(op, amount, date=datetime.date(2025, 10, 10), org=None):
    worktags = {'ledger_account': '71500:Rent - Equipment'}
    if org:
        worktags['student_organization'] = org
    return WorkdayTransaction.objects.create(
        operational_transaction=op, accounting_date=date, net_amount=Decimal(amount),
        supplier='Gateway Productions', worktags_json=worktags)


def revenue(event, amount, op, date=datetime.date(2025, 10, 20), **kwargs):
    line = bank(op, amount, date)
    return ParsedTransaction.objects.create(
        parent_transaction=line, amount=Decimal(amount), effective_date=date,
        linked_event=event, **kwargs)


def cost(event, amount, op, date=datetime.date(2025, 10, 10), org=None, **kwargs):
    line = bank(op, amount, date, org=org)
    kwargs.setdefault('lnl_spend_category', category('event_subrental'))
    return ParsedTransaction.objects.create(
        parent_transaction=line, amount=Decimal(amount), effective_date=date,
        fund_source=fund('legacy'), linked_event=event, **kwargs)


class EventFinancialsTests(TestCase):
    """ One show's figures, and the decisions inside them. """

    def setUp(self):
        self.event = make_event('Pan Asian Festival', when(2025, 10, 4))

    def test_received_costs_and_margin(self):
        revenue(self.event, '5000.00', 'R1')
        cost(self.event, '-3000.00', 'C1')
        figures = event_financials(self.event)
        self.assertEqual(figures['received'], Decimal('5000.00'))
        self.assertEqual(figures['costs'], Decimal('3000.00'))
        self.assertEqual(figures['margin'], Decimal('2000.00'))
        self.assertEqual(figures['margin_percent'], Decimal('40.0'))
        self.assertEqual(figures['entries'], 2)

    def test_a_refund_reduces_the_cost(self):
        """ Refunds inherit the event from the purchase they reverse. """
        purchase = cost(self.event, '-3000.00', 'C1')
        line = bank('C1R', '500.00')
        ParsedTransaction.objects.create(
            parent_transaction=line, amount=Decimal('500.00'), refund_of=purchase,
            effective_date=line.accounting_date, fund_source=fund('legacy'),
            lnl_spend_category=category('event_subrental'), linked_event=self.event)
        self.assertEqual(event_financials(self.event)['costs'], Decimal('2500.00'))

    def test_an_encumbrance_is_reserved_not_spent(self):
        """ Money not yet charged; counting it would report a loss that may never come. """
        ParsedTransaction.objects.create(
            amount=Decimal('-400.00'), status=TransactionStatus.PENDING,
            effective_date=datetime.date(2025, 9, 20), fund_source=fund('legacy'),
            lnl_spend_category=category('event_subrental'), linked_event=self.event)
        figures = event_financials(self.event)
        self.assertEqual(figures['reserved'], Decimal('400.00'))
        self.assertEqual(figures['costs'], Decimal('0.00'))
        self.assertEqual(figures['margin'], Decimal('0.00'))

    def test_costing_more_than_it_brought_in_is_flagged(self):
        revenue(self.event, '1000.00', 'R1')
        cost(self.event, '-3000.00', 'C1')
        figures = event_financials(self.event)
        self.assertEqual(figures['margin'], Decimal('-2000.00'))
        self.assertIn('loss', figures['flag_keys'])

    def test_billed_is_the_latest_bill_not_the_total(self):
        """ A second bill is nearly always the first one, corrected. """
        Billing.objects.create(event=self.event, date_billed=datetime.date(2025, 10, 5),
                               amount=Decimal('4800.00'))
        Billing.objects.create(event=self.event, date_billed=datetime.date(2025, 10, 9),
                               amount=Decimal('5200.00'))
        billed, source = event_billed(self.event)
        self.assertEqual(billed, Decimal('5200.00'))
        self.assertEqual(source, 'bill')

    def test_billed_but_not_received_is_flagged(self):
        Billing.objects.create(event=self.event, date_billed=datetime.date(2025, 10, 5),
                               amount=Decimal('5200.00'))
        revenue(self.event, '5000.00', 'R1')
        self.assertIn('billed_not_received', event_financials(self.event)['flag_keys'])

    def test_money_received_with_no_bill_is_flagged(self):
        revenue(self.event, '5000.00', 'R1')
        figures = event_financials(self.event)
        self.assertIsNone(figures['billed'])
        self.assertIn('received_without_bill', figures['flag_keys'])

    def test_a_rental_hired_for_more_than_was_billed_is_flagged(self):
        """
        The client was billed $2,000 for the hire plus LNL's 15% fee, $2,300 in
        all; the hire cost $2,500.
        """
        Rental.objects.create(event=self.event, name='Video wall', cost=Decimal('2000.00'),
                              quantity=1, rental_fee_applied=True)
        cost(self.event, '-2500.00', 'C1')
        figures = event_financials(self.event)
        self.assertEqual(figures['rentals_billed'], Decimal('2000.00'))
        self.assertEqual(figures['rental_fee'], Decimal('300.00'))
        self.assertEqual(figures['rentals_recovered'], Decimal('2300.00'))
        self.assertEqual(figures['passthrough_cost'], Decimal('2500.00'))
        self.assertIn('rental_under_billed', figures['flag_keys'])

    def test_a_rental_covered_by_its_fee_is_not_flagged(self):
        Rental.objects.create(event=self.event, name='Video wall', cost=Decimal('2000.00'),
                              quantity=1, rental_fee_applied=True)
        cost(self.event, '-2200.00', 'C1')
        self.assertNotIn('rental_under_billed', event_financials(self.event)['flag_keys'])

    def test_no_itemised_rentals_means_no_rental_flag(self):
        """ Nothing billed for the hire to fall short of; the margin tells that story. """
        cost(self.event, '-2500.00', 'C1')
        self.assertNotIn('rental_under_billed', event_financials(self.event)['flag_keys'])

    def test_only_pass_through_costs_count_against_rentals(self):
        Rental.objects.create(event=self.event, name='Video wall', cost=Decimal('100.00'),
                              quantity=1)
        cost(self.event, '-900.00', 'C1', lnl_spend_category=category('consumables'))
        figures = event_financials(self.event)
        self.assertEqual(figures['passthrough_cost'], Decimal('0.00'))
        self.assertNotIn('rental_under_billed', figures['flag_keys'])

    def test_the_partition_narrows_the_entries(self):
        cost(self.event, '-300.00', 'C1', org='315-AG')
        cost(self.event, '-700.00', 'C2')
        self.assertEqual(event_financials(self.event, is_projection=True)['costs'],
                         Decimal('300.00'))
        self.assertEqual(event_financials(self.event, is_projection=False)['costs'],
                         Decimal('700.00'))


class MultiBillShareTests(TestCase):
    """ One figure for several shows, split by what each would have cost alone. """

    def setUp(self):
        self.org = OrgFactory(name='Orientation', shortname='NSO')
        self.big = make_event('NSO Concert', when(2025, 8, 20))
        self.small = make_event('NSO Social', when(2025, 8, 21))
        self.bill = MultiBilling.objects.create(
            org=self.org, date_billed=datetime.date(2025, 9, 1), amount=Decimal('900.00'))
        self.bill.events.set([self.big, self.small])

    def test_shares_follow_each_shows_price(self):
        EventArbitrary.objects.create(event=self.big, key_name='Stage', key_value=Decimal('200.00'))
        EventArbitrary.objects.create(event=self.small, key_name='Mic', key_value=Decimal('100.00'))
        self.assertEqual(event_billed(self.big), (Decimal('600.00'), 'multibill'))
        self.assertEqual(event_billed(self.small), (Decimal('300.00'), 'multibill'))

    def test_unpriced_shows_split_evenly_and_add_up_to_the_cent(self):
        self.bill.amount = Decimal('100.01')
        self.bill.save()
        first, _ = event_billed(self.big)
        second, _ = event_billed(self.small)
        self.assertEqual(first + second, Decimal('100.01'))
        self.assertEqual({first, second}, {Decimal('50.01'), Decimal('50.00')})


class EventPnlRowsTests(TestCase):
    """ The whole year's table. """

    def setUp(self):
        self.june = make_event('Spring Gala', when(2026, 6, 20))

    def test_an_event_counts_in_the_year_it_ran(self):
        """ A late-June show billed in July: one event, one year, all of its money. """
        revenue(self.june, '800.00', 'R1', date=datetime.date(2026, 7, 10))
        fy26 = event_pnl_rows(FY26)
        self.assertEqual([r['event'] for r in fy26], [self.june])
        self.assertEqual(fy26[0]['received'], Decimal('800.00'))
        self.assertEqual(event_pnl_rows(FY26 + 1), [])

    def test_worst_margin_first(self):
        winner = make_event('Talent Show', when(2025, 11, 1))
        revenue(winner, '900.00', 'R1')
        cost(self.june, '-500.00', 'C1')
        rows = event_pnl_rows(FY26)
        self.assertEqual([r['event'] for r in rows], [self.june, winner])

    def test_billed_events_with_nothing_linked_are_left_out_by_default(self):
        quiet = make_event('Quiet Recital', when(2025, 11, 1))
        Billing.objects.create(event=quiet, date_billed=datetime.date(2025, 11, 5),
                               amount=Decimal('150.00'))
        self.assertEqual(event_pnl_rows(FY26), [])
        rows = event_pnl_rows(FY26, include_unlinked=True)
        self.assertEqual([r['event'] for r in rows], [quiet])
        self.assertIn('billed_not_received', rows[0]['flag_keys'])

    def test_totals_add_the_rows_up(self):
        winner = make_event('Talent Show', when(2025, 11, 1))
        revenue(winner, '900.00', 'R1')
        cost(self.june, '-500.00', 'C1')
        totals = event_pnl_totals(event_pnl_rows(FY26))
        self.assertEqual(totals['received'], Decimal('900.00'))
        self.assertEqual(totals['costs'], Decimal('500.00'))
        self.assertEqual(totals['margin'], Decimal('400.00'))
        self.assertEqual(totals['losses'], 1)
        self.assertEqual(totals['events'], 2)


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class EventPnlPageTests(FinanceViewTestCase):

    def setUp(self):
        super(EventPnlPageTests, self).setUp()
        self.event = make_event('Pan Asian Festival', when(2025, 10, 4))
        revenue(self.event, '1000.00', 'R1')
        cost(self.event, '-3000.00', 'C1')

    def test_it_needs_the_view_permission(self):
        self.assertEqual(self.client.get(reverse('finance:events')).status_code, 403)

    def test_it_lists_the_event_and_its_margin(self):
        self.grant('view_subledger')
        response = self.client.get(reverse('finance:events') + '?fy=2026')
        self.assertContains(response, 'Pan Asian Festival')
        self.assertContains(response, '($2,000.00)')
        self.assertContains(response, 'Cost LNL more than it brought in')

    def test_a_flag_narrows_the_table_but_not_the_totals(self):
        self.grant('view_subledger')
        fine = make_event('Talent Show', when(2025, 11, 1))
        revenue(fine, '900.00', 'R2')
        response = self.client.get(reverse('finance:events') + '?fy=2026&flag=loss')
        self.assertEqual([r['event'] for r in response.context['rows']], [self.event])
        self.assertEqual(response.context['totals']['events'], 2)

    def test_the_dashboard_lists_events_that_lost_money(self):
        self.grant('view_subledger')
        response = self.client.get(reverse('finance:dashboard') + '?fy=2026')
        self.assertEqual([r['event'] for r in response.context['event_losses']], [self.event])


class LedgerEventFilterTests(FinanceViewTestCase):

    def setUp(self):
        super(LedgerEventFilterTests, self).setUp()
        self.grant('view_subledger')
        self.event = make_event('Spring Gala', when(2026, 6, 20))
        self.other = make_event('Talent Show', when(2025, 11, 1))

    def test_only_that_events_entries_are_shown(self):
        cost(self.event, '-500.00', 'C1', description='Gala rental')
        cost(self.other, '-200.00', 'C2', description='Talent rental')
        response = self.client.get(reverse('finance:ledger') + '?fy=2026&event=%s'
                                   % self.event.pk)
        self.assertContains(response, 'Gala rental')
        self.assertNotContains(response, 'Talent rental')

    def test_every_year_of_an_events_entries_is_shown(self):
        """ The event's July deposit sits in FY27 while the show ran in FY26. """
        revenue(self.event, '800.00', 'R1', date=datetime.date(2026, 7, 10),
                description='Gala deposit')
        response = self.client.get(reverse('finance:ledger') + '?fy=2026&event=%s'
                                   % self.event.pk)
        self.assertContains(response, 'Gala deposit')
        self.assertContains(response, 'across every fiscal year')

    def test_a_nonsense_event_is_ignored(self):
        self.assertOk(self.client.get(reverse('finance:ledger') + '?event=banana'))


class EventPageFinancePanelTests(FinanceViewTestCase):
    """ The Billing tab of the event's own page. """

    def setUp(self):
        super(EventPageFinancePanelTests, self).setUp()
        for codename in ('view_events', 'view_event_billing'):
            self.user.user_permissions.add(
                Permission.objects.get(codename=codename, content_type__app_label='events'))
        self.event = make_event('Pan Asian Festival', when(2025, 10, 4))
        cost(self.event, '-3000.00', 'C1')

    def _get(self):
        return self.client.get(reverse('events:detail', args=[self.event.pk]))

    def test_a_subledger_reader_sees_the_figures(self):
        self.grant('view_subledger')
        response = self._get()
        self.assertEqual(response.context['finance']['costs'], Decimal('3000.00'))
        self.assertContains(response, '1 subledger entry linked to this event')

    def test_nobody_else_does(self):
        self.grant()
        response = self._get()
        self.assertNotIn('finance', response.context)


class QueueEventTests(FinanceViewTestCase):
    """ How a queue row asks for, fills in and offers the event. """

    def setUp(self):
        super(QueueEventTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.drag = make_event('Drag Show', when(2025, 10, 4))

    def _line(self, op, memo):
        return WorkdayTransaction.objects.create(
            operational_transaction=op, accounting_date=datetime.date(2025, 10, 10),
            net_amount=Decimal('-100.00'), supplier='Gateway Productions', memo=memo,
            worktags_json={'ledger_account': '71500:Rent - Equipment',
                           'spend_category': 'Rent - Equipment'})

    def _row(self, txn):
        response = self.client.get(reverse('finance:queue') + '?fy=2026')
        rows = [row for row in response.context['rows'] if row['txn'].pk == txn.pk]
        return rows[0], response

    def test_a_named_event_is_filled_in_and_the_row_unfolds(self):
        txn = self._line('Q1', 'DT projector rental (Drag Show A25)')
        row, _ = self._row(txn)
        self.assertEqual(row['form'].initial['linked_event'], self.drag.pk)
        self.assertEqual(row['form'].autofilled['linked_event'].source, MEMO)
        self.assertTrue(row['expanded'])
        self.assertFalse(row['needs_event'])

    def test_a_pass_through_cost_with_no_event_is_tagged_and_unfolds(self):
        txn = self._line('Q2', 'Truck rental')
        row, response = self._row(txn)
        self.assertTrue(row['needs_event'])
        self.assertTrue(row['expanded'])
        self.assertContains(response, 'Which event?')

    def test_a_guess_is_a_chip_aimed_at_the_event_picker(self):
        """ queue.js finds the picker's hidden input from the chip's target. """
        festival = make_event('Pan Asian Festival', when(2025, 10, 5))
        txn = self._line('Q3', 'WPI Pan Asian Festival lighting and sound rental')
        row, response = self._row(txn)
        self.assertNotIn('linked_event', row['form'].autofilled)
        self.assertContains(response, 'data-target="id_txn%s-linked_event_text"' % txn.pk)
        self.assertContains(response, 'data-value="%s"' % festival.pk)

    def test_reconciling_with_an_event_files_it_as_a_pass_through(self):
        txn = self._line('Q4', 'Truck rental')
        self.client.post(reverse('finance:reconcile', args=[txn.pk]), {
            'txn%s-fund_source' % txn.pk: fund('legacy').pk,
            'txn%s-linked_event' % txn.pk: str(self.drag.pk),
        })
        entry = txn.slices.get()
        self.assertEqual(entry.linked_event, self.drag)
        self.assertEqual(entry.lnl_spend_category, category('event_subrental'))

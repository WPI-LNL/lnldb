"""
What the export tells us outright, and what we merely infer from it.

The distinction is the whole design of :mod:`finance.suggestions` and is worth
restating here, because every test below turns on it:

*Lookups* are facts the export states through a table somebody maintains in the
admin -- a Workday spend category mapped to an LNL one, a fund code, a project
code appearing verbatim. Those fill the form in.

*Guesses* are inferences: a word noticed in a memo, an event that ran near the
accounting date for roughly the right amount. Those are offered as a chip to
click and never fill anything in, because a pre-selected dropdown gets accepted
without being read, and that is precisely the wrong thing to do with a guess.

The routing suggestions (spend category, fund, project, funding request) are
covered alongside the forms that consume them in ``test_forms``. This module
covers the parts nothing else reaches: the scoring engine behind the event
picker, the refund-target search, and the small value type both produce.
"""
import datetime
from decimal import Decimal

from django.test import TestCase

from events.tests.generators import Event2019Factory, OrgFactory
from finance.models import FundSource, ParsedTransaction, SpendCategory, WorkdayTransaction
from finance.suggestions import (HIGH, LOW, MEDIUM, Suggestion,
                                 event_name_from_memo, event_name_from_transaction,
                                 suggest_linked_event, suggest_refund_targets)
from finance.tests.util import category, fund

SEP = datetime.date(2025, 9, 15)


def bank(op, amount, date=SEP, payee='B&H Photo', **worktags):
    return WorkdayTransaction.objects.create(
        operational_transaction=op, accounting_date=date,
        net_amount=Decimal(amount), supplier=payee,
        worktags_json=dict(worktags))


class SuggestionValueTests(TestCase):
    """ The little carrier every suggester returns. """

    def test_a_lookup_says_so_in_its_repr(self):
        """ Read in tracebacks and the shell, where the distinction matters most. """
        looked_up = Suggestion(7, HIGH, 'because the export said so', is_lookup=True)
        guessed = Suggestion(7, LOW, 'because a word appeared')
        self.assertIn('lookup', repr(looked_up))
        self.assertNotIn('lookup', repr(guessed))
        self.assertIn('7', repr(looked_up))

    def test_the_css_class_follows_the_confidence(self):
        self.assertEqual(Suggestion(1, HIGH, '').css_class, 'success')
        self.assertEqual(Suggestion(1, MEDIUM, '').css_class, 'info')
        self.assertEqual(Suggestion(1, LOW, '').css_class, 'default')

    def test_an_unrecognised_confidence_still_renders(self):
        """ A chip with no class is invisible, which is worse than a plain one. """
        self.assertEqual(Suggestion(1, 'wildly-unsure', '').css_class, 'default')

    def test_a_suggestion_is_a_guess_unless_it_says_otherwise(self):
        """ The safe default: filling a box in has to be asked for explicitly. """
        self.assertFalse(Suggestion(1, HIGH, 'reason').is_lookup)


class EventNameFromMemoTests(TestCase):
    """
    Pulling the event name out of an ISD memo.

    Every string here is copied verbatim from a real Workday export, because
    the point of this parser is that it survives how people actually write
    rather than how the format is described.
    """

    def test_the_house_format(self):
        self.assertEqual(
            event_name_from_memo('Lens and Lights Services for Pan Asian Festival D26'),
            'Pan Asian Festival')

    def test_the_verb_is_matched_case_insensitively(self):
        """ "services" and "Services" both turn up, sometimes in the same export. """
        self.assertEqual(
            event_name_from_memo('Lens and Lights services for ACFest D26'), 'ACFest')

    def test_the_abbreviated_prefix(self):
        self.assertEqual(
            event_name_from_memo('LNL Services for C26 CS Social Movies'),
            'CS Social Movies')

    def test_a_term_code_before_the_name_is_removed(self):
        """ The code moves around; it is stripped wherever it sits. """
        self.assertEqual(
            event_name_from_memo('LNL Services for C26 CS Social Movies'),
            'CS Social Movies')

    def test_a_term_code_inside_the_name_is_removed(self):
        self.assertEqual(
            event_name_from_memo('Lens and Lights services for RRC E26 Rental'),
            'RRC Rental')

    def test_the_commencement_code_is_removed(self):
        """ CM is a term code too, and does not follow the single-letter shape. """
        self.assertEqual(
            event_name_from_memo('Lens and Lights services for Commencement Activities CM26'),
            'Commencement Activities')

    def test_a_parenthetical_is_part_of_the_name(self):
        """
        Several shows run repeatedly and are told apart by a date in brackets.

        Dropping it would collapse four distinct events into one name.
        """
        self.assertEqual(
            event_name_from_memo(
                'Lens and Lights Services for Live at the CC Window (Apr 27) D26'),
            'Live at the CC Window (Apr 27)')

    def test_a_name_with_no_term_code_survives_intact(self):
        self.assertEqual(
            event_name_from_memo('Lens and Lights services for SMA Senior Night'),
            'SMA Senior Night')

    def test_a_journal_entry_memo_yields_nothing(self):
        """ SGA money quotes a request number; it is not event billing. """
        self.assertEqual(event_name_from_memo('F.26.86 Film Posters and Concessions'), '')

    def test_arbitrary_prose_yields_nothing(self):
        self.assertEqual(event_name_from_memo('VOX Q225 Theatre Software'), '')

    def test_an_empty_memo_yields_nothing(self):
        self.assertEqual(event_name_from_memo(''), '')
        self.assertEqual(event_name_from_memo(None), '')


class EventNameFromTransactionTests(TestCase):
    """
    The second memo shape: the event name alone, with no preamble.

    Safe only because of where it is read from and what is done with it -- an
    Internal Service Delivery is LNL invoicing somebody, and the name still has
    to match an event exactly before anything is filled in.
    """

    def _isd(self, memo):
        return WorkdayTransaction(
            operational_transaction='Internal Service Delivery: 25090179-ISD',
            accounting_date=SEP, net_amount=Decimal('500.00'), memo=memo)

    def test_a_bare_name_on_an_isd_is_read(self):
        self.assertEqual(event_name_from_transaction(self._isd('BRASA Carnival C26')),
                         'BRASA Carnival')

    def test_the_prefixed_form_still_wins_on_an_isd(self):
        txn = self._isd('Lens and Lights services for Drag Show D26')
        self.assertEqual(event_name_from_transaction(txn), 'Drag Show')

    def test_a_bare_name_on_a_journal_entry_is_not_read(self):
        """
        The document type is the whole of the safety margin here.

        Without the preamble there is nothing in the text saying this is an
        event, so it is only trusted on the one document type that means LNL
        invoiced somebody for work.
        """
        txn = WorkdayTransaction(operational_transaction='', accounting_date=SEP,
                                 net_amount=Decimal('500.00'), memo='Campus Movies')
        self.assertEqual(event_name_from_transaction(txn), '')

    def test_a_bare_name_on_a_supplier_invoice_is_not_read(self):
        txn = WorkdayTransaction(
            operational_transaction='Supplier Invoice: 25061136-SI',
            accounting_date=SEP, net_amount=Decimal('500.00'), memo='Drag Show C26')
        self.assertEqual(event_name_from_transaction(txn), '')


class SuggestLinkedEventTests(TestCase):
    """
    Matching the memo's event name against lnldb.

    Unlike everything else offered on a revenue line, this is a **lookup**: the
    memo is somebody writing down which event they were invoicing for, so
    reading it is reading their answer rather than guessing at it. That is what
    entitles it to fill the box in.
    """

    def setUp(self):
        self.org = OrgFactory(name='Alpha Club', shortname='ALPHA')
        self.event = Event2019Factory(event_name='Fall Concert', billing_org=self.org)
        self.event.datetime_start = datetime.datetime(2025, 9, 10, 19, 0,
                                                      tzinfo=datetime.timezone.utc)
        self.event.save()

    def _suggest(self, memo, amount='500.00', date=SEP):
        txn = WorkdayTransaction(
            operational_transaction='Internal Service Delivery: 25090179-ISD',
            accounting_date=date, net_amount=Decimal(amount), memo=memo)
        return suggest_linked_event(txn)

    def test_it_finds_the_event_the_memo_names(self):
        suggestion = self._suggest('Lens and Lights services for Fall Concert A26')
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.value, self.event.pk)

    def test_it_is_a_lookup_so_the_form_fills_the_box_in(self):
        """ The distinction this whole module turns on; see its docstring. """
        self.assertTrue(
            self._suggest('Lens and Lights services for Fall Concert A26').is_lookup)

    def test_it_is_offered_at_high_confidence(self):
        self.assertEqual(
            self._suggest('Lens and Lights services for Fall Concert A26').confidence, HIGH)

    def test_the_reason_names_the_date_so_the_year_can_be_checked(self):
        """
        A pre-filled box is the one nobody re-reads, so it has to say enough to
        be checked at a glance -- annual events differ only by year.
        """
        self.assertIn('2025',
                      self._suggest('Lens and Lights services for Fall Concert A26').reason)

    def test_the_name_matches_regardless_of_case(self):
        """ The same show is spelled both ways across one year of exports. """
        self.assertIsNotNone(self._suggest('Lens and Lights services for fall concert A26'))

    def test_an_expense_is_never_linked_this_way(self):
        """ The ISD memo format is about money coming in. """
        self.assertIsNone(self._suggest('Lens and Lights services for Fall Concert', '-500.00'))

    def test_a_memo_naming_no_event_yields_nothing(self):
        self.assertIsNone(self._suggest('Lens and Lights services for A Show We Never Did'))

    def test_a_journal_entry_memo_yields_nothing(self):
        txn = WorkdayTransaction(operational_transaction='', accounting_date=SEP,
                                 net_amount=Decimal('500.00'),
                                 memo='F.26.86 Film Posters')
        self.assertIsNone(suggest_linked_event(txn))

    def test_nothing_is_matched_partially(self):
        """
        Exact or nothing.

        A near-miss would silently attribute thousands of dollars of revenue to
        the wrong show, and it would do it in a box already showing an answer.
        """
        self.assertIsNone(self._suggest('Lens and Lights services for Fall'))
        self.assertIsNone(self._suggest('Lens and Lights services for Fall Concert Series'))

    def test_a_cancelled_event_is_never_offered(self):
        self.event.cancelled = True
        self.event.save()
        self.assertIsNone(self._suggest('Lens and Lights services for Fall Concert A26'))

    def test_a_test_event_is_never_offered(self):
        self.event.test_event = True
        self.event.save()
        self.assertIsNone(self._suggest('Lens and Lights services for Fall Concert A26'))

    def test_an_annual_event_resolves_to_the_year_being_billed(self):
        """
        The same show runs every year, so the name alone is ambiguous.

        The accounting date settles it: an ISD is raised within weeks of the
        show, so the nearest one is the one being invoiced.
        """
        last_year = Event2019Factory(event_name='Fall Concert', billing_org=self.org)
        last_year.datetime_start = datetime.datetime(2024, 9, 10, 19, 0,
                                                     tzinfo=datetime.timezone.utc)
        last_year.save()
        suggestion = self._suggest('Lens and Lights services for Fall Concert A26')
        self.assertEqual(suggestion.value, self.event.pk)

    def test_the_older_event_wins_when_that_is_the_one_being_billed(self):
        """ The same tie-break, pointing the other way. """
        last_year = Event2019Factory(event_name='Fall Concert', billing_org=self.org)
        last_year.datetime_start = datetime.datetime(2024, 9, 10, 19, 0,
                                                     tzinfo=datetime.timezone.utc)
        last_year.save()
        suggestion = self._suggest('Lens and Lights services for Fall Concert A25',
                                   date=datetime.date(2024, 9, 20))
        self.assertEqual(suggestion.value, last_year.pk)


class SuggestRefundTargetsTests(TestCase):
    """
    A positive line from a supplier we have paid before is probably a credit
    note. Which purchase it reverses is a guess, so it is offered as a list.
    """

    def setUp(self):
        self.purchase_txn = bank('OT-P1', '-129.00', payee='B&H Photo')
        self.purchase = ParsedTransaction.objects.create(
            parent_transaction=self.purchase_txn, amount=Decimal('-129.00'),
            effective_date=SEP, description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))

    def test_a_credit_finds_the_earlier_purchase_from_the_same_supplier(self):
        credit = bank('OT-C1', '129.00', date=SEP + datetime.timedelta(days=5))
        self.assertEqual([e.pk for e in suggest_refund_targets(credit)], [self.purchase.pk])

    def test_the_supplier_match_ignores_case(self):
        credit = bank('OT-C2', '129.00', payee='b&h photo',
                      date=SEP + datetime.timedelta(days=5))
        self.assertEqual([e.pk for e in suggest_refund_targets(credit)], [self.purchase.pk])

    def test_an_expense_line_has_nothing_to_refund(self):
        self.assertEqual(suggest_refund_targets(bank('OT-C3', '-50.00')), [])

    def test_a_credit_with_no_payee_finds_nothing(self):
        """ Without a supplier there is no signal at all, so nothing is offered. """
        credit = bank('OT-C4', '129.00', payee='')
        self.assertEqual(suggest_refund_targets(credit), [])

    def test_a_purchase_from_another_supplier_is_not_offered(self):
        other = bank('OT-P2', '-80.00', payee='Sweetwater')
        ParsedTransaction.objects.create(
            parent_transaction=other, amount=Decimal('-80.00'), effective_date=SEP,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        credit = bank('OT-C5', '129.00', date=SEP + datetime.timedelta(days=5))
        self.assertEqual([e.pk for e in suggest_refund_targets(credit)], [self.purchase.pk])

    def test_a_purchase_after_the_credit_is_not_offered(self):
        """ A credit reverses something that already happened. """
        later_txn = bank('OT-P3', '-40.00', date=SEP + datetime.timedelta(days=30))
        ParsedTransaction.objects.create(
            parent_transaction=later_txn, amount=Decimal('-40.00'),
            effective_date=SEP + datetime.timedelta(days=30),
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        credit = bank('OT-C6', '129.00', date=SEP + datetime.timedelta(days=5))
        self.assertEqual([e.pk for e in suggest_refund_targets(credit)], [self.purchase.pk])

    def test_it_matches_an_employee_reimbursement_too(self):
        """ A P-card line names an employee where an invoice names a supplier. """
        expense = WorkdayTransaction.objects.create(
            operational_transaction='OT-P4', accounting_date=SEP,
            net_amount=Decimal('-60.00'), supplier='', employee='Hannah Poirier')
        entry = ParsedTransaction.objects.create(
            parent_transaction=expense, amount=Decimal('-60.00'), effective_date=SEP,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        credit = WorkdayTransaction.objects.create(
            operational_transaction='OT-C7', accounting_date=SEP + datetime.timedelta(days=3),
            net_amount=Decimal('60.00'), supplier='', employee='Hannah Poirier')
        self.assertIn(entry.pk, [e.pk for e in suggest_refund_targets(credit)])

    def test_the_newest_purchases_come_first(self):
        recent_txn = bank('OT-P5', '-20.00', date=SEP + datetime.timedelta(days=2))
        recent = ParsedTransaction.objects.create(
            parent_transaction=recent_txn, amount=Decimal('-20.00'),
            effective_date=SEP + datetime.timedelta(days=2),
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        credit = bank('OT-C8', '10.00', date=SEP + datetime.timedelta(days=5))
        self.assertEqual([e.pk for e in suggest_refund_targets(credit)],
                         [recent.pk, self.purchase.pk])

    def test_the_list_is_capped(self):
        for index in range(12):
            txn = bank('OT-PB%s' % index, '-5.00')
            ParsedTransaction.objects.create(
                parent_transaction=txn, amount=Decimal('-5.00'), effective_date=SEP,
                fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        credit = bank('OT-C9', '5.00', date=SEP + datetime.timedelta(days=5))
        self.assertEqual(len(suggest_refund_targets(credit, limit=4)), 4)


class SuggestionVocabularyTests(TestCase):
    """
    Every suggester reads rows somebody maintains in the admin, so retiring one
    has to stop it being suggested without disturbing what is already filed.
    """

    def test_a_retired_category_stops_being_suggested(self):
        from finance.suggestions import suggest_spend_category
        txn = bank('OT-V1', '-40.00', spend_category='Supplies')
        self.assertIsNotNone(suggest_spend_category(txn))
        SpendCategory.objects.filter(slug='consumables').update(is_active=False)
        from finance.models import reset_finance_cache
        reset_finance_cache()
        self.assertIsNone(suggest_spend_category(txn))

    def test_a_retired_fund_stops_being_matched(self):
        from finance.models import fund_source_for_workday_fund, reset_finance_cache
        self.assertIsNotNone(fund_source_for_workday_fund('220-FD Gift'))
        FundSource.objects.filter(slug='legacy').update(is_active=False)
        reset_finance_cache('fund_codes')
        self.addCleanup(reset_finance_cache, 'fund_codes')
        self.assertIsNone(fund_source_for_workday_fund('220-FD Gift'))

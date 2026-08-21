import datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from events.tests.generators import (CategoryFactory, Event2019Factory, OrgFactory,
                                     ServiceFactory, ServiceInstanceFactory)
from finance.models import (ClientType, FRLineItem, FundingRequest, ParsedTransaction,
                            ProjectTag, TransactionStatus, WorkdayTransaction,
                            fiscal_year_bounds, fiscal_year_for, money)
from finance.templatetags.finance_extras import entry_badge
from finance.tests.util import category, fund, revenue_source


def make_txn(**kwargs):
    """ A Workday line with sensible defaults. """
    defaults = dict(
        operational_transaction=kwargs.pop('op', 'OT-%s' % WorkdayTransaction.objects.count()),
        accounting_date=datetime.date(2025, 9, 15),
        net_amount=Decimal('-1200.00'),
        supplier='B&H Photo',
        memo='Lighting order',
        worktags_json={'ledger_account': '71100:Supplies', 'spend_category': 'Supplies'},
    )
    defaults.update(kwargs)
    return WorkdayTransaction.objects.create(**defaults)


class FiscalYearTests(TestCase):
    """ WPI's FY runs Jul 1 -> Jun 30 and is named for the year it ends in. """

    def test_july_starts_next_fiscal_year(self):
        self.assertEqual(fiscal_year_for(datetime.date(2025, 7, 1)), 2026)
        self.assertEqual(fiscal_year_for(datetime.date(2025, 6, 30)), 2025)

    def test_bounds_are_inclusive(self):
        start, end = fiscal_year_bounds(2026)
        self.assertEqual(start, datetime.date(2025, 7, 1))
        self.assertEqual(end, datetime.date(2026, 6, 30))


class ImmutabilityTests(TestCase):
    """ Table A is the bank's version of events and may not be rewritten. """

    def test_can_be_created(self):
        txn = make_txn(op='OT-1')
        self.assertIsNotNone(txn.pk)

    def test_update_is_refused(self):
        txn = make_txn(op='OT-2')
        txn.net_amount = Decimal('-9999.00')
        with self.assertRaises(ValidationError):
            txn.save()

    def test_delete_is_refused(self):
        txn = make_txn(op='OT-3')
        with self.assertRaises(ValidationError):
            txn.delete()

    def test_one_operational_transaction_may_cover_many_lines(self):
        """
        A real supplier invoice is one Operational Transaction and a dozen
        exported lines, so the column cannot be an identifier.
        """
        make_txn(op='OT-INVOICE', net_amount=Decimal('-17.91'))
        make_txn(op='OT-INVOICE', net_amount=Decimal('-19.19'))
        self.assertEqual(
            WorkdayTransaction.objects.filter(operational_transaction='OT-INVOICE').count(), 2)

    def test_identical_lines_are_separate_occurrences(self):
        first = make_txn(op='OT-SAME', net_amount=Decimal('-19.99'), memo='Spotify')
        second = make_txn(op='OT-SAME', net_amount=Decimal('-19.99'), memo='Spotify')
        self.assertEqual(first.row_fingerprint, second.row_fingerprint)
        self.assertEqual([first.fingerprint_ordinal, second.fingerprint_ordinal], [1, 2])

    def test_an_occurrence_cannot_be_stored_twice(self):
        """ The database, not just the importer, refuses a doubled import. """
        first = make_txn(op='OT-ONCE', net_amount=Decimal('-5.00'))
        clash = WorkdayTransaction(
            operational_transaction='OT-ONCE', accounting_date=first.accounting_date,
            net_amount=first.net_amount, row_fingerprint=first.row_fingerprint,
            fingerprint_ordinal=1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                clash.save()

    def test_queryset_update_is_refused(self):
        """ queryset.update() bypasses Model.save(), so it needs its own guard. """
        make_txn(op='OT-QS1')
        with self.assertRaises(ValidationError):
            WorkdayTransaction.objects.filter(operational_transaction='OT-QS1').update(
                net_amount=Decimal('-1.00'))
        self.assertEqual(
            WorkdayTransaction.objects.get(operational_transaction='OT-QS1').net_amount,
            Decimal('-1200.00'))

    def test_queryset_delete_is_refused(self):
        make_txn(op='OT-QS2')
        with self.assertRaises(ValidationError):
            WorkdayTransaction.objects.filter(operational_transaction='OT-QS2').delete()
        self.assertTrue(
            WorkdayTransaction.objects.filter(operational_transaction='OT-QS2').exists())

    def test_hard_delete_is_the_explicit_escape_hatch(self):
        parent = make_txn(op='OT-QS3')
        ParsedTransaction.objects.create(
            parent_transaction=parent, amount=parent.net_amount, fund_source=fund('sga_budget'))
        WorkdayTransaction.objects.filter(operational_transaction='OT-QS3').hard_delete()
        self.assertFalse(
            WorkdayTransaction.objects.filter(operational_transaction='OT-QS3').exists())
        # The slices go with it, so a bad import can be backed out cleanly.
        self.assertFalse(ParsedTransaction.objects.filter(parent_transaction=parent).exists())


class PartitionDefaultTests(TestCase):
    """
    The org code says which account paid, and therefore where a slice starts.
    It is not a lock: LNL buys Projection gear out of the main 226-AG account
    whenever SGA funds it through a funding request, because the reimbursement
    comes back into 226-AG. The money is 226-AG money and the expense is a
    Projection expense at the same time.
    """

    def test_the_projection_account_is_detected(self):
        txn = make_txn(op='P1', worktags_json={'student_organization': '315-AG'})
        self.assertEqual(txn.default_partition, 'projection')
        self.assertTrue(txn.defaults_to_projection)

    def test_detected_with_trailing_description(self):
        txn = make_txn(op='P2', worktags_json={'student_organization': '315-AG Projection'})
        self.assertEqual(txn.default_partition, 'projection')
        self.assertEqual(txn.partition_code_label, '315-AG')

    def test_the_main_account_is_detected(self):
        txn = make_txn(op='E1', worktags_json={'student_organization': '226-AG'})
        self.assertEqual(txn.default_partition, 'event')
        self.assertFalse(txn.defaults_to_projection)

    def test_an_unknown_code_says_nothing(self):
        self.assertIsNone(
            make_txn(op='P3', worktags_json={'ledger_account': '71100:Supplies'}).default_partition)
        self.assertIsNone(make_txn(op='P4', worktags_json={}).default_partition)

    def test_main_account_money_may_be_projection_spending(self):
        """ The case the old lock made impossible to record. """
        parent = make_txn(op='E3', worktags_json={'student_organization': '226-AG'})
        entry = ParsedTransaction(parent_transaction=parent, amount=parent.net_amount,
                                  is_projection=True, fund_source=fund('sga_budget'),
                                  lnl_spend_category=category('consumables'))
        entry.full_clean()   # must not raise
        entry.save()
        entry.refresh_from_db()
        self.assertTrue(entry.is_projection)

    def test_that_crossing_is_marked(self):
        parent = make_txn(op='E3B', worktags_json={'student_organization': '226-AG'})
        entry = ParsedTransaction.objects.create(
            parent_transaction=parent, amount=parent.net_amount, is_projection=True,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        self.assertTrue(entry.crosses_partition)
        self.assertIn('226-AG', entry.partition_note)
        self.assertIn('Projection', entry.partition_note)

    def test_staying_on_the_default_side_is_not_a_crossing(self):
        parent = make_txn(op='E3C', worktags_json={'student_organization': '226-AG'})
        entry = ParsedTransaction.objects.create(
            parent_transaction=parent, amount=parent.net_amount, is_projection=False,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        self.assertFalse(entry.crosses_partition)
        self.assertEqual(entry.partition_note, '')

    def test_save_no_longer_overwrites_a_deliberate_answer(self):
        """
        save() used to force the flag back to the account's side, so a bulk
        action or a shell edit silently undid the Treasurer.
        """
        parent = make_txn(op='E4', worktags_json={'student_organization': '226-AG'})
        entry = ParsedTransaction.objects.create(
            parent_transaction=parent, amount=parent.net_amount, is_projection=True,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        entry.refresh_from_db()
        self.assertTrue(entry.is_projection)

    def test_an_unknown_code_leaves_the_choice_alone(self):
        parent = make_txn(op='E5', worktags_json={'ledger_account': '71100:Supplies'})
        self.assertIsNone(parent.default_partition)
        entry = ParsedTransaction(parent_transaction=parent, amount=parent.net_amount,
                                  is_projection=True, fund_source=fund('sga_budget'),
                                  lnl_spend_category=category('consumables'))
        entry.full_clean()   # must not raise
        entry.save()
        entry.refresh_from_db()
        self.assertTrue(entry.is_projection)
        self.assertFalse(entry.crosses_partition, "nothing to cross")


class ProjectionAccountNeedsAReasonTests(TestCase):
    """
    315-AG is funded by SGA directly for Projection, so money leaving that side
    is the direction that would breach the isolation the university cares
    about. Still allowed, but it has to be justified in writing.
    """

    def setUp(self):
        self.parent = make_txn(op='P5', worktags_json={'student_organization': '315-AG'})

    def _entry(self, **kwargs):
        values = dict(parent_transaction=self.parent, amount=self.parent.net_amount,
                      fund_source=fund('sga_budget'),
                      lnl_spend_category=category('consumables'))
        values.update(kwargs)
        return ParsedTransaction(**values)

    def test_the_flag_is_marked_as_needing_a_reason(self):
        self.assertTrue(self.parent.crossing_requires_reason)

    def test_leaving_the_projection_side_without_a_reason_is_refused(self):
        entry = self._entry(is_projection=False)
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn('audit_explanation', ctx.exception.error_dict)
        self.assertIn('315-AG', str(ctx.exception))

    def test_leaving_it_with_a_reason_is_allowed(self):
        entry = self._entry(is_projection=False,
                            audit_explanation='Recharged to Event Production per SGA.')
        entry.full_clean()   # must not raise
        entry.save()
        entry.refresh_from_db()
        self.assertFalse(entry.is_projection)
        self.assertTrue(entry.crosses_partition)

    def test_staying_on_the_projection_side_needs_no_reason(self):
        self._entry(is_projection=True).full_clean()   # must not raise

    def test_the_main_account_never_demands_one(self):
        """ Buying Projection gear from 226-AG is ordinary, so it only warns. """
        parent = make_txn(op='P7', worktags_json={'student_organization': '226-AG'})
        self.assertFalse(parent.crossing_requires_reason)
        ParsedTransaction(parent_transaction=parent, amount=parent.net_amount,
                          is_projection=True, fund_source=fund('sga_budget'),
                          lnl_spend_category=category('consumables')).full_clean()


class FundingRequestSetsThePartitionTests(TestCase):
    """
    An award was heard as either a Projection request or an Event Production
    one, and that is more specific than which account the money left from.
    """

    def setUp(self):
        self.parent = make_txn(op='FRP1', worktags_json={'student_organization': '226-AG'})
        self.request = FundingRequest.objects.create(
            name='Projector Lamp', reference='F.26.40', fiscal_year=2026, is_projection=True)
        self.line = FRLineItem.objects.create(
            funding_request=self.request, name='Lamp', amount_awarded=Decimal('900.00'))

    def _entry(self, **kwargs):
        values = dict(parent_transaction=self.parent, amount=Decimal('-500.00'),
                      fund_source=fund('sga_fr'), fr_line_target=self.line,
                      lnl_spend_category=category('consumables'))
        values.update(kwargs)
        return ParsedTransaction(**values)

    def test_a_projection_award_paid_from_the_main_account_is_projection(self):
        """ Exactly how LNL funds Projection: buy from 226-AG, SGA reimburses. """
        entry = self._entry(is_projection=False)
        entry.full_clean()   # must not raise
        entry.save()
        entry.refresh_from_db()
        self.assertTrue(entry.is_projection)
        self.assertTrue(entry.crosses_partition)

    def test_it_holds_without_validation_too(self):
        """ Bulk actions and shell writes skip full_clean(). """
        entry = ParsedTransaction.objects.create(
            parent_transaction=self.parent, amount=Decimal('-500.00'), is_projection=False,
            fund_source=fund('sga_fr'), fr_line_target=self.line,
            lnl_spend_category=category('consumables'))
        entry.refresh_from_db()
        self.assertTrue(entry.is_projection)

    def test_an_event_production_award_pulls_the_other_way(self):
        FundingRequest.objects.filter(pk=self.request.pk).update(is_projection=False)
        self.line.refresh_from_db()
        entry = self._entry(is_projection=True)
        entry.full_clean()
        entry.save()
        entry.refresh_from_db()
        self.assertFalse(entry.is_projection)

    def test_an_entry_with_no_award_keeps_its_own_answer(self):
        entry = ParsedTransaction.objects.create(
            parent_transaction=self.parent, amount=Decimal('-500.00'), is_projection=True,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        entry.refresh_from_db()
        self.assertTrue(entry.is_projection)


class PartitionMatcherTests(TestCase):
    def test_ledger_matcher_does_not_match_a_longer_code(self):
        from finance.models import org_code_matches
        self.assertTrue(org_code_matches('315-AG', '315-AG'))
        self.assertTrue(org_code_matches('315-AG Projection', '315-AG'))
        self.assertTrue(org_code_matches(' 315-ag ', '315-AG'))
        self.assertFalse(org_code_matches('315-AGX', '315-AG'))
        self.assertFalse(org_code_matches('1315-AG', '315-AG'))
        self.assertFalse(org_code_matches('', '315-AG'))
        self.assertFalse(org_code_matches(None, '315-AG'))


class RoutingExclusivityTests(TestCase):
    """ Rule 2: revenue and expense routing are mutually exclusive. """

    def setUp(self):
        self.event = Event2019Factory.create(event_name='Fall Concert')

    def test_revenue_cannot_carry_expense_routing(self):
        parent = make_txn(op='R1', net_amount=Decimal('500.00'))
        entry = ParsedTransaction(parent_transaction=parent, amount=Decimal('500.00'),
                                  linked_event=self.event, fund_source=fund('sga_budget'))
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn('fund_source', ctx.exception.error_dict)

    def test_expense_cannot_be_classified_as_non_event_revenue(self):
        parent = make_txn(op='R2')
        entry = ParsedTransaction(parent_transaction=parent, amount=Decimal('-1200.00'),
                                  non_event_revenue_type=revenue_source('alumni'),
                                  fund_source=fund('sga_budget'))
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn('non_event_revenue_type', ctx.exception.error_dict)

    def test_an_expense_may_name_the_event_it_was_incurred_for(self):
        """
        A sub-rental is one show's cost passed straight through. linked_event
        is the one routing field that belongs to both directions.
        """
        parent = make_txn(op='R2B')
        entry = ParsedTransaction(parent_transaction=parent, amount=Decimal('-1200.00'),
                                  linked_event=self.event, fund_source=fund('sga_budget'),
                                  lnl_spend_category=category('consumables'))
        entry.full_clean()
        entry.save()
        self.assertEqual(entry.linked_event, self.event)
        self.assertTrue(entry.is_expense)

    def test_revenue_must_route_somewhere(self):
        parent = make_txn(op='R3', net_amount=Decimal('500.00'))
        entry = ParsedTransaction(parent_transaction=parent, amount=Decimal('500.00'))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_revenue_cannot_be_both_event_and_non_event(self):
        parent = make_txn(op='R4', net_amount=Decimal('500.00'))
        entry = ParsedTransaction(parent_transaction=parent, amount=Decimal('500.00'),
                                  linked_event=self.event, non_event_revenue_type=revenue_source('alumni'))
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_database_rejects_expense_classified_as_non_event_revenue(self):
        """ The rule survives even if application-level validation is bypassed. """
        parent = make_txn(op='R5')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParsedTransaction.objects.create(
                    parent_transaction=parent, amount=Decimal('-1200.00'),
                    non_event_revenue_type=revenue_source('alumni'))

    def test_database_allows_an_expense_linked_to_an_event(self):
        parent = make_txn(op='R5B')
        entry = ParsedTransaction.objects.create(
            parent_transaction=parent, amount=Decimal('-1200.00'), linked_event=self.event)
        self.assertEqual(entry.linked_event, self.event)

    def test_database_rejects_zero_amount(self):
        parent = make_txn(op='R6')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParsedTransaction.objects.create(parent_transaction=parent, amount=Decimal('0.00'))


class SplitAndSettleTests(TestCase):
    """ Rule 1: a split must balance to the cent before anything can settle. """

    def setUp(self):
        self.parent = make_txn(op='S1', net_amount=Decimal('-1200.00'))

    def _slice(self, amount, **kwargs):
        kwargs.setdefault('fund_source', fund('sga_budget'))
        kwargs.setdefault('lnl_spend_category', category('consumables'))
        return ParsedTransaction.objects.create(
            parent_transaction=self.parent, amount=Decimal(amount), **kwargs)

    def test_unallocated_remainder_tracks_slices(self):
        self.assertEqual(self.parent.unallocated_amount, Decimal('-1200.00'))
        self._slice('-200.00')
        self.assertEqual(self.parent.unallocated_amount, Decimal('-1000.00'))
        self._slice('-1000.00')
        self.assertEqual(self.parent.unallocated_amount, Decimal('0.00'))
        self.assertTrue(self.parent.is_fully_allocated)

    def test_cannot_settle_while_unbalanced(self):
        entry = self._slice('-200.00')
        entry.status = TransactionStatus.SETTLED
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn('status', ctx.exception.error_dict)

    def test_can_settle_once_balanced(self):
        self._slice('-200.00')
        entry = self._slice('-1000.00')
        entry.status = TransactionStatus.SETTLED
        entry.full_clean()  # must not raise

    def test_settle_helper_refuses_unbalanced(self):
        self._slice('-200.00')
        with self.assertRaises(ValidationError):
            self.parent.settle()

    def test_settle_helper_settles_every_slice(self):
        self._slice('-200.00')
        self._slice('-1000.00')
        self.parent.settle()
        self.assertEqual(
            self.parent.slices.filter(status=TransactionStatus.SETTLED).count(), 2)
        self.assertTrue(self.parent.is_reconciled)

    def test_split_purchase_across_two_budgets(self):
        """ The $1,200 B&H invoice from the brief: $200 consumables, $1,000 capital. """
        fr = FundingRequest.objects.create(name='NEL26 Capital Grant')
        line = FRLineItem.objects.create(funding_request=fr, name='Fixtures',
                                         amount_awarded=Decimal('1000.00'))
        self._slice('-200.00', lnl_spend_category=category('consumables'))
        self._slice('-1000.00', lnl_spend_category=category('new_stuff'), fr_line_target=line)
        self.assertTrue(self.parent.is_fully_allocated)
        self.assertTrue(self.parent.is_split)
        self.assertEqual(line.spent, Decimal('1000.00'))
        self.assertEqual(line.remaining, Decimal('0.00'))


class EncumbranceTests(TestCase):
    """ Crew can reserve funds before the bank feed catches up. """

    def test_encumbrance_needs_no_parent(self):
        entry = ParsedTransaction(amount=Decimal('-75.00'), fund_source=fund('sga_budget'),
                                  lnl_spend_category=category('consumables'),
                                  description='Gaff tape run')
        entry.full_clean()
        entry.save()
        self.assertTrue(entry.is_encumbrance)
        self.assertEqual(entry.status, TransactionStatus.PENDING)

    def test_encumbrance_cannot_be_settled(self):
        entry = ParsedTransaction(amount=Decimal('-75.00'), fund_source=fund('sga_budget'),
                                  status=TransactionStatus.SETTLED)
        with self.assertRaises(ValidationError) as ctx:
            entry.full_clean()
        self.assertIn('status', ctx.exception.error_dict)

    def test_database_rejects_settled_encumbrance(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParsedTransaction.objects.create(
                    amount=Decimal('-75.00'), status=TransactionStatus.SETTLED)


class RefundTests(TestCase):
    """ Rule 3: a return credit must restore the budget line it came out of. """

    def setUp(self):
        self.fr = FundingRequest.objects.create(name='FY26 Ops')
        self.line = FRLineItem.objects.create(funding_request=self.fr, name='Consumables',
                                              amount_awarded=Decimal('1000.00'))
        purchase_parent = make_txn(op='F1', net_amount=Decimal('-400.00'))
        self.purchase = ParsedTransaction.objects.create(
            parent_transaction=purchase_parent, amount=Decimal('-400.00'),
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'),
            fr_line_target=self.line)

    def test_purchase_consumes_budget(self):
        self.assertEqual(self.line.spent, Decimal('400.00'))
        self.assertEqual(self.line.remaining, Decimal('600.00'))

    def test_refund_restores_budget(self):
        refund_parent = make_txn(op='F2', net_amount=Decimal('150.00'))
        ParsedTransaction.objects.create(
            parent_transaction=refund_parent, amount=Decimal('150.00'),
            refund_of=self.purchase, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'), fr_line_target=self.line)
        self.assertEqual(self.line.spent, Decimal('250.00'))
        self.assertEqual(self.line.remaining, Decimal('750.00'))

    def test_refund_is_classified_as_a_refund_not_revenue(self):
        refund_parent = make_txn(op='F3', net_amount=Decimal('150.00'))
        refund = ParsedTransaction.objects.create(
            parent_transaction=refund_parent, amount=Decimal('150.00'),
            refund_of=self.purchase, fund_source=fund('sga_budget'))
        self.assertEqual(refund.entry_type, ParsedTransaction.REFUND)
        self.assertTrue(refund.is_expense)
        self.assertFalse(refund.is_revenue)

    def test_refund_keeps_expense_routing(self):
        """ A refund carries expense routing; that is what makes it restore a budget. """
        refund_parent = make_txn(op='F4', net_amount=Decimal('150.00'))
        refund = ParsedTransaction(parent_transaction=refund_parent, amount=Decimal('150.00'),
                                   refund_of=self.purchase, fund_source=fund('sga_budget'),
                                   lnl_spend_category=category('consumables'))
        refund.full_clean()  # must not raise despite being positive

    def test_refund_cannot_reverse_revenue(self):
        rev_parent = make_txn(op='F5', net_amount=Decimal('500.00'))
        revenue = ParsedTransaction.objects.create(
            parent_transaction=rev_parent, amount=Decimal('500.00'),
            non_event_revenue_type=revenue_source('alumni'))
        bad = ParsedTransaction(amount=Decimal('50.00'), refund_of=revenue,
                                fund_source=fund('sga_budget'))
        with self.assertRaises(ValidationError) as ctx:
            bad.full_clean()
        self.assertIn('refund_of', ctx.exception.error_dict)

    def test_database_rejects_negative_refund(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ParsedTransaction.objects.create(
                    amount=Decimal('-50.00'), refund_of=self.purchase, fund_source=fund('sga_budget'))


class InheritedEventMetadataTests(TestCase):
    """ Zero double data entry: client type and services come from the Event. """

    def test_student_org_client_type_is_inherited(self):
        org = OrgFactory.create(name='Student Org', workday_fund=810)
        event = Event2019Factory.create(billing_org=org)
        entry = ParsedTransaction(amount=Decimal('500.00'), linked_event=event)
        self.assertEqual(entry.client_type, ClientType.STUDENT_ORG)

    def test_department_client_type_is_inherited(self):
        org = OrgFactory.create(name='Some Dept', workday_fund=110)
        event = Event2019Factory.create(billing_org=org)
        entry = ParsedTransaction(amount=Decimal('500.00'), linked_event=event)
        self.assertEqual(entry.client_type, ClientType.DEPARTMENT)

    def test_event_workday_fund_wins_over_org(self):
        org = OrgFactory.create(name='Mixed', workday_fund=110)
        event = Event2019Factory.create(billing_org=org, workday_fund=810)
        entry = ParsedTransaction(amount=Decimal('500.00'), linked_event=event)
        self.assertEqual(entry.client_type, ClientType.STUDENT_ORG)

    def test_unknown_without_event(self):
        self.assertEqual(ParsedTransaction(amount=Decimal('500.00')).client_type,
                         ClientType.UNKNOWN)

    def test_service_breakdown_is_inherited(self):
        event = Event2019Factory.create()
        lighting = CategoryFactory.create(name='Lighting')
        sound = CategoryFactory.create(name='Sound')
        ServiceInstanceFactory.create(event=event, service=ServiceFactory.create(category=lighting))
        ServiceInstanceFactory.create(event=event, service=ServiceFactory.create(category=sound))
        entry = ParsedTransaction(amount=Decimal('500.00'), linked_event=event)
        self.assertEqual(entry.event_services, ['Lighting', 'Sound'])


class FundingRequestBurndownTests(TestCase):
    def setUp(self):
        self.fr = FundingRequest.objects.create(name='NEL26')
        self.a = FRLineItem.objects.create(funding_request=self.fr, name='Fixtures',
                                           amount_awarded=Decimal('1000.00'))
        self.b = FRLineItem.objects.create(funding_request=self.fr, name='Cable',
                                           amount_awarded=Decimal('500.00'))

    def _spend(self, line, amount, op):
        parent = make_txn(op=op, net_amount=Decimal(amount))
        return ParsedTransaction.objects.create(
            parent_transaction=parent, amount=Decimal(amount), fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'), fr_line_target=line)

    def test_totals_roll_up(self):
        self.assertEqual(self.fr.total_awarded, Decimal('1500.00'))
        self._spend(self.a, '-250.00', 'B1')
        self.assertEqual(self.fr.total_spent, Decimal('250.00'))
        self.assertEqual(self.fr.total_remaining, Decimal('1250.00'))

    def test_percent_spent(self):
        self._spend(self.a, '-500.00', 'B2')
        self.assertEqual(self.a.percent_spent, 50)

    def test_overspend_is_flagged(self):
        self._spend(self.b, '-600.00', 'B3')
        self.assertTrue(self.b.is_overspent)
        self.assertEqual(self.b.overspent_by, Decimal('100.00'))
        self.assertTrue(self.fr.is_overspent is False)  # other line still has room


class ProjectTagTests(TestCase):
    """ Fully-loaded cost of an asset across years and funding sources. """

    def setUp(self):
        self.parent = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')
        self.child = ProjectTag.objects.create(name='D60 Lustrs', code='D60-LUSTR',
                                               parent=self.parent)

    def _spend(self, tag, amount, op, date=datetime.date(2025, 9, 1)):
        parent = make_txn(op=op, net_amount=Decimal(amount), accounting_date=date)
        return ParsedTransaction.objects.create(
            parent_transaction=parent, amount=Decimal(amount), effective_date=date,
            fund_source=fund('sga_budget'), lnl_spend_category=category('new_stuff'),
            project_tag=tag)

    def test_hierarchy(self):
        self.assertEqual(list(self.parent.children.all()), [self.child])
        self.assertEqual(self.child.parent, self.parent)

    def test_cost_rolls_up_from_descendants(self):
        self._spend(self.child, '-8000.00', 'T1')
        self._spend(self.parent, '-500.00', 'T2')
        self.assertEqual(self.child.total_cost(), Decimal('8000.00'))
        self.assertEqual(self.parent.total_cost(), Decimal('8500.00'))
        self.assertEqual(self.parent.total_cost(include_descendants=False), Decimal('500.00'))

    def test_cost_spans_fiscal_years(self):
        self._spend(self.child, '-8000.00', 'T3', datetime.date(2025, 9, 1))   # FY26
        self._spend(self.child, '-1000.00', 'T4', datetime.date(2026, 9, 1))   # FY27
        self.assertEqual(self.child.total_cost(), Decimal('9000.00'))
        self.assertEqual(self.child.total_cost(fiscal_year=2026), Decimal('8000.00'))
        self.assertEqual(self.child.total_cost(fiscal_year=2027), Decimal('1000.00'))

    def test_refund_reduces_asset_cost(self):
        purchase = self._spend(self.child, '-8000.00', 'T5')
        refund_parent = make_txn(op='T6', net_amount=Decimal('500.00'))
        ParsedTransaction.objects.create(
            parent_transaction=refund_parent, amount=Decimal('500.00'), refund_of=purchase,
            fund_source=fund('sga_budget'), project_tag=self.child,
            effective_date=datetime.date(2025, 10, 1))
        self.assertEqual(self.child.total_cost(), Decimal('7500.00'))

    def test_rollup_survives_a_stale_in_memory_node(self):
        """
        Regression: MPTT's cached tree bounds go stale as soon as anything else
        in the forest is written, and rolling up against them silently reported
        $0.00 instead of the real fully-loaded cost.
        """
        self._spend(self.child, '-1000.00', 'STALE1')
        self._spend(self.parent, '-500.00', 'STALE2')

        held = self.parent            # captured before the tree changes again
        ProjectTag.objects.create(name='Unrelated Project', code='UNREL')

        self.assertEqual(held.total_cost(), Decimal('1500.00'))
        self.assertEqual(held.total_cost(),
                         ProjectTag.objects.get(pk=held.pk).total_cost())

    def test_cannot_be_its_own_parent(self):
        from finance.forms import ProjectTagForm
        form = ProjectTagForm(instance=self.parent)
        self.assertNotIn(self.parent, form.fields['parent'].queryset)
        self.assertNotIn(self.child, form.fields['parent'].queryset)

    def test_indented_label_nests_sub_projects(self):
        self.assertEqual(self.parent.indented_label,
                         'NEL26 — New Equipment List 2026')
        child = ProjectTag.objects.get(pk=self.child.pk)
        label = child.indented_label
        # Non-breaking spaces: a plain space would be collapsed inside <option>.
        self.assertTrue(label.startswith('\u00a0\u00a0\u00a0\u00a0└ '), repr(label))
        self.assertIn('D60-LUSTR — D60 Lustrs', label)


class JournalLineMemoTests(TestCase):
    """ Description is seeded from the CSV's Journal Line Memo. """

    def test_reads_the_stored_worktag(self):
        txn = make_txn(op='JLM1', worktags_json={'journal_line_memo': 'NEL26 fixture order'},
                       memo='NEL26 fixture order — September purchases')
        self.assertEqual(txn.journal_line_memo, 'NEL26 fixture order')

    def test_falls_back_to_splitting_the_concatenated_memo(self):
        """ Rows imported before the memo was kept separately still work. """
        txn = make_txn(op='JLM2', worktags_json={},
                       memo='Lighting order — September purchases')
        self.assertEqual(txn.journal_line_memo, 'Lighting order')

    def test_handles_a_memo_with_no_header_half(self):
        txn = make_txn(op='JLM3', worktags_json={}, memo='Just the one memo')
        self.assertEqual(txn.journal_line_memo, 'Just the one memo')

    def test_blank_memo_is_empty_not_none(self):
        txn = make_txn(op='JLM4', worktags_json={}, memo='')
        self.assertEqual(txn.journal_line_memo, '')


class MoneyRoundingTests(TestCase):
    """
    Totals come back from the database as cents, not as float noise.

    SQLite quantizes a plain column read but not an aggregate, so ``Sum`` on a
    two-decimal column returns fifteen significant digits: ``-2808.24000000000``
    for a column that only ever held ``-2808.24``. Subtracting two of those
    gives ``Decimal('0E-11')``, which is zero, prints as ``0E-11``, and reads to
    a Treasurer as a bug in the ledger.
    """

    def setUp(self):
        self.txn = make_txn(op='OT-M1', net_amount=Decimal('-2808.24'))

    def test_money_quantizes_to_cents(self):
        self.assertEqual(str(money(Decimal('-2808.24000000000'))), '-2808.24')
        self.assertEqual(str(money(Decimal('0E-11'))), '0.00')
        self.assertEqual(str(money(None)), '0.00')
        self.assertEqual(str(money(Decimal('1'))), '1.00')

    def test_money_rounds_half_away_from_zero(self):
        self.assertEqual(str(money(Decimal('0.125'))), '0.13')
        self.assertEqual(str(money(Decimal('-0.125'))), '-0.13')

    def test_an_allocated_total_has_no_trailing_noise(self):
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-2808.24'),
            effective_date=self.txn.accounting_date,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        self.assertEqual(str(self.txn.allocated_amount), '-2808.24')

    def test_a_balanced_remainder_prints_as_zero(self):
        ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-2808.24'),
            effective_date=self.txn.accounting_date,
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        self.assertEqual(str(self.txn.unallocated_amount), '0.00')
        self.assertTrue(self.txn.is_fully_allocated)

    def test_a_split_remainder_is_exact(self):
        """ Three slices of a third of a dollar must still leave nothing over. """
        for amount in ('-936.08', '-936.08', '-936.08'):
            ParsedTransaction.objects.create(
                parent_transaction=self.txn, amount=Decimal(amount),
                effective_date=self.txn.accounting_date,
                fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))
        self.assertEqual(str(self.txn.unallocated_amount), '0.00')


class EncumbranceTypeTests(TestCase):
    """
    An encumbrance is money reserved for a purchase that has not happened. No
    money has left the account and there is no bank line behind it, so calling
    it an Expense made the two impossible to tell apart in the one column whose
    whole job is telling rows apart.
    """

    def _encumbrance(self, amount='-400.00'):
        return ParsedTransaction.objects.create(
            amount=Decimal(amount), effective_date=datetime.date(2025, 9, 15),
            description='Deposit on a console', fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'))

    def test_an_encumbrance_says_encumbrance(self):
        entry = self._encumbrance()
        self.assertEqual(entry.entry_type, ParsedTransaction.ENCUMBRANCE)
        self.assertEqual(entry.get_entry_type_display(), 'Encumbrance')

    def test_a_real_expense_still_says_expense(self):
        txn = make_txn(op='OT-E1', net_amount=Decimal('-400.00'))
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=Decimal('-400.00'),
            effective_date=txn.accounting_date, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self.assertEqual(entry.get_entry_type_display(), 'Expense')

    def test_it_still_routes_and_counts_as_expense_side(self):
        """ Only the label changed; an encumbrance is still money going out. """
        entry = self._encumbrance()
        self.assertTrue(entry.is_expense)
        self.assertFalse(entry.is_revenue)
        self.assertTrue(entry.is_encumbrance)
        self.assertIn(entry, ParsedTransaction.objects.expenses())

    def test_the_badge_is_its_own_colour(self):
        self.assertIn('Encumbrance', entry_badge(self._encumbrance()))
        self.assertIn('label-warning', entry_badge(self._encumbrance()))


class RefundPickerLabelTests(TestCase):
    """
    ``__str__`` is "Expense -129.00", which is what the Refund-of dropdown used
    to show: thirty options, all the same word and a number, with nothing to
    say which purchase each one was.
    """

    def setUp(self):
        self.txn = make_txn(op='OT-P1', net_amount=Decimal('-129.00'))
        self.entry = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-129.00'),
            effective_date=datetime.date(2025, 9, 15), description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))

    def test_the_label_identifies_the_purchase(self):
        label = self.entry.picker_label
        self.assertIn('Sep 15', label)
        self.assertIn('Gaff tape', label)
        self.assertIn('129.00', label)

    def test_the_payee_is_not_repeated_as_the_description(self):
        self.entry.description = self.txn.payee
        self.assertEqual(self.entry.picker_label.count(self.txn.payee), 1)

    def test_a_part_refunded_line_says_what_is_left(self):
        ParsedTransaction.objects.create(
            parent_transaction=make_txn(op='OT-P2', net_amount=Decimal('29.00')),
            amount=Decimal('29.00'), effective_date=datetime.date(2025, 9, 20),
            refund_of=self.entry, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self.assertIn('$100.00 left to refund', self.entry.picker_label)

    def test_a_fully_refunded_line_says_so(self):
        ParsedTransaction.objects.create(
            parent_transaction=make_txn(op='OT-P3', net_amount=Decimal('129.00')),
            amount=Decimal('129.00'), effective_date=datetime.date(2025, 9, 20),
            refund_of=self.entry, fund_source=fund('sga_budget'),
            lnl_spend_category=category('consumables'))
        self.assertIn('fully refunded', self.entry.picker_label)

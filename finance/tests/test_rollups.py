"""
The batch rollups, and the permission wiring a fresh install depends on.

Three things are covered here, and each of them is the kind of defect that
passes every functional test while being wrong:

**Batch figures must equal the per-row ones.** ``FundingRequest.total_awarded``
and ``ProjectTag.total_cost`` each grew a bulk counterpart so that a page
showing many rows costs a fixed number of queries. A bulk figure that disagreed
with the single-row figure would put one number on the list page and a
different number on the detail page for the same request, and nothing would
fail.

**They must actually be cheap.** The point of the annotations is the query
count, and a query count is invisible until someone measures it: the funding
list previously carried a ``prefetch_related`` that could not be read by any of
the properties consuming it, so it looked optimised and was not. The tests
below assert the counts stay flat as rows are added, which is the property that
matters and the one that silently regresses.

**Officers must be able to reach the app at all.** Every finance permission is
declared on a model, but a declared permission grants nothing until a group
holds it. ``fixtures/groups.json`` is what a fresh install loads, and finance
was missing from it entirely -- so the whole app was superuser-only on any
newly built database, which no view test can detect because view tests grant
their own permissions.
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from finance.models import (FRLineItem, FundingRequest, ParsedTransaction, ProjectTag,
                            WorkdayTransaction, project_tag_costs)
from finance.tests.util import fund

SEP = datetime.date(2025, 9, 15)


def _bank_line(reference, amount, date=SEP):
    """ One immutable Workday row to hang allocations off. """
    txn = WorkdayTransaction(operational_transaction=reference,
                             accounting_date=date, net_amount=Decimal(amount))
    txn.save()
    return txn


class FundingRequestRollupTest(TestCase):
    """ ``with_totals()`` against the properties it stands in for. """

    def setUp(self):
        self.fund = fund('sga_fr')

    def _request(self, name, lines=3, allocations=2):
        """ A request with ``lines`` awards, each charged ``allocations`` times. """
        fr = FundingRequest.objects.create(name=name, fiscal_year=2026)
        for index in range(lines):
            line = FRLineItem.objects.create(
                funding_request=fr, name='%s line %s' % (name, index),
                amount_awarded=Decimal('100.00'))
            for n in range(allocations):
                txn = _bank_line('%s-%s-%s' % (name, index, n), '-10.00')
                ParsedTransaction.objects.create(
                    parent_transaction=txn, amount=Decimal('-10.00'), effective_date=SEP,
                    fund_source=self.fund, fr_line_target=line)
        return fr

    def test_annotated_totals_match_the_properties(self):
        """
        The bulk figures and the per-row figures must be the same number.

        Both sums are taken as subqueries rather than joins precisely so they
        cannot multiply each other out; this is what would catch it if that
        ever changed.
        """
        self._request('Alpha')
        self._request('Beta', lines=2, allocations=4)
        # A request with no lines at all, and one with lines but no spending:
        # both are Coalesce branches that would otherwise go unexercised.
        FundingRequest.objects.create(name='Empty', fiscal_year=2026)
        bare = FundingRequest.objects.create(name='Unspent', fiscal_year=2026)
        FRLineItem.objects.create(funding_request=bare, name='untouched',
                                  amount_awarded=Decimal('75.00'))

        plain = {fr.pk: (fr.total_awarded, fr.total_spent, fr.total_remaining)
                 for fr in FundingRequest.objects.all()}
        annotated = {fr.pk: (fr.total_awarded, fr.total_spent, fr.total_remaining)
                     for fr in FundingRequest.objects.with_totals()}
        self.assertEqual(plain, annotated)

        # And the arithmetic itself, so a matching pair of wrong numbers fails.
        alpha = FundingRequest.objects.with_totals().get(name='Alpha')
        self.assertEqual(alpha.total_awarded, Decimal('300.00'))
        self.assertEqual(alpha.total_spent, Decimal('60.00'))
        self.assertEqual(alpha.total_remaining, Decimal('240.00'))

    def test_refunds_reduce_spend_through_the_annotation(self):
        """ A credit against an FR line restores its balance in bulk too. """
        fr = self._request('Gamma', lines=1, allocations=1)
        line = fr.line_items.get()
        original = line.allocations.get()
        credit = _bank_line('Gamma-credit', '4.00')
        ParsedTransaction.objects.create(
            parent_transaction=credit, amount=Decimal('4.00'), effective_date=SEP,
            fund_source=self.fund, fr_line_target=line, refund_of=original)

        annotated = FundingRequest.objects.with_totals().get(pk=fr.pk)
        self.assertEqual(annotated.total_spent, FundingRequest.objects.get(pk=fr.pk).total_spent)
        self.assertEqual(annotated.total_spent, Decimal('6.00'))

    def test_listing_query_count_does_not_grow_with_rows(self):
        """
        The whole point of the annotations: a flat cost per page.

        Reading the same properties the funding list template reads, over
        three requests and then over nine, must cost the same.
        """
        def cost():
            with CaptureQueriesContext(connection) as ctx:
                for fr in FundingRequest.objects.with_totals().with_lines():
                    fr.total_awarded, fr.total_spent, fr.total_remaining, fr.is_overspent
                    for line in fr.line_items.all():
                        line.spent, line.is_overspent
            return len(ctx)

        for name in ('One', 'Two', 'Three'):
            self._request(name)
        small = cost()

        for name in ('Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine'):
            self._request(name)
        large = cost()

        self.assertEqual(small, large)
        # Two selects: the requests with their subqueries, and the prefetched
        # lines. Pinned so a regression reads as a number, not a slowdown.
        self.assertEqual(large, 2)


class ProjectTagRollupTest(TestCase):
    """ ``project_tag_costs()`` against ``ProjectTag.total_cost()``. """

    def _spend(self, tag, amount, day):
        txn = _bank_line('PT-%s-%s' % (tag.code, day), amount,
                         date=datetime.date(2025, 9, day))
        return ParsedTransaction.objects.create(
            parent_transaction=txn, amount=Decimal(amount),
            effective_date=datetime.date(2025, 9, day), project_tag=tag)

    def _forest(self):
        """ Roots, children (one archived) and grandchildren, all with spend. """
        day = 1
        for i in range(3):
            root = ProjectTag.objects.create(name='Project %s' % i, code='P%s' % i)
            self._spend(root, '-50.00', day)
            day += 1
            for j in range(2):
                # An archived child still counts towards its parent's cost, so
                # the batch rollup has to see it too.
                child = ProjectTag.objects.create(
                    name='Asset %s%s' % (i, j), code='C%s%s' % (i, j),
                    parent=root, archived=(j == 1))
                self._spend(child, '-20.00', day)
                day += 1
                grandchild = ProjectTag.objects.create(
                    name='Part %s%s' % (i, j), code='G%s%s' % (i, j), parent=child)
                self._spend(grandchild, '-5.00', day)
                day += 1

    def test_batch_costs_match_total_cost_everywhere(self):
        """ Every node, rolled up and direct, against the per-node property. """
        self._forest()
        # A refund, so "net of refunds" is exercised on the batch path.
        root = ProjectTag.objects.get(code='P0')
        original = root.transactions.first()
        credit = _bank_line('PT-credit', '7.50')
        ParsedTransaction.objects.create(
            parent_transaction=credit, amount=Decimal('7.50'), effective_date=SEP,
            project_tag=root, refund_of=original)

        direct, rollup = project_tag_costs()
        for tag in ProjectTag.objects.all():
            self.assertEqual(rollup.get(tag.pk, Decimal('0.00')), tag.total_cost(),
                             "rollup disagrees for %s" % tag.code)
            self.assertEqual(direct.get(tag.pk, Decimal('0.00')),
                             tag.total_cost(include_descendants=False),
                             "direct cost disagrees for %s" % tag.code)

    def test_batch_costs_respect_the_fiscal_year(self):
        """ Scoping to a year must narrow the batch figures the same way. """
        tag = ProjectTag.objects.create(name='Spanning', code='SPAN')
        self._spend(tag, '-40.00', 5)
        old = _bank_line('PT-old', '-15.00', date=datetime.date(2024, 3, 1))
        ParsedTransaction.objects.create(
            parent_transaction=old, amount=Decimal('-15.00'),
            effective_date=datetime.date(2024, 3, 1), project_tag=tag)

        _direct, rollup = project_tag_costs(fiscal_year=2026)
        self.assertEqual(rollup[tag.pk], tag.total_cost(fiscal_year=2026))
        self.assertEqual(rollup[tag.pk], Decimal('40.00'))

    def test_tree_query_count_does_not_grow_with_nodes(self):
        """ Two queries for the whole forest, however many nodes it holds. """
        self._forest()
        with CaptureQueriesContext(connection) as ctx:
            project_tag_costs()
        small = len(ctx)

        for i in range(6):
            extra = ProjectTag.objects.create(name='Extra %s' % i, code='X%s' % i)
            self._spend(extra, '-9.00', 20 + i)
        with CaptureQueriesContext(connection) as ctx:
            project_tag_costs()

        self.assertEqual(small, len(ctx))
        # The spend aggregate, and one read of the tree's bounds.
        self.assertEqual(small, 2)


class GroupFixtureTest(TestCase):
    """
    The permissions a fresh install actually grants.

    Declaring a permission on a model creates the row; it does not put it in
    anybody's hands. ``README.md`` builds a new database with
    ``loaddata fixtures/*.json``, so this fixture is the only thing standing
    between a working install and a finance app no Officer can open.
    """

    #: Every permission the finance views and templates gate on. Kept as a
    #: literal rather than derived from the models, so that deleting a
    #: permission somewhere and dropping it from the fixture cannot agree with
    #: each other and pass.
    REQUIRED = {
        'view_subledger', 'edit_subledger', 'settle_subledger',
        'view_subledger_receipts', 'import_workdaytransaction',
        'manage_projecttag', 'manage_fundingrequest', 'view_fundingrequest',
    }

    def _held_by(self, group_name):
        """ The finance permissions one group holds after loading the fixture. """
        group = Group.objects.get(name=group_name)
        return set(group.permissions.filter(content_type__app_label='finance')
                   .values_list('codename', flat=True))

    def setUp(self):
        call_command('loaddata', 'fixtures/groups.json', verbosity=0)

    def test_officers_get_every_finance_permission(self):
        self.assertEqual(self.REQUIRED - self._held_by('Officer'), set(),
                         "fixtures/groups.json does not grant Officers these finance "
                         "permissions, so a fresh install cannot use the app")

    def test_active_members_get_read_only_access(self):
        """
        General membership sees the ledger and nothing else.

        Receipts are deliberately excluded: ``view_subledger_receipts`` exists
        precisely so that reading a ledger row and opening somebody's receipt
        are separate decisions, and granting both together would make it
        pointless.
        """
        held = self._held_by('Active')
        self.assertEqual(held, {'view_subledger', 'view_fundingrequest'})

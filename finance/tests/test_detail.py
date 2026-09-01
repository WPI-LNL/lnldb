"""
The two detail pages: one bank line, and one allocation slice.

The transaction page is where a purchase is carved into slices; the entry page
is where one slice gets its final shape and shows its history. Between them
they own the split formset, the audit trail, and the delete confirmation --
the parts of this app most likely to be reached only when something has already
gone slightly wrong.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse

from finance.models import ParsedTransaction, WorkdayTransaction
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund


class TransactionDetailTests(FinanceViewTestCase):
    """ The immutable Workday record on the left, the split interface on the right. """

    def setUp(self):
        super(TransactionDetailTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.txn = self.make_txn(op='OT-D1', amount='-1000.00')

    def _url(self):
        return reverse('finance:txn-detail', args=[self.txn.pk])

    def _split(self, *amounts, **kwargs):
        """ Post the split formset with one row per amount. """
        data = {
            'slices-TOTAL_FORMS': str(len(amounts)),
            'slices-INITIAL_FORMS': '0',
            'slices-MIN_NUM_FORMS': '0',
            'slices-MAX_NUM_FORMS': '1000',
        }
        for index, amount in enumerate(amounts):
            data.update({
                'slices-%s-amount' % index: amount,
                'slices-%s-description' % index: 'Slice %s' % index,
                'slices-%s-fund_source' % index: str(fund('sga_budget').pk),
                'slices-%s-lnl_spend_category' % index: str(category('consumables').pk),
            })
        data.update(kwargs)
        return self.client.post(self._url(), data, follow=True)

    def test_it_renders_the_workday_record(self):
        response = self.client.get(self._url())
        self.assertContains(response, 'OT-D1')

    def test_the_worktags_are_shown_in_readable_form(self):
        """ The export's own columns, so a Treasurer can check our reading of them. """
        response = self.client.get(self._url())
        self.assertContains(response, 'Ledger Account')

    def test_a_balancing_split_is_saved(self):
        response = self._split('-600.00', '-400.00')
        self.assertContains(response, 'balances to $0.00')
        self.assertEqual(self.txn.slices.count(), 2)
        self.assertEqual(self.txn.unallocated_amount, Decimal('0.00'))

    def test_a_split_that_does_not_balance_is_refused(self):
        """
        The mandate: slices sum to the bank line to the cent. This is the
        server-side half of the disabled Save button in the UI.
        """
        response = self._split('-600.00', '-300.00')
        self.assertEqual(self.txn.slices.count(), 0)
        self.assertContains(response, 'unallocated')

    def test_each_slice_inherits_the_bank_lines_date(self):
        """ Typed nowhere in the modal, so it has to come from the parent. """
        self._split('-1000.00')
        self.assertEqual(self.txn.slices.get().effective_date, self.txn.accounting_date)

    def test_each_slice_records_who_made_it(self):
        self._split('-1000.00')
        self.assertEqual(self.txn.slices.get().created_by, self.user)

    def test_a_split_is_recorded_in_the_audit_trail(self):
        from reversion.models import Version
        self._split('-600.00', '-400.00')
        entry = self.txn.slices.first()
        comment = Version.objects.get_for_object(entry)[0].revision.get_comment()
        self.assertIn('Split purchase across 2 allocations', comment)

    def test_removing_a_slice_from_the_formset_deletes_it(self):
        self._split('-600.00', '-400.00')
        first, second = list(self.txn.slices.order_by('pk'))
        data = {
            'slices-TOTAL_FORMS': '2',
            'slices-INITIAL_FORMS': '2',
            'slices-MIN_NUM_FORMS': '0',
            'slices-MAX_NUM_FORMS': '1000',
            'slices-0-id': str(first.pk),
            'slices-0-amount': '-1000.00',
            'slices-0-description': 'Everything',
            'slices-0-fund_source': str(fund('sga_budget').pk),
            'slices-0-lnl_spend_category': str(category('consumables').pk),
            'slices-1-id': str(second.pk),
            'slices-1-amount': '-400.00',
            'slices-1-description': 'Gone',
            'slices-1-fund_source': str(fund('sga_budget').pk),
            'slices-1-lnl_spend_category': str(category('consumables').pk),
            'slices-1-DELETE': 'on',
        }
        self.client.post(self._url(), data, follow=True)
        self.assertEqual(self.txn.slices.count(), 1)
        self.assertEqual(self.txn.unallocated_amount, Decimal('0.00'))

    def test_a_reader_cannot_split(self):
        stranger = get_user_model().objects.create_user(
            username='onlooker2', email='onlooker2@wpi.edu', password='x')
        from django.contrib.auth.models import Permission
        stranger.user_permissions.add(Permission.objects.get(codename='view_subledger'))
        self.client.force_login(get_user_model().objects.get(pk=stranger.pk))
        self._split('-1000.00')
        self.assertEqual(self.txn.slices.count(), 0)


class EntryDetailTests(FinanceViewTestCase):
    """ One slice, its form, and its history. """

    def setUp(self):
        super(EntryDetailTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'view_subledger_receipts')
        self.txn = self.make_txn(op='OT-D2', amount='-120.00')
        self.entry = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-120.00'),
            effective_date=self.txn.accounting_date, description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))

    def _url(self):
        return reverse('finance:entry-detail', args=[self.entry.pk])

    def _post(self, **overrides):
        data = {
            'amount': '-120.00',
            'effective_date': '2025-09-15',
            'description': 'Gaff tape',
            'fund_source': str(fund('sga_budget').pk),
            'lnl_spend_category': str(category('consumables').pk),
        }
        data.update(overrides)
        return self.client.post(self._url(), data, follow=True)

    def test_it_renders(self):
        self.assertContains(self.client.get(self._url()), 'Gaff tape')

    def test_an_edit_is_saved(self):
        self._post(description='Spike tape')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.description, 'Spike tape')

    def test_an_invalid_edit_is_refused_and_redisplayed(self):
        response = self._post(fund_source='')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.fund_source, fund('sga_budget'))
        self.assertContains(response, 'required')

    def test_an_edit_is_recorded_in_the_audit_trail(self):
        self._post(description='Spike tape')
        response = self.client.get(self._url())
        trail = response.context['audit_trail']
        self.assertTrue(trail)
        self.assertIn('Edited from the line item detail page', trail[0]['comment'])

    def test_the_trail_names_what_actually_changed(self):
        """
        Reversion stores a whole snapshot per revision, so the trail is built
        by diffing consecutive versions -- otherwise every entry would read
        "everything changed".
        """
        self._post(description='Spike tape')
        self._post(description='Spike tape', lnl_spend_category=str(category('repairs').pk))
        trail = self.client.get(self._url()).context['audit_trail']
        changed = [c['field'] for c in trail[0]['changes']]
        self.assertIn('Lnl Spend Category', changed)
        self.assertNotIn('Description', changed)

    def test_the_first_revision_is_marked_as_the_creation(self):
        self._post(description='Spike tape')
        trail = self.client.get(self._url()).context['audit_trail']
        self.assertTrue(trail[-1]['is_creation'])

    def test_an_unreadable_revision_degrades_rather_than_500s(self):
        """
        Reversion serialises against the schema of the day, so a field that
        later changed shape leaves older snapshots undeserialisable. Those are
        history and cannot be re-recorded, so the page says "saved this entry"
        instead of falling over.
        """
        import reversion
        from reversion.models import Version
        with reversion.create_revision():
            reversion.set_user(self.user)
            reversion.set_comment('Legacy shape')
            self.entry.save()
        version = Version.objects.get_for_object(self.entry)[0]
        version.serialized_data = '[{"model": "finance.parsedtransaction", "fields": {'
        version.save()

        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['unreadable'] for item in response.context['audit_trail']))

    def test_a_receipt_is_reported_as_missing_when_there_is_none(self):
        """ Optional, but a line without one is a line to chase. """
        self.assertContains(self.client.get(self._url()), 'No receipt attached')

    def test_an_entry_saves_without_paperwork(self):
        response = self._post(description='Spike tape')
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.audit_explanation, '')

    def test_a_reader_cannot_edit(self):
        from django.contrib.auth.models import Permission
        stranger = get_user_model().objects.create_user(
            username='onlooker3', email='onlooker3@wpi.edu', password='x')
        stranger.user_permissions.add(Permission.objects.get(codename='view_subledger'))
        self.client.force_login(get_user_model().objects.get(pk=stranger.pk))
        self._post(description='Vandalised')
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.description, 'Gaff tape')


class EntryDeleteTests(FinanceViewTestCase):
    """ Removing one slice. The bank line it belonged to is never touched. """

    def setUp(self):
        super(EntryDeleteTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger')
        self.txn = self.make_txn(op='OT-D3', amount='-120.00')
        self.entry = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-120.00'),
            effective_date=self.txn.accounting_date, description='Gaff tape',
            fund_source=fund('sga_budget'), lnl_spend_category=category('consumables'))

    def _url(self):
        return reverse('finance:entry-delete', args=[self.entry.pk])

    def test_a_get_only_asks(self):
        """ A destructive action never happens on a link being followed. """
        response = self.client.get(self._url())
        self.assertContains(response, 'Remove this allocation?')
        self.assertTrue(ParsedTransaction.objects.filter(pk=self.entry.pk).exists())

    def test_a_post_removes_the_slice(self):
        self.client.post(self._url(), follow=True)
        self.assertFalse(ParsedTransaction.objects.filter(pk=self.entry.pk).exists())

    def test_the_bank_line_survives_and_returns_to_the_queue(self):
        self.client.post(self._url(), follow=True)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.net_amount, Decimal('-120.00'))
        self.assertEqual(self.txn.unallocated_amount, Decimal('-120.00'))
        self.assertIn(self.txn, WorkdayTransaction.objects.unreconciled())

    def test_it_lands_back_on_the_bank_line(self):
        response = self.client.post(self._url(), follow=True)
        self.assertEqual(response.redirect_chain[-1][0],
                         reverse('finance:txn-detail', args=[self.txn.pk]))

    def test_removing_an_encumbrance_lands_on_the_ledger(self):
        """ There is no bank line to go back to, so the ledger is the fallback. """
        encumbrance = ParsedTransaction.objects.create(
            amount=Decimal('-400.00'), effective_date=datetime.date(2025, 9, 15),
            description='Deposit on a console', fund_source=fund('sga_budget'),
            lnl_spend_category=category('new_stuff'))
        response = self.client.post(
            reverse('finance:entry-delete', args=[encumbrance.pk]), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], reverse('finance:ledger'))

    def test_the_history_of_a_removed_slice_survives_it(self):
        """
        The deletion leaves no *new* version -- django-reversion drops any
        version whose row no longer exists, since a version is a snapshot of
        something that is there. What must survive is everything recorded
        before it, or removing an allocation would erase the account of it
        ever having been filed.
        """
        import reversion
        from reversion.models import Version

        with reversion.create_revision():
            reversion.set_user(self.user)
            reversion.set_comment('Reconciled from the ingestion queue')
            self.entry.save()
        pk = self.entry.pk

        self.client.post(self._url(), follow=True)

        self.assertFalse(ParsedTransaction.objects.filter(pk=pk).exists())
        surviving = Version.objects.get_for_object_reference(ParsedTransaction, pk)
        self.assertTrue(surviving, "the entry's history went with it")
        self.assertIn('Reconciled from the ingestion queue',
                      surviving[0].revision.get_comment())

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
from reversion.models import Version

from finance.models import ParsedTransaction, TransactionStatus, WorkdayTransaction
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
                'slices-%s-fund_source' % index: str(fund('legacy').pk),
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
        self.assertContains(response, 'add up to the')
        self.assertEqual(self.txn.slices.count(), 2)
        self.assertEqual(self.txn.unallocated_amount, Decimal('0.00'))

    def test_a_split_that_does_not_balance_is_refused(self):
        """
        The mandate: slices sum to the bank line to the cent. This is the
        server-side half of the disabled Save button in the UI.
        """
        response = self._split('-600.00', '-300.00')
        self.assertEqual(self.txn.slices.count(), 0)
        self.assertContains(response, 'left to settle')

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
        self.assertIn('Split purchase across 2 entries', comment)

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
            'slices-0-fund_source': str(fund('legacy').pk),
            'slices-0-lnl_spend_category': str(category('consumables').pk),
            'slices-1-id': str(second.pk),
            'slices-1-amount': '-400.00',
            'slices-1-description': 'Gone',
            'slices-1-fund_source': str(fund('legacy').pk),
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

    def _incurred_for_an_event(self):
        from events.tests.generators import Event2019Factory
        event = Event2019Factory(event_name='Pan Asian Festival')
        entry = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-1000.00'), fund_source=fund('legacy'),
            lnl_spend_category=category('event_subrental'), linked_event=event,
            audit_explanation='Hired for the festival', effective_date=self.txn.accounting_date)
        return event, entry

    def test_every_field_the_split_form_saves_is_on_the_page(self):
        """
        A model field the table leaves out is posted blank, and the formset
        saves the blank over the slice. That is how re-saving a split used to
        wipe the event an expense was incurred for, and every slice's audit
        note: the form declared both and the expense table rendered neither.
        """
        self._incurred_for_an_event()
        response = self.client.get(self._url())
        formset = response.context['formset']
        page = response.content.decode('utf-8')
        missing = []
        for form in formset:
            for name in form._meta.fields:
                # The bank line itself is the formset's own business: it comes
                # from the URL, not from anything posted.
                if name == formset.fk.name or name not in form.fields:
                    continue
                if ('name="%s"' % form.add_prefix(name)) not in page:
                    missing.append(form.add_prefix(name))
        self.assertEqual(missing, [])

    def test_re_saving_a_split_keeps_the_event_and_the_note(self):
        """
        The saved slice posted back with every field it rendered, and only the
        description changed. The blank spare rows are left out, as the other
        split tests here do.
        """
        event, entry = self._incurred_for_an_event()
        formset = self.client.get(self._url()).context['formset']
        saved = [form for form in formset if form.instance.pk]
        data = {'slices-TOTAL_FORMS': str(len(saved)),
                'slices-INITIAL_FORMS': str(len(saved)),
                'slices-MIN_NUM_FORMS': '0', 'slices-MAX_NUM_FORMS': '1000'}
        for form in saved:
            for name in tuple(form._meta.fields) + ('id',):
                if name in form.fields and name != formset.fk.name:
                    value = form[name].value()
                    data[form.add_prefix(name)] = '' if value is None else value
        data['slices-0-description'] = 'Video wall'
        self.client.post(self._url(), data, follow=True)

        entry.refresh_from_db()
        self.assertEqual(entry.description, 'Video wall')
        self.assertEqual(entry.linked_event_id, event.pk)
        self.assertEqual(entry.audit_explanation, 'Hired for the festival')

    def test_amounts_can_be_typed_without_a_minus(self):
        """ As they read on the receipt; the bank line says the money went out. """
        response = self._split('600.00', '400.00')
        self.assertContains(response, 'add up to the')
        self.assertEqual(sorted(self.txn.slices.values_list('amount', flat=True)),
                         [Decimal('-600.00'), Decimal('-400.00')])

    def test_a_new_row_can_be_removed_to_leave_it_out(self):
        """ Every row has the X and the hidden box it ticks, not only the saved ones. """
        page = self.client.get(self._url()).content.decode('utf-8')
        self.assertIn('name="slices-0-DELETE"', page)
        self.assertIn('name="slices-1-DELETE"', page)
        self.assertEqual(page.count('fin-row-drop'), page.count('fin-split-row'))
        self.assertNotIn('data-saved', page)
        self._split('1000.00', '250.00', **{'slices-1-DELETE': 'on'})
        self.assertEqual(list(self.txn.slices.values_list('amount', flat=True)),
                         [Decimal('-1000.00')])

    def test_a_removed_new_row_is_not_checked_at_all(self):
        """ It is hidden, so an error on it could never be seen or fixed. """
        self._split('1000.00', 'rubbish', **{'slices-1-DELETE': 'on'})
        self.assertEqual(list(self.txn.slices.values_list('amount', flat=True)),
                         [Decimal('-1000.00')])

    def test_the_request_sga_took_back_is_folded_under_the_line(self):
        """ One picker for spending; the request alone is the rare clawback. """
        self.assertContains(self.client.get(self._url()), 'SGA took money back?')

    def test_an_expense_slice_can_name_its_event_in_the_split(self):
        """ One rental invoice for two shows is divided here, one slice per show. """
        from events.tests.generators import Event2019Factory
        event = Event2019Factory(event_name='Drag Show')
        self._split('-600.00', '-400.00', **{'slices-1-linked_event': str(event.pk)})
        self.assertEqual(self.txn.slices.get(amount=Decimal('-400.00')).linked_event, event)


class SplitLeavesTheQueueTests(FinanceViewTestCase):
    """
    A split saved on this page, then the line in the queue.

    The amounts are a real purchase's: one Workday line of $7,324.72, two
    thirds from a funding request and the rest from Legacy. In floating point
    -4342.40 + -2982.32 is -7324.719999999999, and SQLite keeps money as
    floating point, so a balance checked in SQL saw a cent's fraction left over
    that nothing on the page could show.
    """
    _url = TransactionDetailTests._url
    _split = TransactionDetailTests._split

    def setUp(self):
        super(SplitLeavesTheQueueTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.txn = self.make_txn(op='OT-D95', amount='-7324.72')

    def _queue(self):
        return self.client.get(reverse('finance:queue'), {'fy': 'all'})

    def _in_queue(self):
        return WorkdayTransaction.objects.unreconciled().filter(pk=self.txn.pk).exists()

    def test_saving_a_balanced_split_takes_the_line_out_of_the_queue(self):
        """ The split cannot be saved unless it balances, so there is nothing left to settle. """
        self._split('-4342.40', '-2982.32')
        self.assertEqual(set(self.txn.slices.values_list('status', flat=True)),
                         {TransactionStatus.SETTLED})
        self.assertFalse(self._in_queue())
        self.assertTrue(WorkdayTransaction.objects.reconciled().filter(pk=self.txn.pk).exists())
        self.assertNotContains(self._queue(), 'OT-D95')

    def test_the_settle_is_in_each_entrys_history(self):
        """ Settled as it is saved, and the history says so, under the split's comment. """
        self._split('-4342.40', '-2982.32')
        for entry in self.txn.slices.all():
            version, = Version.objects.get_for_object(entry)
            self.assertEqual(version.field_dict['status'], TransactionStatus.SETTLED)
            self.assertEqual(version.revision.get_comment(), 'Split purchase across 2 entries')
            self.assertEqual(version.revision.user, self.user)

    def test_a_split_saved_without_the_settle_permission_waits_in_the_queue(self):
        from django.contrib.auth.models import Permission
        self.user.user_permissions.remove(Permission.objects.get(codename='settle_subledger'))
        self.client.force_login(get_user_model().objects.get(pk=self.user.pk))
        self._split('-4342.40', '-2982.32')
        self.assertEqual(set(self.txn.slices.values_list('status', flat=True)),
                         {TransactionStatus.PENDING})
        self.assertTrue(self._in_queue())
        # Waiting for a settle, not for more filing: no "Allocate $0.00".
        queue = self._queue()
        self.assertContains(queue, 'OT-D95')
        self.assertContains(queue, 'Ready to settle')
        self.assertNotContains(queue, 'Settle $0.00')

    def test_marking_it_settled_takes_the_line_out_of_the_queue(self):
        """ Slices left Pending, by whoever could not settle, settled from the page later. """
        for amount in ('-4342.40', '-2982.32'):
            ParsedTransaction.objects.create(
                parent_transaction=self.txn, amount=Decimal(amount), fund_source=fund('legacy'),
                lnl_spend_category=category('consumables'), effective_date=self.txn.accounting_date)
        self.assertTrue(self._in_queue())
        self.client.post(reverse('finance:settle', args=[self.txn.pk]), follow=True)
        self.assertFalse(self._in_queue())

    def test_the_queue_will_not_file_a_balanced_line_a_second_time(self):
        """ With nothing left to file, the queue used to file the whole line again. """
        self._split('-4342.40', '-2982.32')
        response = self.client.post(reverse('finance:reconcile', args=[self.txn.pk]), {
            'txn%s-fund_source' % self.txn.pk: fund('legacy').pk,
            'txn%s-lnl_spend_category' % self.txn.pk: category('consumables').pk,
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 400)
        self.assertIn('nothing left', str(response.json()['errors']))
        self.assertEqual(self.txn.slices.count(), 2)
        self.assertEqual(self.txn.unallocated_amount, Decimal('0.00'))

    def test_a_settled_split_can_be_split_again(self):
        """ Settling is not a lock: the Treasurer can still move money between the slices. """
        self._split('-4342.40', '-2982.32')
        first, second = list(self.txn.slices.order_by('pk'))
        data = {
            'slices-TOTAL_FORMS': '2', 'slices-INITIAL_FORMS': '2',
            'slices-MIN_NUM_FORMS': '0', 'slices-MAX_NUM_FORMS': '1000',
        }
        for index, (entry, amount) in enumerate(((first, '-4000.00'), (second, '-3324.72'))):
            data.update({
                'slices-%s-id' % index: str(entry.pk),
                'slices-%s-amount' % index: amount,
                'slices-%s-description' % index: entry.description,
                'slices-%s-fund_source' % index: str(entry.fund_source_id),
                'slices-%s-lnl_spend_category' % index: str(entry.lnl_spend_category_id),
            })
        response = self.client.post(self._url(), data, follow=True)
        self.assertContains(response, 'add up to the')
        self.assertEqual(sorted(self.txn.slices.values_list('amount', flat=True)),
                         [Decimal('-4000.00'), Decimal('-3324.72')])
        self.assertFalse(self._in_queue())

    def _resplit(self, rows):
        """ The settled split posted back as ``[(entry or None, amount, description)]``. """
        data = {
            'slices-TOTAL_FORMS': str(len(rows)),
            'slices-INITIAL_FORMS': str(len([row for row in rows if row[0] is not None])),
            'slices-MIN_NUM_FORMS': '0', 'slices-MAX_NUM_FORMS': '1000',
        }
        for index, (entry, amount, description) in enumerate(rows):
            data.update({
                'slices-%s-amount' % index: amount,
                'slices-%s-description' % index: description,
                'slices-%s-fund_source' % index: str(fund('legacy').pk),
                'slices-%s-lnl_spend_category' % index: str(category('consumables').pk),
            })
            if entry is not None:
                data['slices-%s-id' % index] = str(entry.pk)
        return self.client.post(self._url(), data, follow=True)

    def test_changing_a_settled_split_does_not_unsettle_it_without_the_settle_permission(self):
        """
        Saving the split reopened every row it changed, so someone who can't
        settle could unsettle a line by changing a description -- which Undo,
        Remove and the bulk bar all refuse them.
        """
        self._split('-4342.40', '-2982.32')
        first, second = list(self.txn.slices.order_by('pk'))
        self.revoke('settle_subledger')
        response = self._resplit([(first, '4000.00', 'Lamps'), (second, '3324.72', second.description)])
        self.assertContains(response, 'stays settled')
        self.assertEqual(sorted(self.txn.slices.values_list('amount', flat=True)),
                         [Decimal('-4000.00'), Decimal('-3324.72')])
        self.assertEqual(set(self.txn.slices.values_list('status', flat=True)),
                         {TransactionStatus.SETTLED})
        self.assertFalse(self._in_queue())

    def test_a_row_added_without_the_settle_permission_waits_to_be_settled(self):
        """ Only what was settled stays settled; the new row is for someone who can settle. """
        self._split('-4342.40', '-2982.32')
        first, second = list(self.txn.slices.order_by('pk'))
        self.revoke('settle_subledger')
        response = self._resplit([(first, '4342.40', first.description), (second, '2000.00', 'Cable'),
                                  (None, '982.32', 'Tape')])
        self.assertContains(response, 'that were settled stay settled')
        statuses = dict(self.txn.slices.values_list('description', 'status'))
        self.assertEqual(statuses['Cable'], TransactionStatus.SETTLED)
        self.assertEqual(statuses['Tape'], TransactionStatus.PENDING)
        self.assertTrue(self._in_queue())


class EntryDetailTests(FinanceViewTestCase):
    """ One slice, its form, and its history. """

    def setUp(self):
        super(EntryDetailTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'view_subledger_receipts')
        self.txn = self.make_txn(op='OT-D2', amount='-120.00')
        self.entry = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-120.00'),
            effective_date=self.txn.accounting_date, description='Gaff tape',
            fund_source=fund('legacy'), lnl_spend_category=category('consumables'))

    def _url(self):
        return reverse('finance:entry-detail', args=[self.entry.pk])

    def _post(self, **overrides):
        data = {
            'amount': '-120.00',
            'effective_date': '2025-09-15',
            'description': 'Gaff tape',
            'fund_source': str(fund('legacy').pk),
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
        self.assertEqual(self.entry.fund_source, fund('legacy'))
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
            fund_source=fund('legacy'), lnl_spend_category=category('consumables'))

    def _url(self):
        return reverse('finance:entry-delete', args=[self.entry.pk])

    def test_a_get_only_asks(self):
        """ A destructive action never happens on a link being followed. """
        response = self.client.get(self._url())
        self.assertContains(response, 'Remove this entry?')
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
            description='Deposit on a console', fund_source=fund('legacy'),
            lnl_spend_category=category('equipment_noncapital'))
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


class RemovingGuardTests(FinanceViewTestCase):
    """
    What can't be removed, and how the page says so.

    A purchase with a refund against it is held in place by the database, which
    raised a server error from both the entry page and the split's *Del* box.
    A settled entry needs the settle permission to remove, as Undo does.
    """

    def setUp(self):
        super(RemovingGuardTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.txn = self.make_txn(op='OT-RG1', amount='-100.00')
        self.purchase = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-100.00'),
            effective_date=self.txn.accounting_date, description='Gaff tape',
            fund_source=fund('legacy'), lnl_spend_category=category('consumables'),
            status=TransactionStatus.SETTLED)

    def _refund(self):
        credit = self.make_txn(op='OT-RG2', amount='40.00')
        return ParsedTransaction.objects.create(
            parent_transaction=credit, amount=Decimal('40.00'),
            effective_date=credit.accounting_date, description='Gaff tape returned',
            refund_of=self.purchase, fund_source=fund('legacy'),
            lnl_spend_category=category('consumables'), status=TransactionStatus.SETTLED)

    def _delete(self):
        return self.client.post(reverse('finance:entry-delete', args=[self.purchase.pk]), follow=True)

    def _split(self, txn, entry, **row):
        """ ``txn``'s split posted back with its one entry, as the page renders it. """
        data = {
            'slices-TOTAL_FORMS': '1', 'slices-INITIAL_FORMS': '1',
            'slices-MIN_NUM_FORMS': '0', 'slices-MAX_NUM_FORMS': '1000',
            'slices-0-id': str(entry.pk),
            'slices-0-amount': str(abs(entry.amount)),
            'slices-0-description': entry.description,
            'slices-0-fund_source': str(entry.fund_source_id),
        }
        data.update({'slices-0-%s' % name: value for name, value in row.items()})
        return self.client.post(reverse('finance:txn-detail', args=[txn.pk]), data, follow=True)

    def test_a_purchase_with_a_refund_is_not_removed_and_the_page_says_why(self):
        self._refund()
        page = self.client.get(reverse('finance:entry-delete', args=[self.purchase.pk]))
        self.assertContains(page, 'Remove the refund first')
        self.assertNotContains(page, 'Remove entry</button>')
        response = self._delete()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Remove the refund first')
        self.assertTrue(ParsedTransaction.objects.filter(pk=self.purchase.pk).exists())

    def test_a_settled_entry_needs_the_settle_permission_to_remove(self):
        self.revoke('settle_subledger')
        self.assertContains(self._delete(), "don&#x27;t have permission to unsettle it")
        self.assertTrue(ParsedTransaction.objects.filter(pk=self.purchase.pk).exists())

    def test_a_pending_entry_can_be_removed_without_it(self):
        self.revoke('settle_subledger')
        ParsedTransaction.objects.filter(pk=self.purchase.pk).update(status=TransactionStatus.PENDING)
        self._delete()
        self.assertFalse(ParsedTransaction.objects.filter(pk=self.purchase.pk).exists())

    def test_the_split_will_not_delete_a_purchase_with_a_refund(self):
        self._refund()
        response = self._split(self.txn, self.purchase, DELETE='on',
                               lnl_spend_category=str(category('consumables').pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Remove the refund first')
        self.assertTrue(ParsedTransaction.objects.filter(pk=self.purchase.pk).exists())

    def test_the_split_will_not_delete_a_settled_entry_without_the_settle_permission(self):
        self.revoke('settle_subledger')
        response = self._split(self.txn, self.purchase, DELETE='on',
                               lnl_spend_category=str(category('consumables').pk))
        self.assertContains(response, "don&#x27;t have permission to unsettle it")
        self.assertTrue(ParsedTransaction.objects.filter(pk=self.purchase.pk).exists())

    def test_a_refund_saved_again_on_the_split_keeps_its_purchases_routing(self):
        """
        The credit line's split shows the money-coming-in columns, which have
        no spend category or FR line. A refund is an expense, so they were
        posted blank and wiped.
        """
        refund = self._refund()
        self._split(refund.parent_transaction, refund, description='Gaff tape back')
        refund.refresh_from_db()
        self.assertEqual(refund.description, 'Gaff tape back')
        self.assertEqual(refund.lnl_spend_category, category('consumables'))
        self.assertEqual(refund.refund_of, self.purchase)


class RefundRoutingTests(FinanceViewTestCase):
    """
    A refund is charged where its purchase is, always.

    The queue copied the purchase's routing onto a refund when it was filed,
    but nothing kept the two together afterwards: the ledger's bulk bar or the
    refund's own page could move it to another fund, crediting money back to a
    fund that never spent it, and changing the purchase left the refund behind.
    """

    def setUp(self):
        super(RefundRoutingTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.txn = self.make_txn(op='OT-RR1', amount='-100.00')
        self.purchase = ParsedTransaction.objects.create(
            parent_transaction=self.txn, amount=Decimal('-100.00'),
            effective_date=self.txn.accounting_date, description='Gaff tape',
            fund_source=fund('legacy'), lnl_spend_category=category('consumables'),
            status=TransactionStatus.SETTLED)
        credit = self.make_txn(op='OT-RR2', amount='40.00')
        self.refund = ParsedTransaction.objects.create(
            parent_transaction=credit, amount=Decimal('40.00'),
            effective_date=credit.accounting_date, description='Gaff tape returned',
            refund_of=self.purchase, status=TransactionStatus.SETTLED)

    def _bulk(self, action, value, *entries):
        return self.client.post(reverse('finance:bulk-action'), {
            'action': action, action: str(value),
            'selected': ','.join(str(entry.pk) for entry in entries)}, follow=True)

    def test_a_refund_saved_with_no_routing_takes_its_purchases(self):
        self.refund.refresh_from_db()
        self.assertEqual((self.refund.fund_source, self.refund.lnl_spend_category),
                         (fund('legacy'), category('consumables')))

    def test_a_refund_cannot_be_moved_off_its_purchase(self):
        self.refund.fund_source = fund('legacy')
        self.refund.save()
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.fund_source, fund('legacy'))

    def test_changing_the_purchase_moves_its_refunds(self):
        self.purchase.fund_source = fund('legacy')
        self.purchase.lnl_spend_category = category('repairs')
        self.purchase.save()
        self.refund.refresh_from_db()
        self.assertEqual((self.refund.fund_source, self.refund.lnl_spend_category),
                         (fund('legacy'), category('repairs')))

    def test_the_bulk_bar_skips_a_refund_and_says_why(self):
        response = self._bulk('fund_source', fund('legacy').pk, self.refund)
        self.assertContains(response, '1 refund was skipped')
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.fund_source, fund('legacy'))

    def test_a_refund_ticked_with_its_purchase_moves_with_it(self):
        response = self._bulk('fund_source', fund('legacy').pk, self.purchase, self.refund)
        self.assertNotContains(response, 'skipped')
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.fund_source, fund('legacy'))

    def test_the_bulk_bar_skips_a_refund_for_a_spend_category_too(self):
        self._bulk('lnl_spend_category', category('repairs').pk, self.refund)
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.lnl_spend_category, category('consumables'))

    def test_the_refunds_page_shows_where_it_is_charged_instead_of_asking(self):
        page = self.client.get(reverse('finance:entry-detail', args=[self.refund.pk]))
        self.assertContains(page, 'so it is charged where the purchase is')
        self.assertNotContains(page, 'name="fund_source"')
        self.assertNotContains(page, 'name="lnl_spend_category"')

    def test_saving_the_refunds_page_keeps_its_purchases_routing(self):
        self.client.post(reverse('finance:entry-detail', args=[self.refund.pk]), {
            'amount': '40.00', 'effective_date': self.refund.effective_date.isoformat(),
            'description': 'Tape back', 'refund_of': str(self.purchase.pk),
            'fund_source': str(fund('legacy').pk)})
        self.refund.refresh_from_db()
        self.assertEqual(self.refund.description, 'Tape back')
        self.assertEqual(self.refund.fund_source, fund('legacy'))

    def _resplit_purchase(self, purchase_amount, other_amount):
        """ The purchase's line split again: the purchase at one amount, a new entry at the other. """
        data = {'slices-TOTAL_FORMS': '2', 'slices-INITIAL_FORMS': '1',
                'slices-MIN_NUM_FORMS': '0', 'slices-MAX_NUM_FORMS': '1000',
                'slices-0-id': str(self.purchase.pk)}
        for index, (amount, description) in enumerate(((purchase_amount, 'Gaff tape'),
                                                       (other_amount, 'Spike tape'))):
            data.update({'slices-%s-amount' % index: amount,
                         'slices-%s-description' % index: description,
                         'slices-%s-fund_source' % index: str(fund('legacy').pk),
                         'slices-%s-lnl_spend_category' % index: str(category('consumables').pk)})
        return self.client.post(reverse('finance:txn-detail', args=[self.txn.pk]), data, follow=True)

    def test_a_purchase_cannot_be_split_smaller_than_its_refunds(self):
        """ $40 came back against it, so $10 of it would give the fund back $30 never spent. """
        response = self._resplit_purchase('10.00', '90.00')
        self.assertContains(response, '$40.00 has been credited back against this purchase, so it '
                                      'can&#x27;t come to less than that')
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.amount, Decimal('-100.00'))
        self.assertEqual(self.txn.slices.count(), 1)

    def test_a_purchase_can_be_split_down_to_its_refunds(self):
        self._resplit_purchase('40.00', '60.00')
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.amount, Decimal('-40.00'))
        self.assertEqual(self.txn.slices.count(), 2)

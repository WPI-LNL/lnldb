"""
The problems the review before merging found, one test class for each.

Most of them don't show in ordinary use or on the development setup. Client
text in a message, a value retired after it was chosen, a bulk draw undone, an
ISD deleted with its bill, and a show starting late in the evening all need
something to have happened first. So each class sets that up and then does
what the Treasurer would do next.
"""
import csv
import datetime
import importlib
import io
import pathlib
import re
import weakref
from decimal import Decimal
from unittest import mock

import reversion
from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.contrib.messages import constants as message_levels
from django.contrib.messages.storage.base import Message
from django.contrib.messages.storage.cookie import MessageDecoder, MessageEncoder
from django.db.models.signals import post_save
from django.template import Context, Template
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from events.models import EventArbitrary, Organization
from events.tests.generators import OrgFactory
from finance.billing_forms import BillingEmailForm, MultiBillChargeForm, MultiBillingEmailForm
from finance.calculators import cash_flow_by_month, spend_by_category
from finance.filters import back_to
from finance.forms import AllocationForm
from finance.importers import ImportError_, _read_csv, import_workday_export
from finance.lookups import EventLookup
from finance.models import (Billing, FinanceSettings, FRLineItem, FundingRequest, MultiBilling, MultiBillingEmail,
                            ParsedTransaction, ProjectTag, TransactionStatus, _cached, changes_client_type, local_day,
                            reset_finance_cache, started_between)
from finance.reports import csv_cell
from finance.suggestions import _event_label
from finance.tests.test_billing import multibill, priced_event
from finance.tests.test_billing_page import bill as make_bill
from finance.tests.test_billing_page import show
from finance.tests.test_views import CSV_HEADER, CSV_ROW, FinanceViewTestCase
from finance.tests.util import category, fund, revenue_source
from finance.views import billing as billing_views

SEP = datetime.date(2025, 9, 15)


def rendered_data(form):
    """ What a browser posts for ``form`` as rendered: every field as it stands. """
    data = {}
    for field in form:
        value = field.value()
        if value in (None, False, ''):
            continue
        if getattr(field.field.widget, 'input_type', None) == 'file':
            continue
        data[field.html_name] = 'on' if value is True else str(value)
    return data


def formset_data(formset):
    """ The whole split table as a browser posts it. """
    data = {'%s-%s' % (formset.prefix, key): value
            for key, value in (('TOTAL_FORMS', len(formset.forms)), ('INITIAL_FORMS', formset.initial_form_count()),
                               ('MIN_NUM_FORMS', 0), ('MAX_NUM_FORMS', 1000))}
    for form in formset.forms:
        data.update(rendered_data(form))
    return data


class Entry(object):
    """ A settled $100 purchase on a bank line, for the tests to change around it. """

    def entry(self, amount='-100.00', **routing):
        routing.setdefault('fund_source', fund('legacy'))
        routing.setdefault('lnl_spend_category', category('consumables'))
        txn = self.make_txn(op='OT-%s' % ParsedTransaction.objects.count(), amount=amount,
                            memo=routing.pop('memo', 'Test line'))
        return ParsedTransaction.objects.create(
            parent_transaction=txn, amount=Decimal(amount), description='Gaff tape', effective_date=SEP,
            status=TransactionStatus.PENDING, **routing)

    def resave_entry(self, entry, **changes):
        """ Open the entry's page and save it, changing only ``changes``. """
        url = reverse('finance:entry-detail', args=[entry.pk])
        data = rendered_data(self.client.get(url).context['form'])
        data.update(changes)
        response = self.client.post(url, data, follow=True)
        entry.refresh_from_db()
        return response

    def resave_split(self, txn):
        """
        Open the bank line's page and save its split table with only the first
        row's description changed, which also says whether the save went through.
        """
        url = reverse('finance:txn-detail', args=[txn.pk])
        formset = self.client.get(url).context['formset']
        data = formset_data(formset)
        data['%s-0-description' % formset.prefix] = 'Saved from the split'
        return self.client.post(url, data, follow=True)


class MessagesAreEscapedTests(FinanceViewTestCase):
    """ #1: a client's event name reached the Treasurer's page as markup. """

    def setUp(self):
        super(MessagesAreEscapedTests, self).setUp()
        self.grant('bill_event')

    def test_an_event_name_in_a_message_is_not_markup(self):
        event = show('<img src=x onerror=alert(1)>')
        response = self.client.post(reverse('finance:no-bill-needed', args=[event.pk]),
                                    {'reason': 'other', 'note': 'Rehearsal'}, follow=True)
        self.assertIn('needs no bill', [str(m) for m in response.context['messages']][0])
        self.assertNotContains(response, '<img src=x')
        self.assertContains(response, '&lt;img src=x')

    def test_a_message_that_means_its_link_keeps_it_after_being_stored(self):
        """ Spotify's. Messages are stored between requests, and a link has to survive that. """
        stored = MessageEncoder().encode(Message(message_levels.WARNING, format_html('<a href="{}">{}</a>', '/x', '<b>')))
        html = Template('{{ message }}').render(Context({'message': MessageDecoder().decode(stored)}))
        self.assertEqual(html, '<a href="/x">&lt;b&gt;</a>')


class SettingsCacheTests(TestCase):
    """ #2: the signals that clear the cache were gone once Django started with DEBUG off. """

    def tearDown(self):
        reset_finance_cache()

    def test_the_receivers_are_held_strongly(self):
        """ A weak reference to a function local to ready() outlives nothing. """
        held = [row[1] for row in post_save.receivers if row[0][0] == 'finance.cache_save.FinanceSettings']
        self.assertEqual(len(held), 1)
        self.assertNotIsInstance(held[0], weakref.ReferenceType)

    def test_saving_a_row_changes_what_is_read(self):
        settings_row = FinanceSettings.objects.get(pk=1)
        from finance.models import fiscal_year_start_month
        self.assertEqual(fiscal_year_start_month(), settings_row.fiscal_year_start_month)
        settings_row.fiscal_year_start_month = 3
        settings_row.save()
        self.assertEqual(fiscal_year_start_month(), 3)

    def test_another_workers_copy_expires(self):
        """ Nothing tells the other workers about a save, so their copies have to run out. """
        self.assertEqual(_cached('review-test', lambda: 'first', None), 'first')
        self.assertEqual(_cached('review-test', lambda: 'second', None), 'first')
        with mock.patch('finance.models.CACHE_SECONDS', 0):
            self.assertEqual(_cached('review-test', lambda: 'second', None), 'second')


class SavedValuesStayOnOfferTests(Entry, FinanceViewTestCase):
    """ #3: something retired since was dropped by the next save of the entry. """

    def setUp(self):
        super(SavedValuesStayOnOfferTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')

    def test_an_archived_project_survives_fixing_a_typo(self):
        project = ProjectTag.objects.create(name='Old rig')
        entry = self.entry(project_tag=project)
        ProjectTag.objects.filter(pk=project.pk).update(archived=True)

        self.resave_entry(entry, description='Gaffer tape')

        self.assertEqual(entry.description, 'Gaffer tape')
        self.assertEqual(entry.project_tag, project)

    def test_a_retired_category_survives_the_split_page(self):
        spend = category('consumables')
        entry = self.entry(lnl_spend_category=spend)
        type(spend).objects.filter(pk=spend.pk).update(is_active=False)

        self.resave_split(entry.parent_transaction)

        entry.refresh_from_db()
        self.assertEqual(entry.description, 'Saved from the split')
        self.assertEqual(entry.lnl_spend_category, spend)

    def test_a_retired_fund_can_be_saved(self):
        retired = fund('legacy')
        entry = self.entry(fund_source=retired)
        type(retired).objects.filter(pk=retired.pk).update(is_active=False)

        self.resave_entry(entry, description='Gaffer tape')

        self.assertEqual(entry.description, 'Gaffer tape')
        self.assertEqual(entry.fund_source, retired)

    def test_a_retired_source_of_income_survives(self):
        source = revenue_source()
        entry = self.entry(amount='100.00', fund_source=fund('legacy'), lnl_spend_category=None,
                           non_event_revenue_type=source)
        type(source).objects.filter(pk=source.pk).update(is_active=False)

        self.resave_entry(entry, description='A gift')

        self.assertEqual(entry.description, 'A gift')
        self.assertEqual(entry.non_event_revenue_type, source)

    def test_what_is_retired_is_still_not_offered_to_anything_else(self):
        project = ProjectTag.objects.create(name='Old rig', archived=True)
        entry = self.entry()
        self.assertNotIn(project, AllocationForm(instance=entry).fields['project_tag'].queryset)
        retired = category('consumables')
        type(retired).objects.filter(pk=retired.pk).update(is_active=False)
        self.assertNotIn(retired, AllocationForm(parent_transaction=entry.parent_transaction)
                         .fields['lnl_spend_category'].queryset)


class BlankSplitRowsTests(Entry, FinanceViewTestCase):
    """
    Found while testing #3. Blank rows are drawn with the fund and category
    filled in, and a posted form isn't, so an unused row refused the save.
    """

    def setUp(self):
        super(BlankSplitRowsTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.saved = self.entry()
        self.url = reverse('finance:txn-detail', args=[self.saved.parent_transaction.pk])

    def test_a_row_left_blank_does_not_stop_the_save(self):
        form = self.client.get(self.url).context['formset'].forms[1]
        self.assertTrue(form['fund_source'].value(), "This needs a blank row drawn with its fund filled in.")
        self.resave_split(self.saved.parent_transaction)
        self.saved.refresh_from_db()
        self.assertEqual(self.saved.description, 'Saved from the split')
        self.assertEqual(self.saved.parent_transaction.slices.count(), 1)

    def test_a_row_with_an_amount_still_has_to_be_right(self):
        formset = self.client.get(self.url).context['formset']
        data = formset_data(formset)
        data['slices-1-amount'] = '50.00'
        response = self.client.post(self.url, data, follow=True)
        self.assertTrue(response.context['formset'].total_error_count() or
                        response.context['formset'].non_form_errors())
        self.assertEqual(self.saved.parent_transaction.slices.count(), 1)


class ClosedRequestTests(Entry, FinanceViewTestCase):
    """ #7: closing a request after SGA paid froze every entry charged to it. """

    def setUp(self):
        super(ClosedRequestTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        self.request = FundingRequest.objects.create(name='Fall lights', fiscal_year=2026)
        self.line = FRLineItem.objects.create(funding_request=self.request, name='Gels',
                                              amount_awarded=Decimal('500.00'))
        self.charged = self.entry(fund_source=fund('sga_fr'), fr_line_target=self.line)
        FundingRequest.objects.filter(pk=self.request.pk).update(closed=True)

    def test_an_entry_on_a_closed_request_can_be_saved(self):
        response = self.resave_entry(self.charged, description='Rosco gels')
        self.assertEqual(self.charged.description, 'Rosco gels', response.context.get('form') and
                         response.context['form'].errors)
        self.assertEqual(self.charged.fr_line_target, self.line)

    def test_the_split_page_saves_it_too(self):
        self.resave_split(self.charged.parent_transaction)
        self.charged.refresh_from_db()
        self.assertEqual(self.charged.description, 'Saved from the split')
        self.assertEqual(self.charged.fr_line_target, self.line)

    def test_a_closed_request_is_not_offered_to_another_entry(self):
        other = self.entry()
        self.assertNotIn(self.line, AllocationForm(instance=other).fields['fr_line_target'].queryset)


class BulkDrawUndoTests(FinanceViewTestCase):
    """
    #4: undoing a bulk draw's last line brought the whole encumbrance back.

    ``RevisionMiddleware`` makes the whole request one revision, so the line's
    history can't say what it held before the last draw. These go through the
    view, with that middleware, for that reason.
    """

    def setUp(self):
        super(BulkDrawUndoTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        from finance.tests.util import encumbrance
        self.header = encumbrance('Kit build', datetime.date(2025, 8, 1))
        # In a revision, as the form writes one: undoing reads this history.
        with reversion.create_revision():
            self.line = ParsedTransaction.objects.create(
                encumbrance=self.header, amount=Decimal('-1000.00'), status=TransactionStatus.PENDING,
                effective_date=datetime.date(2025, 8, 1), description='Kit build', fund_source=fund('legacy'),
                lnl_spend_category=category('consumables'))
        self.lines = [self.make_txn(op='SINV-%s' % amount, amount='-%s.00' % amount) for amount in (200, 300, 500)]
        self.client.post(reverse('finance:bulk-match-encumbrance'),
                         {'selected': ','.join(str(t.pk) for t in self.lines), 'encumbrance': str(self.line.pk)})
        self.line.refresh_from_db()

    def undo(self, txn):
        return self.client.post(reverse('finance:unreconcile', args=[txn.pk]), follow=True)

    def encumbered(self):
        return sum(abs(e.amount) for e in ParsedTransaction.objects.filter(parent_transaction__isnull=True))

    def charged(self):
        return sum(abs(e.amount) for e in ParsedTransaction.objects.filter(parent_transaction__isnull=False))

    def test_undoing_the_last_line_restores_only_what_it_took(self):
        self.assertEqual(self.line.parent_transaction, self.lines[2])
        self.undo(self.lines[2])
        self.assertEqual(self.encumbered(), Decimal('500.00'))
        self.assertEqual(self.charged(), Decimal('500.00'))

    def test_the_last_line_stretching_comes_back_at_what_was_left(self):
        """ The encumbrance had $500 left for a $505 charge, so $500 goes back, not $505. """
        self.client.post(reverse('finance:unreconcile', args=[self.lines[2].pk]))
        stretched = self.make_txn(op='SINV-505', amount='-505.00')
        entry = ParsedTransaction.objects.get(parent_transaction__isnull=True, amount=Decimal('-500.00'))
        self.client.post(reverse('finance:match-encumbrance', args=[stretched.pk]), {'encumbrance': str(entry.pk)})
        entry.refresh_from_db()
        self.assertEqual(entry.parent_transaction, stretched)
        self.assertEqual(entry.amount, Decimal('-505.00'))

        self.undo(stretched)

        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal('-500.00'))
        self.assertIsNone(entry.held_before_match)

    def test_undoing_every_line_comes_back_to_the_whole_encumbrance(self):
        for txn in reversed(self.lines):
            self.undo(txn)
        self.assertEqual(self.encumbered(), Decimal('1000.00'))
        self.assertEqual(self.charged(), Decimal('0'))

    def test_undoing_them_in_the_order_they_were_drawn_comes_to_the_same(self):
        for txn in self.lines:
            self.undo(txn)
        self.assertEqual(self.encumbered(), Decimal('1000.00'))
        self.assertEqual(self.charged(), Decimal('0'))


class EventDatesTests(FinanceViewTestCase):
    """ #5 and #15: an evening show is the next day in UTC, and MySQL needs help with __date. """

    def setUp(self):
        super(EventDatesTests, self).setUp()
        self.late = show('Late show')
        # 11pm on Sep 30 in Worcester, which is Oct 1 in UTC.
        self.late.datetime_start = timezone.make_aware(datetime.datetime(2025, 9, 30, 23, 0))
        self.late.save()
        self.late.refresh_from_db()

    def found(self, *days, **kwargs):
        return type(self.late).objects.filter(started_between(*days, **kwargs), pk=self.late.pk).exists()

    def test_a_late_show_belongs_to_the_day_it_ran(self):
        day = datetime.date(2025, 9, 30)
        self.assertTrue(self.found(day, day))
        self.assertFalse(self.found(day + datetime.timedelta(days=1), None))
        self.assertFalse(self.found(None, day - datetime.timedelta(days=1)))

    def test_no_limits_is_no_filter(self):
        self.assertTrue(self.found(None, None))

    def test_finance_does_not_use_date_lookups_on_datetimes(self):
        """
        The filters that came with this branch silently matched nothing on a
        MySQL without time-zone tables, which no SQLite test can show.
        """
        folder = pathlib.Path(apps.get_app_config('finance').path)
        pattern = re.compile(r'datetime_(start|end)__date')
        offenders = [str(path) for path in folder.rglob('*.py')
                     if 'tests' not in path.parts and pattern.search(path.read_text(encoding='utf-8'))]
        self.assertEqual(offenders, [])

    def test_the_labels_say_the_day_it_ran(self):
        self.assertTrue(_event_label(self.late).endswith('Sep 30, 2025'))
        self.assertIn('Sep 30, 2025', EventLookup().format_item_display(self.late))

    def test_a_date_passes_through(self):
        self.assertEqual(local_day(SEP), SEP)


class DashboardSpendingTests(Entry, FinanceViewTestCase):
    """ #6: money only encumbered was on the dashboard as spent. """

    def setUp(self):
        super(DashboardSpendingTests, self).setUp()
        self.grant('view_subledger')
        ParsedTransaction.objects.create(
            amount=Decimal('-750.00'), status=TransactionStatus.PENDING, effective_date=SEP,
            description='Order', fund_source=fund('legacy'), lnl_spend_category=category('consumables'))

    def test_an_encumbrance_is_not_spending(self):
        self.assertEqual(spend_by_category(fiscal_year=2026), [])
        self.assertEqual(sum(row['expense'] for row in cash_flow_by_month(fiscal_year=2026)), 0)
        response = self.client.get(reverse('finance:dashboard'), {'fy': 2026})
        self.assertEqual(response.context['total_expense'], 0)

    def test_a_charge_is(self):
        self.entry()
        self.assertEqual(spend_by_category(fiscal_year=2026)[0]['amount'], Decimal('100.00'))
        self.assertEqual(sum(row['expense'] for row in cash_flow_by_month(fiscal_year=2026)), Decimal('100.00'))
        response = self.client.get(reverse('finance:dashboard'), {'fy': 2026})
        self.assertEqual(response.context['total_expense'], Decimal('100.00'))

    def test_the_ledger_still_lists_it(self):
        self.assertEqual(ParsedTransaction.objects.expenses().count(), 1)
        self.assertEqual(ParsedTransaction.objects.spending().count(), 0)


class DeletingABillWithAnISDTests(FinanceViewTestCase):
    """ #8: the deleted bill's ISD left the worktag form locked, with no way to unlock it. """

    def setUp(self):
        super(DeletingABillWithAnISDTests, self).setUp()
        self.grant('bill_event')
        self.event = show('Spring Fest', client=OrgFactory())

    def record(self, bill, number='25090179-ISD'):
        bill.isd_number = number
        bill.isd_amount = Decimal('100.00')
        bill.isd_entered_on = datetime.date(2025, 9, 1)
        bill.save()
        self.event.entered_into_workday = True
        self.event.save()

    def delete(self):
        bill = self.event.billings.first()
        return self.client.post(reverse('finance:bill-delete', args=[self.event.pk, bill.pk]), follow=True)

    def warnings(self, response):
        return [str(m) for m in response.context['messages'] if m.level == message_levels.WARNING]

    def test_the_confirmation_says_the_isd_stays_in_workday(self):
        bill = make_bill(self.event)
        self.record(bill)
        response = self.client.get(reverse('finance:bill-delete', args=[self.event.pk, bill.pk]))
        self.assertContains(response, 'ISD 25090179-ISD for $100.00 is in Workday')

    def test_deleting_it_unlocks_the_worktag_form_and_warns(self):
        self.record(make_bill(self.event))
        response = self.delete()
        self.event.refresh_from_db()
        self.assertFalse(self.event.entered_into_workday)
        self.assertIn('does not cancel it', self.warnings(response)[0])

    def test_a_bill_with_no_isd_says_nothing_and_changes_nothing(self):
        make_bill(self.event)
        self.event.entered_into_workday = True
        self.event.save()
        response = self.delete()
        self.event.refresh_from_db()
        self.assertTrue(self.event.entered_into_workday)
        self.assertEqual(self.warnings(response), [])

    def test_a_second_bill_holding_an_isd_keeps_it_locked(self):
        doomed = make_bill(self.event)
        self.record(doomed)
        kept = make_bill(self.event)
        self.record(kept, number='25090180-ISD')
        self.client.post(reverse('finance:bill-delete', args=[self.event.pk, doomed.pk]))
        self.event.refresh_from_db()
        self.assertTrue(self.event.entered_into_workday)

    def test_a_multibill_unlocks_each_of_its_events(self):
        other = show('Spring Fest II')
        bill = multibill(self.event, other, name='Festival')
        bill.isd_number, bill.isd_amount = '25090179-ISD', Decimal('100.00')
        bill.isd_entered_on = datetime.date(2025, 9, 1)
        bill.save()
        for event in (self.event, other):
            event.entered_into_workday = True
            event.save()

        response = self.client.post(reverse('finance:multibill-delete', args=[bill.pk]), follow=True)

        self.assertFalse(MultiBilling.objects.filter(pk=bill.pk).exists())
        self.assertIn('does not cancel it', self.warnings(response)[0])
        for event in (self.event, other):
            event.refresh_from_db()
            self.assertFalse(event.entered_into_workday)


class CrossYearOnTheSplitPageTests(Entry, FinanceViewTestCase):
    """ #9: the split page insisted on a tick box it did not have. """

    def setUp(self):
        super(CrossYearOnTheSplitPageTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        request = FundingRequest.objects.create(name='Last year', fiscal_year=2025)
        self.line = FRLineItem.objects.create(funding_request=request, name='Gels', amount_awarded=Decimal('500.00'))
        self.charged = self.entry(fund_source=fund('sga_fr'), fr_line_target=self.line)
        self.url = reverse('finance:txn-detail', args=[self.charged.parent_transaction.pk])

    def test_the_box_is_on_the_page_and_ticked(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="slices-0-allow_cross_year_fr"')
        self.assertTrue(response.context['formset'].forms[0]['allow_cross_year_fr'].value())

    def test_saving_the_row_as_it_stands_is_accepted(self):
        self.resave_split(self.charged.parent_transaction)
        self.charged.refresh_from_db()
        self.assertEqual(self.charged.description, 'Saved from the split')
        self.assertEqual(self.charged.fr_line_target, self.line)


class OfficerPermissionsTests(TestCase):
    """ #10: nothing gave the finance permissions to an Officer on an existing database. """

    def setUp(self):
        self.migration = importlib.import_module('finance.migrations.0006_officer_finance_permissions')
        self.officer = Group.objects.create(name='Officer')

    def held(self):
        return set(self.officer.permissions.values_list('codename', flat=True))

    def test_officers_get_all_nine(self):
        self.migration.grant_to_officers(apps, None)
        self.assertEqual(self.held(), {codename for codename, _ in self.migration.OFFICER_PERMISSIONS})

    def test_what_they_held_is_kept(self):
        kept = Permission.objects.get(codename='bill_event')
        self.officer.permissions.add(kept)
        self.migration.grant_to_officers(apps, None)
        self.assertIn('bill_event', self.held())

    def test_permissions_not_created_yet_are_made(self):
        """ Django makes them after migrations, so a first deploy gets here without them. """
        Permission.objects.filter(content_type__app_label='finance').delete()
        self.migration.grant_to_officers(apps, None)
        self.assertEqual(Permission.objects.get(codename='view_subledger').name, 'View the financial subledger')
        self.assertEqual(Permission.objects.get(codename='view_fundingrequest').name,
                         'Can view Funding Request')

    def test_with_no_officer_group_there_is_nothing_to_do(self):
        self.officer.delete()
        self.migration.grant_to_officers(apps, None)
        self.assertFalse(Group.objects.filter(name='Officer').exists())

    def test_it_matches_the_fixture(self):
        import json
        with open('fixtures/groups.json', encoding='utf-8') as fixture:
            groups = json.load(fixture)
        officer = next(group for group in groups if group['fields']['name'] == 'Officer')
        finance = {row[0] for row in officer['fields']['permissions'] if row[1] == 'finance'}
        self.assertEqual(finance, {codename for codename, _ in self.migration.OFFICER_PERMISSIONS})


class BillingInTheMenuTests(FinanceViewTestCase):
    """ #10: the old Billing links are gone, so this menu has to reach whoever bills. """

    def menu(self):
        html = self.client.get(reverse('finance:billing')).content.decode()
        found = re.search(r'Finance\s*<b class="caret"></b>\s*</a>\s*<ul class="dropdown-menu">(.*?)</ul>', html, re.S)
        return re.findall(r'<a href="[^"]*">([^<]+)</a>', found.group(1)) if found else None

    def test_someone_who_only_bills_sees_billing(self):
        self.grant('bill_event')
        self.assertEqual(self.menu(), ['Billing'])


class ClientWorktagOnFileTests(FinanceViewTestCase):
    """
    #11: one show paid from elsewhere moved the client between Student Org and
    Department. The form still keeps the rest of what the client sends on file,
    which is what the billing plan decided.
    """

    def setUp(self):
        super(ClientWorktagOnFileTests, self).setUp()
        self.grant('edit_org_billing', 'view_events')
        self.org = OrgFactory(workday_fund=810, worktag='1111-AA')
        self.event = show('Spring Fest', client=self.org)
        make_bill(self.event)

    def submit(self, fund_code, worktag):
        return self.client.post(reverse('events:worktag-form', args=[self.event.pk]),
                                {'workday_fund': fund_code, 'worktag': worktag, 'workday_form_comments': '',
                                 'submit': 'Pay'})

    def on_file(self):
        self.org.refresh_from_db()
        return self.org.workday_fund, self.org.worktag

    def test_a_new_worktag_on_the_same_fund_goes_on_file(self):
        self.submit(810, '2222-BB')
        self.assertEqual(self.on_file(), (810, '2222-BB'))

    def test_a_department_changing_fund_goes_on_file(self):
        Organization.objects.filter(pk=self.org.pk).update(workday_fund=110)
        self.submit(120, '2222-BB')
        self.assertEqual(self.on_file(), (120, '2222-BB'))

    def test_a_fund_of_the_other_kind_stays_on_the_event_only(self):
        self.submit(110, '2222-BB')
        self.assertEqual(self.on_file(), (810, '1111-AA'))
        self.event.refresh_from_db()
        self.assertEqual((self.event.workday_fund, self.event.worktag), (110, '2222-BB'))

    def test_a_client_with_nothing_on_file_gets_it(self):
        Organization.objects.filter(pk=self.org.pk).update(workday_fund=None, worktag=None)
        self.submit(110, '2222-BB')
        self.assertEqual(self.on_file(), (110, '2222-BB'))

    def test_the_check_itself(self):
        self.assertTrue(changes_client_type(self.org, 110))
        self.assertFalse(changes_client_type(self.org, 810))
        self.assertFalse(changes_client_type(self.org, None))


class EmailRecipientsTests(TestCase):
    """ #12: the bill's own Bill to could not be chosen as who the email goes to. """

    def setUp(self):
        self.club = OrgFactory(name='Attached club', exec_email='club@wpi.edu')
        self.office = OrgFactory(name='Billing office', exec_email='office@wpi.edu')

    def test_a_multibill_offers_and_ticks_its_bill_to(self):
        event = priced_event('Film', '100.00', org=self.office)
        event.org.add(self.club)
        form = MultiBillingEmailForm(multibill(event, org=self.office))
        self.assertEqual(set(form.fields['email_to_orgs'].queryset), {self.club, self.office})
        self.assertEqual(form.fields['email_to_orgs'].initial, self.office)

    def test_a_bill_to_on_no_event_at_all(self):
        event = priced_event('Film', '100.00')
        event.org.add(self.club)
        form = MultiBillingEmailForm(multibill(event, org=self.office))
        self.assertIn(self.office, form.fields['email_to_orgs'].queryset)

    def test_a_single_bill_offers_the_billing_org(self):
        event = priced_event('Film', '100.00', org=self.office)
        event.org.add(self.club)
        bill = Billing.objects.create(event=event, amount=Decimal('100.00'), date_billed=SEP)
        self.assertEqual(set(BillingEmailForm(bill).fields['email_to_orgs'].queryset), {self.club, self.office})


class InvoiceTotalTests(TestCase):
    """ #13: a re-sent invoice printed today's prices, not the figure the client was given. """

    def setUp(self):
        self.film = priced_event('Film', '500.00')
        self.bill = multibill(self.film, name='Films')

    def sent(self):
        self.bill.sent_on = datetime.date(2026, 3, 2)
        self.bill.save()

    def raise_the_price(self):
        EventArbitrary.objects.filter(event=self.film).update(key_value=Decimal('650.00'))
        self.bill.refresh_from_db()

    def test_before_it_is_sent_it_follows_the_prices(self):
        self.raise_the_price()
        data = billing_views.get_multibill_data(self.bill)
        self.assertEqual(data['total_cost'], Decimal('650.00'))
        self.assertEqual(data['adjustment'], 0)

    def test_once_sent_it_is_the_saved_figure_and_still_adds_up(self):
        self.sent()
        self.raise_the_price()
        data = billing_views.get_multibill_data(self.bill)
        self.assertEqual(data['total_cost'], Decimal('500.00'))
        self.assertEqual(data['adjustment'], Decimal('-150.00'))
        self.assertEqual(data['breakdown']['total'] + data['adjustment'], data['total_cost'])

    def test_a_paid_bill_keeps_its_figure(self):
        self.bill.date_paid = datetime.date(2026, 3, 9)
        self.bill.save()
        self.raise_the_price()
        self.assertEqual(billing_views.get_multibill_data(self.bill)['total_cost'], Decimal('500.00'))

    def test_update_total_moves_it_on_purpose(self):
        self.sent()
        self.raise_the_price()
        self.bill.recalculate()
        data = billing_views.get_multibill_data(self.bill)
        self.assertEqual((data['total_cost'], data['adjustment']), (Decimal('650.00'), 0))

    def test_an_email_sent_last_counts_as_sent(self):
        MultiBillingEmail.objects.create(multibilling=self.bill, subject='Bill', message='Bill',
                                         sent_at=timezone.now())
        self.raise_the_price()
        self.assertEqual(billing_views.get_multibill_data(self.bill)['total_cost'], Decimal('500.00'))


class FirstSendingTests(FinanceViewTestCase):
    """ #13: the first email is the moment the figure reaches the client, so it has to be saved. """

    def test_the_first_email_saves_what_it_says(self):
        self.grant('bill_event')
        client = OrgFactory(exec_email='club@wpi.edu')
        film = priced_event('Film', '500.00', org=client)
        bill = multibill(film, org=client, name='Films')
        EventArbitrary.objects.filter(event=film).update(key_value=Decimal('650.00'))

        with mock.patch('finance.views.billing.multibill_invoice_pdf', return_value=b'%PDF'), \
                mock.patch('finance.views.billing.DLEG'):
            self.client.post(reverse('finance:multibill-email', args=[bill.pk]),
                             {'subject': 'Bill', 'message': 'Bill', 'email_to_orgs': [client.pk],
                              'email_to_users': '|'})

        bill.refresh_from_db()
        self.assertEqual(bill.amount, Decimal('650.00'))


class FormulaCellsTests(Entry, FinanceViewTestCase):
    """ #14: a client's event name reached Excel as a formula. """

    def test_text_that_would_run_gets_an_apostrophe(self):
        for text in ('=HYPERLINK("http://evil","Open")', '+1+1', '@SUM(A1)', '-2+3', '\tx'):
            self.assertEqual(csv_cell(text), "'" + text)

    def test_everything_else_is_left_alone(self):
        for value in ('Spring Fest', '-120.50', '+15', '-1,200.00', '', Decimal('-5.00'), 12, None):
            self.assertEqual(csv_cell(value), value)

    def test_the_ledger_download(self):
        self.grant('view_subledger')
        self.entry(memo='=cmd|calc')
        response = self.client.get(reverse('finance:ledger'), {'format': 'csv', 'fy': 2026})
        rows = list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(rows[0]['Memo'], "'=cmd|calc")


class SmallerProblemsTests(Entry, FinanceViewTestCase):
    """ The ones below the cut: a 500 each, and a label. """

    def test_a_csv_too_broken_to_read_says_so(self):
        raw = (CSV_HEADER + '\n"' + 'x' * 200000 + '\n').encode('utf-8')
        with self.assertRaises(ImportError_):
            _read_csv(raw)

    def test_a_long_operational_transaction_is_cut_to_fit(self):
        row = CSV_ROW.replace('OT-9001', 'X' * 200)
        import_workday_export(io.BytesIO((CSV_HEADER + '\n' + row + '\n').encode('utf-8')), filename='journal.csv')
        txn = type(self.make_txn(op='other')).objects.exclude(operational_transaction='other').get()
        self.assertEqual(len(txn.operational_transaction), 128)

    def test_a_year_no_calendar_holds_is_ignored(self):
        self.grant('view_subledger')
        for year in ('99999', '1', '0', '²'):
            self.assertOk(self.client.get(reverse('finance:dashboard'), {'fy': year}))

    def test_a_year_already_remembered_is_ignored_too(self):
        self.grant('view_subledger')
        session = self.client.session
        session['finance_fy'] = 99999
        session.save()
        self.assertOk(self.client.get(reverse('finance:dashboard')))

    def test_a_round_rental_fee_reads_as_a_number(self):
        with mock.patch('finance.billing_forms.default_rental_fee_percent', return_value=Decimal('20.00')):
            self.assertEqual(MultiBillChargeForm().fields['add_rental_fee'].label, 'Add the 20% rental fee')

    def test_a_redirect_only_goes_to_this_site(self):
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger')
        txn = self.make_txn()
        for path, outside in ((reverse('finance:settle', args=[txn.pk]), 'https://evil.example/'),
                              (reverse('finance:bulk-action'), '//evil.example/')):
            response = self.client.post(path, {'next': outside})
            self.assertNotIn('evil.example', response['Location'])

    def test_a_page_of_ours_is_still_where_it_goes_back_to(self):
        request = mock.Mock(POST={'next': '/db/finance/queue/?page=2'}, GET={})
        request.get_host.return_value = 'testserver'
        request.is_secure.return_value = False
        self.assertEqual(back_to(request, '/elsewhere/'), '/db/finance/queue/?page=2')

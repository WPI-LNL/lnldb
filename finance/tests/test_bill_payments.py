"""
Payments for bills: finding the bill a payment settles, and marking it paid.

* **The ISD number.** A payment names the Internal Service Delivery it pays,
  and the bill that ISD's number is recorded on is a lookup: the queue fills
  the event in for a bill, or offers to split across a multi-bill's events,
  before it tries the memo's event name.
* **Marking paid when filing.** The queue, and the split page for a
  multi-bill, offer a ticked *Mark bill paid* box when the payment covers the
  bill; filing with it ticked marks the bill paid on the day the last of the
  money arrived, and unticked leaves it alone.
* **The Mark paid form**, the only other way, for either kind of bill: it asks
  how a bill was paid when no payment filed from Workday covers it. The
  one-click buttons it replaced are gone.
* **Shared figures.** What an unpaid bill has received and owes, and for how
  long, read the same on the Billing page as on the Owed to LNL report.
"""
import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.formats import date_format

from events.tests.generators import OrgFactory, UserFactory
from finance import billing
from finance.billing_forms import BillingUpdateForm, BillPaidForm
from finance.models import ZERO, Billing, MultiBilling, ParsedTransaction, TransactionStatus, WorkdayTransaction
from finance.reports import owed_to_lnl
from finance.suggestions import EXPORT, isd_number_of, suggest_all
from finance.tests.test_billing_page import TODAY, bill, days_ago, multibill, show
from finance.tests.test_revenue_sources import MAIN, CacheResetMixin, event_income
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import fund


def payment(number, amount, date, memo='Lens and Lights services for something else'):
    """ A payment for an ISD, as the export carries it, not yet filed. """
    return WorkdayTransaction.objects.create(
        operational_transaction='Internal Service Delivery: %s' % number,
        accounting_date=date, net_amount=Decimal(amount), memo=memo,
        worktags_json={'student_organization': MAIN,
                       'ledger_account': '70050:Internal Service Provider Revenue'})


def filed(event, amount, date):
    """ A payment already filed against ``event``. """
    return event_income(event, amount, date=date)


def recorded(made, number, amount=None):
    """ ``made`` with its ISD recorded, as the Billing page records it. """
    made.isd_number = number
    made.isd_amount = Decimal(amount) if amount is not None else made.amount
    made.isd_entered_on = days_ago(5)
    made.save()
    return made


# ---------------------------------------------------------------------------
# The ISD number
# ---------------------------------------------------------------------------

class ISDNumberTests(CacheResetMixin, TestCase):
    """ Reading the ISD a payment names, and the bill it is recorded on. """

    def setUp(self):
        super(ISDNumberTests, self).setUp()
        self.gala = show('Spring Gala', start=days_ago(40))
        self.bill = recorded(bill(self.gala, '500.00'), '26090179-ISD')

    def test_the_number_is_read_off_the_operational_transaction(self):
        self.assertEqual(isd_number_of(payment('26090179-ISD', '500.00', TODAY)), '26090179-ISD')
        self.assertEqual(isd_number_of(payment('26090179-isd', '500.00', TODAY)), '26090179-ISD')

    def test_only_an_isd_names_one(self):
        line = WorkdayTransaction.objects.create(
            operational_transaction='Supplier Invoice: 26090179-ISD', accounting_date=TODAY,
            net_amount=Decimal('500.00'), memo='x')
        self.assertEqual(isd_number_of(line), '')
        self.assertEqual(isd_number_of(payment('26090179-ISD-500.00', '500.00', TODAY)), '')

    def test_a_bill_with_the_number_fills_the_event_in(self):
        suggestions = suggest_all(payment('26090179-ISD', '500.00', TODAY))
        linked = suggestions['linked_event']
        self.assertEqual(linked.value, self.gala.pk)
        self.assertEqual(linked.source, EXPORT)
        self.assertEqual(linked.reason, 'ISD number recorded on the bill (26090179-ISD)')
        self.assertEqual(suggestions['isd_bill'], self.bill)
        self.assertIsNone(suggestions['multibill'])
        self.assertFalse(suggestions['needs_event'])

    def test_the_number_wins_over_the_memo(self):
        show('Winter Ball', start=days_ago(40))
        suggestions = suggest_all(payment('26090179-ISD', '500.00', TODAY,
                                          memo='Lens and Lights services for Winter Ball'))
        self.assertEqual(suggestions['linked_event'].value, self.gala.pk)

    def test_the_memo_is_still_read_when_no_bill_has_the_number(self):
        ball = show('Winter Ball', start=days_ago(40))
        suggestions = suggest_all(payment('26099999-ISD', '500.00', TODAY,
                                          memo='Lens and Lights services for Winter Ball'))
        self.assertEqual(suggestions['linked_event'].value, ball.pk)
        self.assertEqual(suggestions['linked_event'].reason[:16], 'Memo names this ')
        self.assertIsNone(suggestions['isd_bill'])

    def test_a_multibill_with_the_number_is_split(self):
        films = [show('Film %s' % n, start=days_ago(40)) for n in (1, 2)]
        bills = recorded(multibill(films), '26090200-ISD')
        suggestions = suggest_all(payment('26090200-ISD', '300.00', TODAY))
        self.assertIsNone(suggestions['linked_event'])
        self.assertEqual(suggestions['multibill']['multibill'], bills)
        self.assertEqual(suggestions['multibill']['reason'], 'ISD number recorded on the multi-bill (26090200-ISD)')
        self.assertFalse(suggestions['needs_event'])


# ---------------------------------------------------------------------------
# Marking the bill paid when the payment is filed
# ---------------------------------------------------------------------------

class QueueMarkPaidTests(CacheResetMixin, FinanceViewTestCase):
    """ The queue's *Mark bill paid* box, and filing a payment with it. """

    def setUp(self):
        super(QueueMarkPaidTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'settle_subledger', 'bill_event', 'view_events')
        self.gala = show('Spring Gala', start=days_ago(40))
        self.bill = recorded(bill(self.gala, '500.00', billed_days_ago=30), '26090179-ISD')

    def queue(self):
        return self.client.get(reverse('finance:queue'), {'fy': 'all'})

    def reconcile(self, line, event=None, **extra):
        data = {'txn%s-linked_event' % line.pk: str((event or self.gala).pk),
                'txn%s-fund_source' % line.pk: str(fund('legacy').pk)}
        data.update(extra)
        return self.client.post(reverse('finance:reconcile', args=[line.pk]), data,
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_a_payment_that_covers_the_bill_offers_it_ticked(self):
        line = payment('26090179-ISD', '500.00', days_ago(2))
        response = self.queue()
        self.assertContains(response, 'name="mark_bill_paid" value="%s" checked' % self.bill.pk)
        self.assertContains(response, 'Mark bill paid on %s' % date_format(days_ago(2), 'M j, Y'))
        self.assertContains(response, 'ISD number recorded on the bill (26090179-ISD)')
        offer = [row['bill_offer'] for row in response.context['rows'] if row['txn'] == line][0]
        self.assertEqual(offer['paid_on'], days_ago(2))

    def test_part_of_the_bill_is_not_offered(self):
        payment('26090179-ISD', '200.00', days_ago(2))
        self.assertNotContains(self.queue(), 'name="mark_bill_paid"')

    def test_the_last_part_is_offered_dated_by_the_last_payment(self):
        filed(self.gala, '200.00', days_ago(9))
        line = payment('26090179-ISD', '300.00', days_ago(2))
        offer = [row['bill_offer'] for row in self.queue().context['rows'] if row['txn'] == line][0]
        self.assertEqual((offer['received'], offer['paid_on']), (Decimal('500.00'), days_ago(2)))

    def test_a_paid_bill_is_not_offered(self):
        self.bill.date_paid = days_ago(1)
        self.bill.save()
        payment('26090179-ISD', '500.00', days_ago(2))
        self.assertNotContains(self.queue(), 'name="mark_bill_paid"')

    def test_filing_with_the_box_ticked_marks_it_paid(self):
        line = payment('26090179-ISD', '500.00', days_ago(2))
        response = self.reconcile(line, mark_bill_paid=str(self.bill.pk), bill_offered=str(self.bill.pk))
        self.assertEqual(response.status_code, 200)
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.date_paid, days_ago(2))
        self.assertIn('Marked the bill for Spring Gala paid on', response.json()['message'])

    def test_filing_with_the_box_unticked_leaves_it_unpaid(self):
        line = payment('26090179-ISD', '500.00', days_ago(2))
        response = self.reconcile(line, bill_offered=str(self.bill.pk))
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)
        self.assertNotIn('bill', response.json()['message'])

    def test_filing_against_another_event_leaves_the_bill_alone(self):
        other = show('Winter Ball', start=days_ago(40))
        line = payment('26090179-ISD', '500.00', days_ago(2))
        response = self.reconcile(line, event=other, mark_bill_paid=str(self.bill.pk),
                                  bill_offered=str(self.bill.pk))
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)
        self.assertIn('filed against another event', response.json()['message'])

    def test_a_payment_that_falls_short_is_not_marked(self):
        line = payment('26090179-ISD', '400.00', days_ago(2))
        response = self.reconcile(line, mark_bill_paid=str(self.bill.pk))
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)
        self.assertIn('$400.00 of its $500.00 has been filed', response.json()['message'])

    def test_an_event_picked_by_hand_says_the_bill_is_covered(self):
        line = payment('26099999-ISD', '500.00', days_ago(2), memo='Payment')
        response = self.reconcile(line)
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)
        self.assertIn('now covers the bill for Spring Gala', response.json()['message'])

    def test_someone_who_cannot_bill_sees_the_match_but_no_box(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='bill_event'))
        self.grant()
        payment('26090179-ISD', '500.00', days_ago(2))
        response = self.queue()
        self.assertContains(response, 'ISD number recorded on the bill (26090179-ISD)')
        self.assertNotContains(response, 'name="mark_bill_paid"')

    def test_someone_who_cannot_bill_cannot_mark_it(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='bill_event'))
        self.grant()
        line = payment('26090179-ISD', '500.00', days_ago(2))
        self.reconcile(line, mark_bill_paid=str(self.bill.pk))
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)


class SplitMarkPaidTests(CacheResetMixin, FinanceViewTestCase):
    """ Splitting a multi-bill's payment, and marking the bill paid with it. """

    def setUp(self):
        super(SplitMarkPaidTests, self).setUp()
        self.grant('view_subledger', 'edit_subledger', 'bill_event')
        self.films = [show('Film %s' % n, start=days_ago(40)) for n in (1, 2)]
        self.bill = recorded(multibill(self.films), '26090200-ISD')
        self.line = payment('26090200-ISD', '300.00', days_ago(3))

    def url(self):
        return reverse('finance:txn-detail', args=[self.line.pk])

    def split(self, **extra):
        data = {'slices-TOTAL_FORMS': '2', 'slices-INITIAL_FORMS': '0',
                'slices-MIN_NUM_FORMS': '0', 'slices-MAX_NUM_FORMS': '1000'}
        for index, film in enumerate(self.films):
            data.update({'slices-%s-amount' % index: '150.00',
                         'slices-%s-description' % index: film.event_name,
                         'slices-%s-linked_event' % index: str(film.pk),
                         'slices-%s-fund_source' % index: str(fund('legacy').pk)})
        data.update(extra)
        return self.client.post(self.url(), data, follow=True)

    def test_laying_out_the_split_offers_the_box_ticked(self):
        response = self.client.get(self.url(), {'multibill': self.bill.pk})
        self.assertContains(response, 'name="mark_bill_paid" value="%s" checked' % self.bill.pk)
        self.assertContains(response, 'Mark Fall films paid on')

    def test_saving_with_the_box_ticked_marks_it_paid(self):
        response = self.split(mark_bill_paid=str(self.bill.pk), bill_offered=str(self.bill.pk))
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.date_paid, days_ago(3))
        self.assertContains(response, 'Marked Fall films paid on')

    def test_a_show_with_no_share_gets_no_row(self):
        """ A slice cannot be $0, so a $0 show's row could only be refused. """
        from finance.views.detail import _multibill_rows
        free = show('Free Film', start=days_ago(40))
        self.bill.events.add(free)
        shares = {self.films[0].pk: Decimal('300.00'), self.films[1].pk: ZERO, free.pk: ZERO}
        with mock.patch('finance.calculators.multibill_shares', return_value=shares):
            rows = _multibill_rows(self.line, MultiBilling.objects.get(pk=self.bill.pk))
        self.assertEqual([(row['linked_event'], row['amount']) for row in rows],
                         [(self.films[0].pk, Decimal('300.00'))])

    def test_saving_without_it_leaves_the_bill_unpaid(self):
        self.split(bill_offered=str(self.bill.pk))
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)


# ---------------------------------------------------------------------------
# The Mark paid form
# ---------------------------------------------------------------------------

class MarkPaidFormTests(CacheResetMixin, FinanceViewTestCase):
    """ Marking either kind of bill paid by hand, and unpaid again. """

    def setUp(self):
        super(MarkPaidFormTests, self).setUp()
        self.grant('view_subledger', 'bill_event', 'view_events', 'view_event_billing')
        self.gala = show('Spring Gala', start=days_ago(40))
        self.bill = bill(self.gala, '500.00', billed_days_ago=30)

    def url(self, name='bill-paid'):
        return reverse('finance:%s' % name, args=[self.gala.pk, self.bill.pk])

    def test_with_nothing_filed_it_starts_today_and_asks_how(self):
        response = self.client.get(self.url())
        self.assertEqual(response.context['form'].initial['date_paid'], timezone.localdate())
        self.assertContains(response, 'say how it was paid')
        response = self.client.post(self.url(), {'date_paid': days_ago(4).isoformat()})
        self.assertContains(response, 'Say how it was paid. No payment filed from Workday covers it.')
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)

    def test_a_check_is_recorded_with_its_day(self):
        response = self.client.post(self.url(), {'date_paid': days_ago(4).isoformat(),
                                                 'paid_note': 'Check from the department'})
        self.assertRedirects(response, reverse('events:detail', args=[self.gala.pk]) + '#billing',
                             fetch_redirect_response=False)
        self.bill.refresh_from_db()
        self.assertEqual((self.bill.date_paid, self.bill.paid_note), (days_ago(4), 'Check from the department'))

    def test_with_the_payment_filed_it_starts_on_the_day_it_arrived(self):
        filed(self.gala, '300.00', days_ago(9))
        filed(self.gala, '200.00', days_ago(6))
        response = self.client.get(self.url())
        self.assertEqual(response.context['form'].initial['date_paid'], days_ago(6))
        self.assertContains(response, 'That covers it')
        self.client.post(self.url(), {'date_paid': days_ago(6).isoformat()})
        self.bill.refresh_from_db()
        self.assertEqual((self.bill.date_paid, self.bill.paid_note), (days_ago(6), ''))

    def test_a_day_after_today_is_refused(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        response = self.client.post(self.url(), {'date_paid': tomorrow.isoformat(), 'paid_note': 'Cash'})
        self.assertContains(response, 'A bill cannot have been paid after today.')

    def test_a_paid_bill_is_not_marked_again(self):
        self.bill.date_paid = days_ago(2)
        self.bill.save()
        response = self.client.get(self.url(), follow=True)
        self.assertContains(response, 'The bill for Spring Gala was already marked paid on')

    def test_a_closed_event_locks_it(self):
        self.gala.closed = True
        self.gala.save()
        response = self.client.post(self.url(), {'date_paid': days_ago(4).isoformat(), 'paid_note': 'Cash'},
                                    follow=True)
        self.assertContains(response, 'is closed')
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.date_paid)

    def test_the_clients_own_members_cannot_mark_it(self):
        """
        The events app grants Bill event on an event to its client's members.
        The one-click Mark Paid accepted that; the form needs the Officers'.
        """
        member = UserFactory.create(is_superuser=False, onboarded=True)
        org = OrgFactory.create(name='Drama Council')
        org.associated_users.add(member)
        self.gala.billing_org = org
        self.gala.save()
        self.assertTrue(member.has_perm('events.bill_event', self.gala))
        self.client.force_login(member)
        response = self.client.post(self.url(), {'date_paid': days_ago(4).isoformat(), 'paid_note': 'Cash'})
        self.assertEqual(response.status_code, 403)

    def test_marking_unpaid_opens_it_again(self):
        self.bill.date_paid = days_ago(2)
        self.bill.paid_note = 'Cash'
        self.bill.save()
        response = self.client.post(self.url('bill-unpaid'))
        self.assertEqual(response.status_code, 302)
        self.bill.refresh_from_db()
        self.assertEqual((self.bill.date_paid, self.bill.paid_note), (None, ''))
        self.assertEqual(self.client.get(self.url('bill-unpaid')).status_code, 405)

    def test_a_multibill_uses_the_same_form(self):
        films = [show('Film %s' % n, start=days_ago(40)) for n in (1, 2)]
        bills = multibill(films)
        url = reverse('finance:multibill-paid', args=[bills.pk])
        self.assertContains(self.client.get(url), 'filed against\n                        these events')
        response = self.client.post(url, {'date_paid': days_ago(1).isoformat()})
        self.assertContains(response, 'Say how it was paid')
        filed(films[0], '150.00', days_ago(3))
        filed(films[1], '150.00', days_ago(2))
        self.client.post(url, {'date_paid': days_ago(2).isoformat()})
        bills.refresh_from_db()
        self.assertEqual(bills.date_paid, days_ago(2))

    def test_the_one_click_buttons_are_gone(self):
        for name, args in (('bill-pay', [self.gala.pk, self.bill.pk]), ('event-mark-paid', [self.gala.pk])):
            with self.assertRaises(NoReverseMatch):
                reverse('finance:%s' % name, args=args)

    def test_editing_a_bill_no_longer_sets_its_paid_date(self):
        self.assertNotIn('date_paid', BillingUpdateForm(self.gala, instance=self.bill).fields)

    def test_the_event_lists_and_page_open_the_form(self):
        response = self.client.get(reverse('events:detail', args=[self.gala.pk]))
        self.assertContains(response, 'href="%s"' % self.url())
        self.assertContains(response, 'Mark Paid…')

    def test_covered_means_the_note_may_be_left_blank(self):
        self.assertFalse(BillPaidForm(covered=True).fields['paid_note'].required)
        self.assertTrue(BillPaidForm(covered=False).fields['paid_note'].required)


class PnLMarkPaidTests(CacheResetMixin, FinanceViewTestCase):
    """ The Events P&L flags a bill paid in full and not marked, and opens the form. """

    def setUp(self):
        super(PnLMarkPaidTests, self).setUp()
        self.grant('view_subledger', 'bill_event')
        self.gala = show('Spring Gala', start=datetime.date(2026, 4, 25))
        self.bill = Billing.objects.create(event=self.gala, date_billed=datetime.date(2026, 4, 30),
                                           amount=Decimal('500.00'))

    def test_the_flag_opens_the_mark_paid_form(self):
        filed(self.gala, '500.00', datetime.date(2026, 5, 20))
        response = self.client.get(reverse('finance:events'), {'fy': 2026})
        self.assertContains(response, 'Paid in full, bill not marked paid')
        self.assertContains(response, reverse('finance:bill-paid', args=[self.gala.pk, self.bill.pk]))

    def test_a_multibill_flag_opens_its_own_form(self):
        org = OrgFactory(name='Orientation', shortname='NSO')
        concert = show('NSO Concert', start=datetime.date(2026, 4, 20))
        bills = MultiBilling.objects.create(org=org, date_billed=datetime.date(2026, 4, 30),
                                            amount=Decimal('900.00'))
        bills.events.set([concert])
        filed(concert, '900.00', datetime.date(2026, 5, 2))
        response = self.client.get(reverse('finance:events'), {'fy': 2026})
        self.assertContains(response, reverse('finance:multibill-paid', args=[bills.pk]))

    def test_only_someone_who_can_bill_is_offered_it(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='bill_event'))
        self.grant()
        filed(self.gala, '500.00', datetime.date(2026, 5, 20))
        response = self.client.get(reverse('finance:events'), {'fy': 2026})
        self.assertContains(response, 'Paid in full, bill not marked paid')
        self.assertNotContains(response, 'Mark paid…')


# ---------------------------------------------------------------------------
# The figures the Billing page shares with the Owed to LNL report
# ---------------------------------------------------------------------------

class SharedFiguresTests(CacheResetMixin, FinanceViewTestCase):
    """ Received, owed and days owed, the same on the Billing page and the report. """

    def setUp(self):
        super(SharedFiguresTests, self).setUp()
        self.grant('view_subledger', 'bill_event', 'view_events', 'view_event_billing')
        # The books start at least a year before these shows, whatever today is.
        payment('26000001-ISD', '1.00', days_ago(400))
        self.gala = show('Spring Gala', start=days_ago(40))
        self.bill = recorded(bill(self.gala, '500.00', billed_days_ago=30, emailed_days_ago=29), '26090179-ISD')

    def page(self):
        return self.client.get(reverse('finance:billing'), {'stage': billing.WAITING_ON_APPROVAL, 'fy': 'all'})

    def test_the_page_and_the_report_count_the_same_days(self):
        filed(self.gala, '200.00', days_ago(3))
        row = self.page().context['rows'][0]
        self.assertEqual((row.received, row.owed, row.days_owed), (Decimal('200.00'), Decimal('300.00'), 30))
        report = owed_to_lnl(today=timezone.localdate())
        client_rows = report.sections[1].rows
        self.assertEqual([(r.cells['owed'], r.cells['days']) for r in client_rows], [(Decimal('300.00'), 30)])

    def test_the_page_shows_what_is_owed(self):
        filed(self.gala, '200.00', days_ago(3))
        response = self.page()
        self.assertContains(response, '$300.00')
        self.assertContains(response, '$200.00 received')
        self.assertContains(response, '30 days')

    def test_a_bill_received_in_full_says_so_and_offers_mark_paid(self):
        filed(self.gala, '500.00', days_ago(3))
        response = self.page()
        self.assertContains(response, 'Received in full')
        self.assertContains(response, 'href="%s?next=' % reverse('finance:bill-paid', args=[self.gala.pk, self.bill.pk]))
        self.assertTrue(response.context['rows'][0].covered)

    def test_the_next_step_box_says_the_bill_is_covered(self):
        filed(self.gala, '500.00', days_ago(3))
        response = self.client.get(reverse('events:detail', args=[self.gala.pk]))
        self.assertContains(response, 'The payments filed against it cover the bill, the last on')

    def test_a_bill_from_before_the_books_has_no_figures(self):
        old = show('Old Show', start=days_ago(800))
        recorded(bill(old, '50.00', billed_days_ago=790), '26090180-ISD')
        rows = {row.event.event_name: row for row in self.page().context['rows']}
        self.assertIsNone(rows['Old Show'].owed)
        self.assertEqual(rows['Spring Gala'].owed, Decimal('500.00'))

    def test_a_paid_bill_lists_how_it_was_paid(self):
        self.bill.date_paid = days_ago(1)
        self.bill.paid_note = 'Check from the department'
        self.bill.save()
        response = self.client.get(reverse('finance:billing'), {'stage': billing.PAID, 'fy': 'all'})
        self.assertContains(response, 'Check from the department')

    def test_payment_offer_and_marking(self):
        self.assertIsNone(billing.payment_offer(self.bill, Decimal('499.99'), days_ago(1)))
        offer = billing.payment_offer(self.bill, Decimal('500.00'), days_ago(1))
        self.assertEqual((offer['paid_on'], offer['owed']), (days_ago(1), Decimal('500.00')))
        self.assertIsNone(billing.mark_paid_from_payments(self.bill))
        filed(self.gala, '500.00', days_ago(1))
        self.assertEqual(billing.mark_paid_from_payments(self.bill), days_ago(1))
        self.assertIsNone(billing.payment_offer(self.bill, Decimal('500.00'), days_ago(1)))
        self.assertIsNone(billing.mark_paid_from_payments(self.bill))
        self.assertEqual(ParsedTransaction.objects.filter(status=TransactionStatus.SETTLED).count(), 1)

"""
The end of billing: closing events from the Billing page, and the weekly digest.

* **Closing.** The Paid and No bill needed tabs close events one row at a time
  or ticked together, exactly as the event page's Close button does, by the
  same permission. A multi-bill's row closes each of its open events. An
  event money is still owed on -- marked paid, with less filed from Workday
  than was billed -- is refused; a bill from before the books start has
  nothing filed to count, and is not.
* **The digest.** What the ``billing_digest`` command emails the Treasurer:
  bills the client has not answered and ISDs not yet approved, past the days
  set in Finance Configuration, and events ready to close.
"""
import datetime
from decimal import Decimal
from io import StringIO

from django.conf import settings
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from reversion.models import Version

from events.models import BaseEvent
from events.tests.generators import OrgFactory
from finance import billing
from finance.models import FinanceSettings, NoBillNeeded
from finance.tests.test_bill_payments import filed, payment, recorded
from finance.tests.test_billing_page import bill, days_ago, multibill, show
from finance.tests.test_revenue_sources import CacheResetMixin
from finance.tests.test_views import FinanceViewTestCase


def waiting_on_approval(event, days, amount='500.00'):
    """ A bill for ``event`` whose ISD was recorded ``days`` days ago. """
    made = recorded(bill(event, amount, billed_days_ago=days + 10, emailed_days_ago=days + 9),
                    '2609%04d-ISD' % event.pk)
    made.isd_entered_on = days_ago(days)
    made.save()
    return made


def no_bill(event, user=None):
    return NoBillNeeded.objects.create(event=event, reason=NoBillNeeded.OTHER, note='Rehearsal only',
                                       decided_by=user)


# ---------------------------------------------------------------------------
# Closing from the Billing page
# ---------------------------------------------------------------------------

class CloseTests(CacheResetMixin, FinanceViewTestCase):
    """ The Paid and No bill needed tabs close events, and refuse while money is owed. """

    def setUp(self):
        super(CloseTests, self).setUp()
        self.grant('bill_event', 'close_event', 'view_events', 'view_event_billing')
        # The books start at least a year before these shows, whatever today is.
        payment('26000001-ISD', '1.00', days_ago(400))
        self.url = reverse('finance:billing-close')
        self.paid_tab = reverse('finance:billing') + '?stage=paid&fy=all'

    def close(self, *keys, **data):
        data.setdefault('close', list(keys))
        data.setdefault('next', self.paid_tab)
        return self.client.post(self.url, data, follow=True)

    def paid(self, name, amount='500.00', received=None, start=40):
        """ A show billed and marked paid, with ``received`` filed against it. """
        event = show(name, start=days_ago(start))
        bill(event, amount, billed_days_ago=30, emailed_days_ago=29, paid_days_ago=2)
        if received:
            filed(event, received, days_ago(3))
        return event

    def test_one_row_is_closed_as_the_event_page_closes_it(self):
        gala = self.paid('Spring Gala', received='500.00')
        response = self.client.post(self.url, {'only': 'e%s' % gala.pk, 'next': self.paid_tab})
        self.assertRedirects(response, self.paid_tab, fetch_redirect_response=False)
        gala = BaseEvent.objects.get(pk=gala.pk)
        self.assertTrue(gala.closed)
        self.assertEqual(gala.closed_by, self.user)
        self.assertIsNotNone(gala.closed_on)
        latest = Version.objects.get_for_object(gala).first()
        self.assertEqual((latest.revision.comment, latest.revision.user), ('Closed', self.user))

    def test_only_the_pressed_row_is_closed_whatever_else_is_ticked(self):
        gala = self.paid('Spring Gala', received='500.00')
        ball = self.paid('Winter Ball', received='500.00')
        self.close('e%s' % gala.pk, 'e%s' % ball.pk, only='e%s' % ball.pk)
        self.assertFalse(BaseEvent.objects.get(pk=gala.pk).closed)
        self.assertTrue(BaseEvent.objects.get(pk=ball.pk).closed)

    def test_ticked_rows_on_either_tab_are_closed_together(self):
        gala = self.paid('Spring Gala', received='500.00')
        rehearsal = show('Rehearsal')
        no_bill(rehearsal, self.user)
        response = self.close('e%s' % gala.pk, 'e%s' % rehearsal.pk)
        self.assertContains(response, 'Closed 2 events: Spring Gala, Rehearsal.')
        self.assertEqual(BaseEvent.objects.filter(closed=True).count(), 2)
        self.assertEqual(billing.billing_items(), [])

    def test_a_multibill_row_closes_each_of_its_open_events(self):
        films = [show('Film %s' % n, start=days_ago(40)) for n in (1, 2, 3)]
        bulk = multibill(films, paid_days_ago=2)
        filed(films[0], '300.00', days_ago(3))
        BaseEvent.objects.filter(pk=films[2].pk).update(closed=True)
        response = self.close('m%s' % bulk.pk)
        self.assertContains(response, 'Closed 2 events: Film 1, Film 2.')
        self.assertTrue(all(BaseEvent.objects.get(pk=film.pk).closed for film in films))

    def test_money_still_owed_is_refused(self):
        gala = self.paid('Spring Gala')
        response = self.close('e%s' % gala.pk)
        self.assertContains(response, 'Not closed, because money is still owed. Spring Gala: none of the $500.00 '
                                      'billed has been received. Settle the payment in the queue')
        self.assertFalse(BaseEvent.objects.get(pk=gala.pk).closed)

    def test_part_filed_is_refused_with_what_is_missing(self):
        gala = self.paid('Spring Gala', received='200.00')
        response = self.close('e%s' % gala.pk)
        self.assertContains(response, 'Spring Gala: $300.00 of the $500.00 billed has not been received')
        self.assertFalse(BaseEvent.objects.get(pk=gala.pk).closed)

    def test_overpaid_is_closed(self):
        gala = self.paid('Spring Gala', received='520.00')
        self.close('e%s' % gala.pk)
        self.assertTrue(BaseEvent.objects.get(pk=gala.pk).closed)

    def test_a_bill_from_before_the_books_is_taken_as_paid(self):
        old = self.paid('Old Show', start=800)
        self.close('e%s' % old.pk)
        self.assertTrue(BaseEvent.objects.get(pk=old.pk).closed)

    def test_the_rest_are_closed_when_one_is_refused(self):
        gala = self.paid('Spring Gala')
        ball = self.paid('Winter Ball', received='500.00')
        response = self.close('e%s' % gala.pk, 'e%s' % ball.pk)
        self.assertContains(response, 'Closed 1 event: Winter Ball.')
        self.assertContains(response, 'Not closed, because money is still owed. Spring Gala')
        self.assertEqual(list(BaseEvent.objects.filter(closed=True)), [BaseEvent.objects.get(pk=ball.pk)])

    def test_a_row_at_any_other_stage_is_left_alone(self):
        waiting = show('Waiting')
        bill(waiting, emailed_days_ago=5)
        response = self.close('e%s' % waiting.pk, 'e999999', 'nonsense')
        self.assertContains(response, '3 rows were no longer paid or needing no bill, or already closed, so they '
                                      'were left alone.')
        self.assertFalse(BaseEvent.objects.get(pk=waiting.pk).closed)

    def test_closing_twice_closes_once(self):
        gala = self.paid('Spring Gala', received='500.00')
        self.close('e%s' % gala.pk)
        response = self.close('e%s' % gala.pk)
        self.assertContains(response, '1 row was no longer paid or needing no bill, or already closed, so it was '
                                      'left alone.')

    def test_nothing_ticked(self):
        response = self.close()
        self.assertContains(response, 'Tick the events to close first.')

    def test_only_by_post(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_needs_the_close_permission(self):
        gala = self.paid('Spring Gala', received='500.00')
        self.user.user_permissions.remove(*self.user.user_permissions.filter(codename='close_event'))
        self.grant()
        response = self.client.post(self.url, {'only': 'e%s' % gala.pk})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BaseEvent.objects.get(pk=gala.pk).closed)
        page = self.client.get(self.paid_tab)
        self.assertNotContains(page, 'fin-close-form')
        self.assertNotContains(page, 'Close the ticked events')

    def test_and_the_bill_permission(self):
        gala = self.paid('Spring Gala', received='500.00')
        self.user.user_permissions.remove(*self.user.user_permissions.filter(codename='bill_event'))
        self.grant()
        self.assertEqual(self.client.post(self.url, {'only': 'e%s' % gala.pk}).status_code, 403)

    def test_the_paid_tab_offers_close_except_where_money_is_owed(self):
        gala = self.paid('Spring Gala', received='500.00')
        ball = self.paid('Winter Ball', received='200.00')
        response = self.client.get(self.paid_tab)
        self.assertContains(response, 'name="close" value="e%s"' % gala.pk)
        self.assertContains(response, 'name="only" value="e%s"' % gala.pk)
        self.assertNotContains(response, 'value="e%s"' % ball.pk)
        self.assertContains(response, '$300.00 not received')
        self.assertContains(response, 'Close the ticked events')
        # Paid, so not offered Mark paid again, though what was filed covers it.
        self.assertNotContains(response, 'Mark paid…')

    def test_the_no_bill_needed_tab_offers_close(self):
        rehearsal = show('Rehearsal')
        no_bill(rehearsal, self.user)
        response = self.client.get(reverse('finance:billing') + '?stage=no-bill-needed&fy=all')
        self.assertContains(response, 'name="only" value="e%s"' % rehearsal.pk)
        self.assertContains(response, 'Close the ticked events')
        self.assertContains(response, reverse('finance:no-bill-needed-undo', args=[rehearsal.pk]))


# ---------------------------------------------------------------------------
# The weekly digest
# ---------------------------------------------------------------------------

class DigestTests(CacheResetMixin, TestCase):
    """ What the digest lists, by the limits in Finance Configuration. """

    def setUp(self):
        super(DigestTests, self).setUp()
        payment('26000001-ISD', '1.00', days_ago(400))

    def names(self, key):
        return [item.name for item in billing.digest()[key]]

    def test_bills_waiting_on_the_client_from_fourteen_days(self):
        bill(show('Fourteen'), emailed_days_ago=14)
        bill(show('Thirteen'), emailed_days_ago=13)
        bill(show('Thirty'), emailed_days_ago=30)
        self.assertEqual(self.names('waiting_on_client'), ['Thirty', 'Fourteen'])

    def test_counted_from_the_last_email(self):
        made = bill(show('Emailed again'), emailed_days_ago=30)
        made.billingemail_set.create(subject='Again', message='Again',
                                     sent_at=timezone.now() - datetime.timedelta(days=2))
        self.assertEqual(self.names('waiting_on_client'), [])

    def test_isds_waiting_on_approval_from_twenty_one_days(self):
        waiting_on_approval(show('Twenty-one', start=days_ago(60)), 21)
        waiting_on_approval(show('Twenty', start=days_ago(60)), 20)
        self.assertEqual(self.names('waiting_on_approval'), ['Twenty-one'])

    def test_the_limits_are_settings(self):
        config = FinanceSettings.load()
        config.digest_client_days, config.digest_approval_days = 5, 10
        config.save()
        bill(show('Six'), emailed_days_ago=6)
        waiting_on_approval(show('Eleven', start=days_ago(60)), 11)
        found = billing.digest()
        self.assertEqual((found['client_days'], found['approval_days']), (5, 10))
        self.assertEqual(self.names('waiting_on_client'), ['Six'])
        self.assertEqual(self.names('waiting_on_approval'), ['Eleven'])

    def test_events_ready_to_close(self):
        gala = show('Spring Gala', start=days_ago(40))
        bill(gala, billed_days_ago=30, emailed_days_ago=29, paid_days_ago=5)
        no_bill(show('Rehearsal'))
        bill(show('Unpaid'), emailed_days_ago=3)
        found = billing.digest()
        self.assertEqual([item.name for item in found['to_close']], ['Spring Gala', 'Rehearsal'])
        self.assertEqual(found['to_close'][0].close_refusal, 'none of the $100.00 billed has been received')
        self.assertIsNone(found['to_close'][1].close_refusal)

    def test_test_events_are_left_out(self):
        bill(show('Practice', test_event=True), emailed_days_ago=30)
        no_bill(show('Practice too', test_event=True))
        found = billing.digest()
        self.assertEqual((found['waiting_on_client'], found['to_close']), ([], []))

    def test_what_has_been_received_is_attached(self):
        gala = show('Spring Gala', start=days_ago(40))
        waiting_on_approval(gala, 30)
        filed(gala, '200.00', days_ago(2))
        row = billing.digest()['waiting_on_approval'][0]
        self.assertEqual((row.received, row.owed), (Decimal('200.00'), Decimal('300.00')))


class DigestCommandTests(CacheResetMixin, TestCase):
    """ The billing_digest command: who it goes to, what it says, and when it says nothing. """

    def setUp(self):
        super(DigestCommandTests, self).setUp()
        payment('26000001-ISD', '1.00', days_ago(400))
        masque = OrgFactory.create(name='Masque')
        self.waiting = show('Masque Fall Production', masque)
        bill(self.waiting, '382.50', emailed_days_ago=15)
        no_bill(show('Rehearsal'))

    def run_command(self, *args):
        out = StringIO()
        call_command('billing_digest', *args, stdout=out)
        return out.getvalue()

    def test_it_goes_to_the_treasurer(self):
        said = self.run_command()
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [settings.EMAIL_TARGET_T])
        self.assertEqual(email.subject, 'Billing digest: 1 waiting on the client, 1 to close')
        self.assertIn('Sent the billing digest to %s' % settings.EMAIL_TARGET_T, said)

    def test_what_it_says(self):
        self.run_command()
        text = mail.outbox[0].body
        self.assertIn('WAITING ON THE CLIENT, 14 DAYS OR MORE', text)
        self.assertIn('- Masque Fall Production (Masque): $382.50, last sent', text)
        self.assertIn('15 days ago.', text)
        self.assertIn('/db/finance/billing/?stage=waiting-on-client&fy=all', text)
        self.assertIn(reverse('events:detail', args=[self.waiting.pk]), text)
        self.assertIn('- Rehearsal: no bill needed (Other).', text)
        self.assertNotIn('WAITING ON APPROVAL', text)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn('Waiting on the client, 14 days or more', html)
        self.assertIn('Masque Fall Production</a>', html)
        self.assertIn('stage=no-bill-needed&amp;fy=all', html)

    def test_it_can_go_somewhere_else(self):
        self.run_command('--to', 'a@wpi.edu', '--to', 'b@wpi.edu')
        self.assertEqual(mail.outbox[0].to, ['a@wpi.edu', 'b@wpi.edu'])

    def test_a_dry_run_prints_it_and_sends_nothing(self):
        said = self.run_command('--dry-run')
        self.assertEqual(mail.outbox, [])
        self.assertIn('Subject: Billing digest: 1 waiting on the client, 1 to close', said)
        self.assertIn('Masque Fall Production', said)

    def test_nothing_to_say_sends_nothing(self):
        BaseEvent.objects.update(closed=True)
        said = self.run_command()
        self.assertEqual(mail.outbox, [])
        self.assertIn('no digest was sent', said)

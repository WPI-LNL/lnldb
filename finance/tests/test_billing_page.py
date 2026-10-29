"""
The Billing page, and the stages it lists bills by (:mod:`finance.billing`).

What stage each bill is at and since when, read off the bill, its emails, its
recorded worktag and ISD, the event's worktag and its history; the
fiscal-year and partition filters; the page's tabs and what each offers;
recording a worktag and an ISD; deciding an event needs no bill; starting a
multi-bill from ticked events; the event page's *Next step* box; and the
site menu, where the events app's billing lists gave way to the page.
"""
import datetime
from decimal import Decimal

import reversion
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from reversion.models import Revision

from data.tests.util import ViewTestCase
from events.models import BaseEvent, Category, ServiceInstance
from events.tests.generators import Event2019Factory, OrgFactory, ServiceFactory, UserFactory
from events.models import EventArbitrary
from finance import billing
from finance.billing_forms import billable_events
from finance.calculators import event_financials
from finance.models import Billing, BillingEmail, MultiBilling, MultiBillingEmail, NoBillNeeded

TODAY = timezone.localdate()


def days_ago(days):
    return TODAY - datetime.timedelta(days=days)


def evening(day):
    """ 7pm on ``day``, local time, so it is that day wherever it is read. """
    return timezone.make_aware(datetime.datetime(day.year, day.month, day.day, 19, 0))


def show(name, client=None, reviewed_days_ago=3, start=None, **extra):
    """ An event reviewed for billing ``reviewed_days_ago`` days ago, booked by ``client``. """
    event = Event2019Factory.create(event_name=name, reviewed=True,
                                    reviewed_on=evening(days_ago(reviewed_days_ago)), **extra)
    if start is not None:
        event.datetime_start = evening(start)
        event.datetime_end = evening(start) + datetime.timedelta(hours=3)
        event.save()
    if client is not None:
        event.org.add(client)
    return event


def bill(event, amount='100.00', billed_days_ago=10, emailed_days_ago=None, paid_days_ago=None):
    """ A bill for ``event``, emailed and paid that many days ago when given. """
    made = Billing.objects.create(event=event, amount=Decimal(amount), date_billed=days_ago(billed_days_ago),
                                  date_paid=days_ago(paid_days_ago) if paid_days_ago is not None else None)
    if emailed_days_ago is not None:
        BillingEmail.objects.create(billing=made, subject='Bill', message='Bill',
                                    sent_at=evening(days_ago(emailed_days_ago)))
    return made


def multibill(events, org=None, emailed_days_ago=None, paid_days_ago=None, name='Fall films'):
    made = MultiBilling.objects.create(name=name, org=org, amount=Decimal('300.00'), date_billed=days_ago(20),
                                       date_paid=days_ago(paid_days_ago) if paid_days_ago is not None else None)
    made.events.set(events)
    if emailed_days_ago is not None:
        MultiBillingEmail.objects.create(multibilling=made, subject='Bill', message='Bill',
                                         sent_at=evening(days_ago(emailed_days_ago)))
    return made


def item(event):
    """ The item an event is part of, read fresh from the database. """
    return billing.item_for_event(BaseEvent.objects.get(pk=event.pk))


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))


# ---------------------------------------------------------------------------
# Which stage a bill is at
# ---------------------------------------------------------------------------

class StageTests(TestCase):

    def test_reviewed_with_no_bill_is_ready_to_bill_since_the_review(self):
        gala = show('Gala', reviewed_days_ago=4)
        found = item(gala)
        self.assertEqual((found.stage, found.not_sent, found.bill), (billing.READY, False, None))
        self.assertEqual((found.since, found.days), (days_ago(4), 4))

    def test_no_stage_before_the_review_or_after_closing(self):
        unreviewed = Event2019Factory.create(event_name='Unreviewed')
        closed = show('Closed', closed=True)
        self.assertIsNone(item(unreviewed))
        self.assertIsNone(item(closed))
        self.assertEqual(billing.billing_items(), [])

    def test_a_bill_never_emailed_is_still_ready_to_bill_marked_not_sent(self):
        gala = show('Gala')
        bill(gala, billed_days_ago=6)
        found = item(gala)
        self.assertEqual((found.stage, found.not_sent, found.since), (billing.READY, True, days_ago(6)))

    def test_an_emailed_bill_waits_on_the_client_from_the_last_email(self):
        gala = show('Gala')
        made = bill(gala, emailed_days_ago=9)
        BillingEmail.objects.create(billing=made, subject='Again', message='Again', sent_at=evening(days_ago(2)))
        found = item(gala)
        self.assertEqual((found.stage, found.since, found.last_sent, found.sent_by_hand),
                         (billing.WAITING_ON_CLIENT, days_ago(2), days_ago(2), False))

    def test_a_bill_marked_sent_waits_on_the_client_from_that_day(self):
        gala = show('Gala')
        made = bill(gala, billed_days_ago=8)
        made.sent_on = days_ago(5)
        made.save()
        found = item(gala)
        self.assertEqual((found.stage, found.not_sent, found.since, found.sent_by_hand),
                         (billing.WAITING_ON_CLIENT, False, days_ago(5), True))
        # Emailed after it was handed over: the email is the last time it went out.
        BillingEmail.objects.create(billing=made, subject='Bill', message='Bill', sent_at=evening(days_ago(1)))
        found = item(gala)
        self.assertEqual((found.since, found.sent_by_hand), (days_ago(1), False))

    def test_a_multibill_marked_sent_waits_on_the_client(self):
        bulk = multibill([show('Film')])
        bulk.sent_on = days_ago(3)
        bulk.save()
        found = billing.multibill_item(bulk)
        self.assertEqual((found.stage, found.since, found.sent_by_hand), (billing.WAITING_ON_CLIENT, days_ago(3), True))

    def test_a_worktag_from_the_client_means_create_the_isd(self):
        gala = show('Gala', worktag='1234-CC', workday_fund=110)
        bill(gala, emailed_days_ago=5)
        found = item(gala)
        self.assertEqual(found.stage, billing.CREATE_ISD)
        self.assertEqual((found.worktag, found.fund, found.memo),
                         ('1234-CC', '110-FD', 'Lens and Lights services for Gala'))

    def test_a_fund_without_a_worktag_is_not_a_reply(self):
        # The fund can be on the event before the client answers; only the form sets the worktag.
        gala = show('Gala', workday_fund=110)
        bill(gala, emailed_days_ago=5)
        self.assertEqual(item(gala).stage, billing.WAITING_ON_CLIENT)

    def test_a_recorded_isd_waits_on_approval_from_the_day_it_was_created(self):
        gala = show('Gala', worktag='1234-CC')
        made = bill(gala, emailed_days_ago=5)
        made.isd_number, made.isd_amount, made.isd_entered_on = '25090179-ISD', made.amount, days_ago(2)
        made.save()
        self.assertEqual((item(gala).stage, item(gala).since), (billing.WAITING_ON_APPROVAL, days_ago(2)))

    def test_marked_entered_into_workday_before_isd_numbers_still_waits_on_approval(self):
        gala = show('Gala', worktag='1234-CC', entered_into_workday=True)
        bill(gala, emailed_days_ago=5)
        self.assertEqual(item(gala).stage, billing.WAITING_ON_APPROVAL)

    def test_a_worktag_recorded_on_the_bill_means_create_the_isd(self):
        gala = show('Gala')
        made = bill(gala, emailed_days_ago=5)
        made.worktag_charged, made.fund_charged, made.worktag_entered_on = '1234-CC', 110, days_ago(1)
        made.save()
        found = item(gala)
        self.assertEqual((found.stage, found.since, found.worktag, found.fund),
                         (billing.CREATE_ISD, days_ago(1), '1234-CC', '110-FD'))
        self.assertFalse(found.worktag_disagrees)
        gala.worktag = '9999-GR'
        gala.save()
        found = item(gala)
        self.assertEqual(found.worktag, '1234-CC')  # the one recorded on the bill
        self.assertTrue(found.worktag_disagrees)

    def test_no_bill_needed_from_the_day_it_was_decided(self):
        gala = show('Gala')
        NoBillNeeded.objects.create(event=gala, reason=NoBillNeeded.LNL_EVENT, decided_on=evening(days_ago(3)))
        found = item(gala)
        self.assertEqual((found.stage, found.since, found.no_bill.reason),
                         (billing.NO_BILL_NEEDED, days_ago(3), NoBillNeeded.LNL_EVENT))

    def test_no_bill_needed_is_suggested_for_an_sga_funded_show_at_zero(self):
        show_ = show('SGA show', is_sga_funded=True)
        self.assertTrue(item(show_).suggest_no_bill)
        self.assertFalse(item(show('Paid show')).suggest_no_bill)
        EventArbitrary.objects.create(event=show_, key_name='Popcorn', key_value=Decimal('50.00'), key_quantity=1)
        self.assertFalse(item(show_).suggest_no_bill)  # a one-off is charged even to an SGA-funded show

    def test_a_paid_bill_is_paid_until_the_event_is_closed(self):
        gala = show('Gala', worktag='1234-CC', entered_into_workday=True)
        bill(gala, emailed_days_ago=30, paid_days_ago=3)
        found = item(gala)
        self.assertEqual((found.stage, found.since), (billing.PAID, days_ago(3)))
        gala.closed = True
        gala.save()
        self.assertEqual(billing.billing_items(), [])

    def test_the_latest_bill_stands(self):
        gala = show('Gala')
        bill(gala, billed_days_ago=60, emailed_days_ago=60, paid_days_ago=40)
        bill(gala, '50.00', billed_days_ago=5, emailed_days_ago=5)
        found = item(gala)
        self.assertEqual((found.stage, found.amount), (billing.WAITING_ON_CLIENT, Decimal('50.00')))

    def test_a_multibill_is_one_item_for_all_its_events(self):
        soccomm = OrgFactory.create(name='SocComm')
        films = [show('Film %s' % n, soccomm) for n in (1, 2, 3)]
        bulk = multibill(films, soccomm)
        items = billing.billing_items()
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0].stage, items[0].not_sent, items[0].name, items[0].client),
                         (billing.READY, True, 'Fall films', soccomm))
        self.assertEqual([e.event_name for e in items[0].events], ['Film 1', 'Film 2', 'Film 3'])

        MultiBillingEmail.objects.create(multibilling=bulk, subject='Bill', message='Bill',
                                         sent_at=evening(days_ago(4)))
        self.assertEqual((item(films[0]).stage, item(films[0]).since), (billing.WAITING_ON_CLIENT, days_ago(4)))

        bulk.worktag_charged, bulk.fund_charged, bulk.worktag_entered_on = '1234-CC', 810, days_ago(3)
        bulk.save()
        self.assertEqual((item(films[0]).stage, item(films[0]).since), (billing.CREATE_ISD, days_ago(3)))
        bulk.isd_number, bulk.isd_amount, bulk.isd_entered_on = '25090179-ISD', bulk.amount, days_ago(2)
        bulk.save()
        self.assertEqual((item(films[0]).stage, item(films[0]).since), (billing.WAITING_ON_APPROVAL, days_ago(2)))

        bulk.date_paid = days_ago(1)
        bulk.save()
        self.assertEqual(item(films[1]).stage, billing.PAID)

        # Still listed while any of its events is open
        BaseEvent.objects.filter(pk__in=[films[0].pk, films[1].pk]).update(closed=True)
        self.assertEqual(len(billing.billing_items()), 1)
        BaseEvent.objects.filter(pk=films[2].pk).update(closed=True)
        self.assertEqual(billing.billing_items(), [])

    def test_hidden_and_test_events_are_left_out_for_whoever_cannot_see_them(self):
        show('Secret', sensitive=True)
        show('Rehearsal', test_event=True)
        viewer = UserFactory.create(username='viewer', is_superuser=False)
        self.assertEqual(billing.billing_items(viewer), [])
        grant(viewer, 'view_hidden_event', 'view_test_event')
        viewer = type(viewer).objects.get(pk=viewer.pk)
        self.assertEqual(sorted(found.name for found in billing.billing_items(viewer)), ['Rehearsal', 'Secret'])

    def test_a_multibills_requester_is_its_clients_person_in_charge(self):
        soccomm = OrgFactory.create(name='SocComm')
        bulk = multibill([show('Film 1', soccomm, contact=UserFactory.create(username='booker'))], soccomm)
        self.assertEqual(billing.multibill_item(bulk).requester, soccomm.user_in_charge)

    def test_price_now_and_whether_the_bill_still_matches(self):
        gala = show('Gala', worktag='1234-CC')
        bill(gala, '250.00', emailed_days_ago=5)
        found = item(gala)
        self.assertEqual((found.amount, found.price_now, found.price_differs),
                         (Decimal('250.00'), Decimal('0.00'), True))


class StageDateTests(TestCase):
    """ The day a single bill reached Create ISD or Waiting on approval comes from the event's history. """

    def setUp(self):
        self.gala = show('Gala', workday_fund=110)
        bill(self.gala, emailed_days_ago=10)

    def save_with_comment(self, comment, days, **changes):
        with reversion.create_revision():
            reversion.set_comment(comment)
            for name, value in changes.items():
                setattr(self.gala, name, value)
            self.gala.save()
        Revision.objects.filter(comment=comment).update(date_created=evening(days_ago(days)))

    def test_the_day_the_client_sent_the_worktag(self):
        self.save_with_comment(billing.WORKTAG_SENT_COMMENT, 4, worktag='1234-CC')
        self.assertEqual((item(self.gala).stage, item(self.gala).since), (billing.CREATE_ISD, days_ago(4)))

    def test_the_day_it_was_marked_entered_into_workday(self):
        self.save_with_comment(billing.WORKTAG_SENT_COMMENT, 4, worktag='1234-CC')
        self.save_with_comment(billing.WORKDAY_ENTERED_COMMENT, 1, entered_into_workday=True)
        self.assertEqual((item(self.gala).stage, item(self.gala).since), (billing.WAITING_ON_APPROVAL, days_ago(1)))

    def test_with_no_history_it_counts_from_the_last_email(self):
        self.gala.worktag = '1234-CC'
        self.gala.save()
        self.assertEqual(item(self.gala).since, days_ago(10))
        self.gala.entered_into_workday = True
        self.gala.save()
        self.assertEqual(item(self.gala).since, days_ago(10))


# ---------------------------------------------------------------------------
# The filters
# ---------------------------------------------------------------------------

class FilterTests(TestCase):

    def test_the_fiscal_year_is_the_one_the_event_started_in(self):
        show('Fall show', start=datetime.date(2026, 9, 10))
        show('Spring show', start=datetime.date(2026, 3, 10))
        items = billing.billing_items()
        self.assertEqual([found.name for found in billing.filter_items(items, fiscal_year=2027)], ['Fall show'])
        self.assertEqual([found.name for found in billing.filter_items(items, fiscal_year=2026)], ['Spring show'])
        self.assertEqual(len(billing.filter_items(items)), 2)

    def test_projection_is_film_showings(self):
        projection = Category.objects.create(name='Projection')
        lighting = Category.objects.create(name='Lighting')
        film = show('Film')
        concert = show('Concert with a screen')
        plain = show('Talk')
        ServiceInstance.objects.create(service=ServiceFactory.create(category=projection), event=film)
        ServiceInstance.objects.create(service=ServiceFactory.create(category=projection), event=concert)
        ServiceInstance.objects.create(service=ServiceFactory.create(category=lighting), event=concert)
        items = billing.billing_items()
        self.assertEqual([found.name for found in billing.filter_items(items, is_projection=True)], ['Film'])
        self.assertEqual(sorted(found.name for found in billing.filter_items(items, is_projection=False)),
                         ['Concert with a screen', 'Talk'])
        self.assertEqual(billing.projection_event_ids([plain.pk]), set())

    def test_a_multibill_is_projections_when_every_event_on_it_is(self):
        projection = Category.objects.create(name='Projection')
        films = [show('Film %s' % n) for n in (1, 2)]
        for film in films:
            ServiceInstance.objects.create(service=ServiceFactory.create(category=projection), event=film)
        multibill(films)
        self.assertEqual(len(billing.filter_items(billing.billing_items(), is_projection=True)), 1)
        films.append(show('Talk'))
        MultiBilling.objects.get().events.add(films[-1])
        self.assertEqual(billing.filter_items(billing.billing_items(), is_projection=True), [])


class ReadySectionTests(TestCase):

    def test_split_into_not_sent_on_its_own_and_in_bulk_by_client(self):
        soccomm = OrgFactory.create(name='SocComm')
        admissions = OrgFactory.create(name='Admissions')
        bill(show('Billed, never sent'))
        show('Gala', admissions)
        show('Film 2', soccomm, billed_in_bulk=True, reviewed_days_ago=2)
        show('Film 1', soccomm, billed_in_bulk=True, reviewed_days_ago=5)
        show('Tour', admissions, billed_in_bulk=True)
        ready = billing.by_stage(billing.billing_items())[billing.READY]
        sections = billing.ready_sections(ready)
        self.assertEqual([found.name for found in sections['not_sent']], ['Billed, never sent'])
        self.assertEqual([found.name for found in sections['alone']], ['Gala'])
        self.assertEqual([(group['client'].name, [found.name for found in group['items']])
                          for group in sections['bulk']],
                         [('Admissions', ['Tour']), ('SocComm', ['Film 1', 'Film 2'])])
        self.assertEqual(sections['bulk'][1]['total'], Decimal('0.00'))


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

class BillingPageTests(ViewTestCase):

    def setUp(self):
        super(BillingPageTests, self).setUp()
        grant(self.user, 'bill_event')
        self.url = reverse('finance:billing')

    def test_needs_the_bill_event_permission(self):
        self.user.user_permissions.clear()
        self.assertOk(self.client.get(self.url), 403)

    def test_tabs_count_each_stage_and_ready_to_bill_comes_first(self):
        show('Gala')
        bill(show('Ball'), emailed_days_ago=3)
        bill(show('Fair', worktag='1234-CC'), emailed_days_ago=3)
        resp = self.client.get(self.url + '?fy=all')
        self.assertOk(resp)
        self.assertEqual(resp.context['stage'], billing.READY)
        self.assertEqual([(tab['label'], tab['count']) for tab in resp.context['tabs']],
                         [('Ready to bill', 1), ('No bill needed', 0), ('Waiting on client', 1), ('Create ISD', 1),
                          ('Waiting on approval', 0), ('Paid', 0)])
        self.assertContains(resp, 'Gala')
        self.assertNotContains(resp, 'Ball')
        self.assertEqual(self.client.get(self.url + '?stage=nonsense').context['stage'], billing.READY)

    def test_ready_to_bill_offers_a_bill_or_a_multibill(self):
        soccomm = OrgFactory.create(name='SocComm')
        gala = show('Gala')
        films = [show('Film %s' % n, soccomm, billed_in_bulk=True, reviewed_days_ago=n) for n in (2, 1)]
        resp = self.client.get(self.url + '?stage=ready&fy=all')
        self.assertContains(resp, reverse('finance:bill-new', args=[gala.pk]))
        self.assertContains(resp, 'name="events" value="%s"' % gala.pk)
        self.assertContains(resp, '%s?events=%s&amp;events=%s' % (reverse('finance:multibill-new'),
                                                                  films[0].pk, films[1].pk))
        self.assertContains(resp, 'Make a multi-bill of the ticked events')

    def test_a_bill_need_not_be_emailed_to_be_paid(self):
        gala = show('Gala')
        made = bill(gala)
        tab = self.url + '?stage=ready&fy=all'
        resp = self.client.get(tab)
        paid = reverse('finance:bill-paid', args=[gala.pk, made.pk])
        self.assertContains(resp, paid)
        self.assertContains(resp, reverse('finance:bill-worktag', args=[gala.pk, made.pk]))
        self.assertRedirects(self.client.post(paid, {'next': tab, 'date_paid': TODAY.isoformat(),
                                                     'paid_note': 'Check handed over'}), tab)
        self.assertEqual(item(gala).stage, billing.PAID)

    def test_mark_a_bill_sent_without_emailing_it(self):
        gala = show('Gala')
        made = bill(gala, billed_days_ago=8)
        tab = self.url + '?stage=ready&fy=all'
        sent = reverse('finance:bill-sent', args=[gala.pk, made.pk])
        self.assertContains(self.client.get(tab), sent)
        self.assertOk(self.client.get(sent))
        self.assertRedirects(self.client.post(sent, {'next': tab, 'sent_on': days_ago(2).isoformat(),
                                                     'sent_note': 'Handed over at the meeting'}), tab)
        made.refresh_from_db()
        self.assertEqual((made.sent_on, made.sent_note), (days_ago(2), 'Handed over at the meeting'))
        resp = self.client.get(self.url + '?stage=waiting-on-client&fy=all')
        self.assertContains(resp, 'Not by email: Handed over at the meeting.')
        self.assertContains(resp, sent)

    def test_mark_sent_refuses_a_day_before_the_bill_or_after_today(self):
        gala = show('Gala')
        made = bill(gala, billed_days_ago=8)
        sent = reverse('finance:bill-sent', args=[gala.pk, made.pk])
        for day, error in ((days_ago(9), 'cannot have been sent before then'),
                           (TODAY + datetime.timedelta(days=1), 'cannot have been sent after today')):
            self.assertContains(self.client.post(sent, {'sent_on': day.isoformat()}), error)
        made.refresh_from_db()
        self.assertIsNone(made.sent_on)

    def test_mark_not_sent_puts_it_back(self):
        gala = show('Gala')
        made = bill(gala)
        made.sent_on, made.sent_note = TODAY, 'By hand'
        made.save()
        self.client.post(reverse('finance:bill-sent', args=[gala.pk, made.pk]), {'unsend': '1'})
        made.refresh_from_db()
        self.assertEqual((made.sent_on, made.sent_note), (None, ''))
        self.assertTrue(item(gala).not_sent)

    def test_a_paid_bill_is_past_being_sent(self):
        gala = show('Gala')
        made = bill(gala, paid_days_ago=1)
        self.client.post(reverse('finance:bill-sent', args=[gala.pk, made.pk]), {'sent_on': TODAY.isoformat()})
        made.refresh_from_db()
        self.assertIsNone(made.sent_on)

    def test_mark_a_multibill_sent(self):
        bulk = multibill([show('Film'), show('Other film')])
        sent = reverse('finance:multibill-sent', args=[bulk.pk])
        self.assertContains(self.client.get(self.url + '?stage=ready&fy=all'), sent)
        self.assertContains(self.client.get(reverse('finance:multibill-detail', args=[bulk.pk])), sent)
        self.client.post(sent, {'sent_on': TODAY.isoformat()})
        bulk.refresh_from_db()
        self.assertEqual(bulk.sent_on, TODAY)
        self.assertContains(self.client.get(reverse('finance:multibill-detail', args=[bulk.pk])),
                            'not by email')
        self.assertContains(self.client.get(reverse('finance:multibill-list')), 'not by email')

    def test_every_unpaid_stage_offers_mark_paid(self):
        waiting = bill(show('Ball'), emailed_days_ago=3)
        isd = bill(show('Fair', worktag='1234-CC'), emailed_days_ago=3)
        for stage, made in (('waiting-on-client', waiting), ('create-isd', isd)):
            resp = self.client.get(self.url + '?stage=%s&fy=all' % stage)
            self.assertContains(resp, reverse('finance:bill-paid', args=[made.event_id, made.pk]))

    def test_other_years_are_counted_not_hidden(self):
        show('Fall show', start=datetime.date(2026, 9, 10))
        show('Spring show', start=datetime.date(2026, 3, 10))
        resp = self.client.get(self.url + '?fy=2027')
        self.assertContains(resp, 'Fall show')
        self.assertNotContains(resp, 'Spring show')
        self.assertContains(resp, '1 more from other years.')

    def test_create_isd_shows_what_to_type_into_workday(self):
        ada = UserFactory.create(username='ada', first_name='Ada', last_name='Lovelace', email='ada@wpi.edu')
        gala = show('Gala', OrgFactory.create(name='Admissions'), worktag='1234-CC', workday_fund=110,
                    contact=ada, workday_form_comments='Spring budget, please')
        bill(gala, '250.00', emailed_days_ago=5)
        resp = self.client.get(self.url + '?stage=create-isd&fy=all')
        made = Billing.objects.get(event=gala)
        for text in ('$250.00', 'data-copy="250.00"', '1234-CC', '110-FD', 'Ada Lovelace', 'ada@wpi.edu',
                     'Lens and Lights services for Gala', 'Spring budget, please', 'Now $0.00',
                     reverse('events:bills:pdf', args=[gala.pk]), reverse('finance:bill-isd', args=[gala.pk, made.pk]),
                     'name="isd_number"', 'name="worktag" value="1234-CC"', 'name="fund" value="110"',
                     'name="amount" value="250.00"'):
            self.assertContains(resp, text)

    def test_recording_the_isd_from_its_row_moves_it_on(self):
        gala = show('Gala', worktag='1234-CC', workday_fund=110)
        made = bill(gala, '250.00', emailed_days_ago=5)
        tab = self.url + '?stage=create-isd'
        resp = self.client.post(reverse('finance:bill-isd', args=[gala.pk, made.pk]),
                                {'next': tab, 'worktag': '1234-CC', 'fund': '110', 'amount': '250.00',
                                 'entered_on': TODAY.isoformat(), 'isd_number': '25090179-isd'})
        self.assertRedirects(resp, tab)
        made.refresh_from_db()
        self.assertEqual((made.isd_number, made.isd_amount, made.isd_entered_on, made.isd_entered_by),
                         ('25090179-ISD', Decimal('250.00'), TODAY, self.user))
        found = item(gala)
        self.assertEqual((found.stage, found.since), (billing.WAITING_ON_APPROVAL, TODAY))
        self.assertTrue(found.event.entered_into_workday)

    def test_waiting_on_approval_offers_mark_paid(self):
        gala = show('Gala', worktag='1234-CC', entered_into_workday=True)
        made = bill(gala, emailed_days_ago=5)
        resp = self.client.get(self.url + '?stage=waiting-on-approval&fy=all')
        self.assertContains(resp, reverse('finance:bill-paid', args=[gala.pk, made.pk]))
        self.assertContains(resp, 'Mark paid…')
        self.assertContains(resp, 'not recorded')
        self.assertContains(resp, reverse('finance:bill-isd', args=[gala.pk, made.pk]))

    def test_no_bill_needed_tab(self):
        gala = show('Gala')
        NoBillNeeded.objects.create(event=gala, reason=NoBillNeeded.OTHER, note='Rehearsal only',
                                    decided_by=self.user)
        resp = self.client.get(self.url + '?stage=no-bill-needed&fy=all')
        self.assertContains(resp, 'Gala')
        self.assertContains(resp, 'Rehearsal only')
        self.assertContains(resp, reverse('finance:no-bill-needed-undo', args=[gala.pk]))

    def test_a_multibill_waiting_on_the_client(self):
        soccomm = OrgFactory.create(name='SocComm')
        bulk = multibill([show('Film 1', soccomm), show('Film 2', soccomm)], soccomm, emailed_days_ago=3)
        resp = self.client.get(self.url + '?stage=waiting-on-client&fy=all')
        self.assertContains(resp, 'Fall films')
        self.assertContains(resp, 'Film 1, Film 2')
        self.assertContains(resp, reverse('finance:multibill-email', args=[bulk.pk]))
        self.assertContains(resp, reverse('finance:multibill-worktag', args=[bulk.pk]))

    def test_paid_offers_close_only_to_whoever_may_close(self):
        # Closing from the tab is tested in test_billing_closing.
        gala = show('Gala')
        bill(gala, emailed_days_ago=30, paid_days_ago=2)
        resp = self.client.get(self.url + '?stage=paid&fy=all')
        self.assertContains(resp, reverse('events:detail', args=[gala.pk]))
        self.assertNotContains(resp, 'Close the ticked events')
        grant(self.user, 'close_event')
        self.user = type(self.user).objects.get(pk=self.user.pk)
        self.client.force_login(self.user)
        resp = self.client.get(self.url + '?stage=paid&fy=all')
        self.assertContains(resp, 'id="fin-close-form"')
        self.assertContains(resp, 'Close the ticked events')


class MultiBillFromTickedEventsTests(ViewTestCase):
    """ The Ready to bill tab's ticked events open the new multi-bill form already ticked. """

    def setUp(self):
        super(MultiBillFromTickedEventsTests, self).setUp()
        grant(self.user, 'bill_event')
        self.soccomm = OrgFactory.create(name='SocComm')

    def test_ticked_events_come_ticked(self):
        films = [show('Film %s' % n, self.soccomm, billed_in_bulk=True) for n in (1, 2)]
        show('Film 3', self.soccomm, billed_in_bulk=True)
        resp = self.client.get('%s?events=%s&events=%s' % (reverse('finance:multibill-new'), films[0].pk, films[1].pk))
        self.assertOk(resp)
        self.assertEqual(resp.context['form'].initial['events'], [str(films[0].pk), str(films[1].pk)])
        self.assertFalse(resp.context['include_unmarked'])

    def test_an_event_not_marked_for_bulk_widens_the_list_and_still_saves(self):
        gala = show('Gala', self.soccomm)
        film = show('Film', self.soccomm, billed_in_bulk=True)
        url = '%s?events=%s&events=%s' % (reverse('finance:multibill-new'), gala.pk, film.pk)
        resp = self.client.get(url)
        self.assertTrue(resp.context['include_unmarked'])
        self.assertIn(gala, resp.context['form'].fields['events'].queryset)
        resp = self.client.post(url, {'events': [gala.pk, film.pk], 'name': 'Two shows',
                                      'date_billed': TODAY.isoformat()})
        made = MultiBilling.objects.get()
        self.assertRedirects(resp, reverse('finance:multibill-detail', args=[made.pk]))
        self.assertEqual(set(made.events.all()), {gala, film})

    def test_ticked_events_for_different_clients_ask_first(self):
        films = [show('Film 1', self.soccomm, billed_in_bulk=True),
                 show('Film 2', OrgFactory.create(name='LNL'), billed_in_bulk=True)]
        resp = self.client.get('%s?events=%s&events=%s' % (reverse('finance:multibill-new'), films[0].pk, films[1].pk))
        self.assertContains(resp, 'Bill these together')
        self.assertFalse(resp.context['form'].fields['confirm_mixed_clients'].initial)


# ---------------------------------------------------------------------------
# Recording the worktag and the ISD
# ---------------------------------------------------------------------------

class WorktagAndISDTests(ViewTestCase):

    def setUp(self):
        super(WorktagAndISDTests, self).setUp()
        grant(self.user, 'bill_event')
        self.client_org = OrgFactory.create(name='Admissions', worktag='5555-DE', workday_fund=110)
        self.gala = show('Gala', self.client_org)
        self.bill = bill(self.gala, '250.00', emailed_days_ago=4)
        self.worktag_url = reverse('finance:bill-worktag', args=[self.gala.pk, self.bill.pk])
        self.isd_url = reverse('finance:bill-isd', args=[self.gala.pk, self.bill.pk])

    def isd(self, number, url=None, **extra):
        data = {'worktag': '1234-CC', 'fund': '110', 'amount': '250.00', 'entered_on': TODAY.isoformat(),
                'isd_number': number}
        data.update(extra)
        return self.client.post(url or self.isd_url, data)

    def test_needs_the_bill_event_permission(self):
        self.user.user_permissions.clear()
        self.assertOk(self.client.get(self.worktag_url), 403)
        self.assertOk(self.client.get(self.isd_url), 403)

    def test_enter_the_worktag_a_client_sent_by_email(self):
        resp = self.client.get(self.worktag_url)
        self.assertEqual((resp.context['form'].initial['worktag'], resp.context['form'].initial['fund']),
                         ('5555-DE', 110))
        self.assertContains(resp, 'Filled in: on file for Admissions from their last bill. Confirm it with them.')
        resp = self.client.post(self.worktag_url, {'worktag': ' 1234-cc ', 'fund': '810'})
        self.assertRedirects(resp, reverse('finance:billing') + '?stage=create-isd')
        self.bill.refresh_from_db()
        self.assertEqual((self.bill.worktag_charged, self.bill.fund_charged, self.bill.worktag_entered_on),
                         ('1234-CC', 810, TODAY))
        self.assertEqual(item(self.gala).stage, billing.CREATE_ISD)

    def test_a_worktag_must_look_like_one(self):
        resp = self.client.post(self.worktag_url, {'worktag': 'spring budget', 'fund': '110'})
        self.assertFormError(resp.context['form'], 'worktag',
                             "That is not a worktag. Worktags look like 1234-CC or 123-AG.")

    def test_the_isd_form_starts_with_what_the_client_sent(self):
        self.gala.worktag, self.gala.workday_fund = '7777-GF', 220
        self.gala.save()
        resp = self.client.get(self.isd_url)
        form = resp.context['form']
        self.assertEqual((form.initial['worktag'], form.initial['fund'], form.initial['amount'],
                          form.initial['entered_on']), ('7777-GF', 220, Decimal('250.00'), TODAY))
        self.assertContains(resp, "Filled in: sent by the client through the bill's form.")
        self.assertContains(resp, 'Lens and Lights services for Gala')

    def test_recording_the_isd_locks_the_clients_form(self):
        self.isd('25090179-ISD')
        self.bill.refresh_from_db()
        self.assertEqual((self.bill.isd_number, self.bill.worktag_charged), ('25090179-ISD', '1234-CC'))
        self.assertTrue(BaseEvent.objects.get(pk=self.gala.pk).entered_into_workday)

    def test_isd_numbers_are_workdays_and_unique(self):
        for typed, stored in (('25090179', '25090179-ISD'), (' 25090180-isd', '25090180-ISD')):
            self.isd(typed)
            self.bill.refresh_from_db()
            self.assertEqual(self.bill.isd_number, stored)
        resp = self.isd('ISD-25090179')
        self.assertFormError(resp.context['form'], 'isd_number',
                             "Workday's ISD numbers are digits, then -ISD, such as 25090179-ISD.")
        resp = self.isd('25090181-ISD', entered_on=(TODAY + datetime.timedelta(days=1)).isoformat())
        self.assertFormError(resp.context['form'], 'entered_on', "The ISD cannot have been created after today.")
        soccomm = OrgFactory.create(name='SocComm')
        bulk = multibill([show('Film', soccomm)], soccomm, emailed_days_ago=1)
        resp = self.isd('25090180-ISD', url=reverse('finance:multibill-isd', args=[bulk.pk]))
        self.assertFormError(resp.context['form'], 'isd_number',
                             '25090180-ISD is already recorded on the bill for Gala.')

    def test_a_multibill_has_its_worktag_entered_and_its_isd_recorded(self):
        soccomm = OrgFactory.create(name='SocComm', worktag='4242-CC', workday_fund=810)
        films = [show('Film %s' % n, soccomm) for n in (1, 2)]
        bulk = multibill(films, soccomm, emailed_days_ago=2)
        resp = self.client.get(reverse('finance:multibill-worktag', args=[bulk.pk]))
        self.assertEqual(resp.context['form'].initial['worktag'], '4242-CC')
        self.client.post(reverse('finance:multibill-worktag', args=[bulk.pk]), {'worktag': '4242-CC', 'fund': '810'})
        self.assertEqual(item(films[0]).stage, billing.CREATE_ISD)
        self.isd('25090200-ISD', url=reverse('finance:multibill-isd', args=[bulk.pk]), worktag='4242-CC',
                 fund='810', amount='300.00')
        self.assertEqual(item(films[0]).stage, billing.WAITING_ON_APPROVAL)
        self.assertTrue(all(BaseEvent.objects.get(pk=film.pk).entered_into_workday for film in films))

    def test_remove_a_mistaken_isd(self):
        self.isd('25090179-ISD')
        resp = self.client.post(self.isd_url, {'remove-isd': '1'})
        self.assertRedirects(resp, reverse('finance:billing') + '?stage=create-isd')
        self.bill.refresh_from_db()
        self.assertEqual((self.bill.isd_number, self.bill.isd_entered_by, self.bill.worktag_charged),
                         (None, None, '1234-CC'))
        self.assertFalse(BaseEvent.objects.get(pk=self.gala.pk).entered_into_workday)
        self.assertEqual(item(self.gala).stage, billing.CREATE_ISD)

    def test_not_once_paid_or_closed(self):
        self.bill.date_paid = TODAY
        self.bill.save()
        self.assertRedirects(self.client.get(self.isd_url), reverse('events:detail', args=[self.gala.pk]) + '#billing',
                             fetch_redirect_response=False)
        self.bill.date_paid = None
        self.bill.save()
        BaseEvent.objects.filter(pk=self.gala.pk).update(closed=True)
        self.isd('25090179-ISD')
        self.bill.refresh_from_db()
        self.assertIsNone(self.bill.isd_number)

    def test_changing_a_multibill_after_its_isd_warns(self):
        soccomm = OrgFactory.create(name='SocComm')
        bulk = multibill([show('Film', soccomm)], soccomm, emailed_days_ago=2)
        bulk.recalculate()
        self.isd('25090300-ISD', url=reverse('finance:multibill-isd', args=[bulk.pk]), amount=str(bulk.amount))
        self.assertContains(self.client.get(reverse('finance:multibill-edit', args=[bulk.pk])),
                            'ISD 25090300-ISD was created for $0.00.')
        resp = self.client.post(reverse('finance:multibill-charge-new', args=[bulk.pk]),
                                {'kind': 'oneoff', 'description': 'Popcorn', 'quantity': '1', 'unit_price': '40.00'},
                                follow=True)
        self.assertContains(resp, 'ISD 25090300-ISD charges $0.00, but the bill now comes to $40.00.')
        bulk.refresh_from_db()
        self.assertTrue(bulk.isd_differs)


# ---------------------------------------------------------------------------
# No bill needed
# ---------------------------------------------------------------------------

class NoBillNeededTests(ViewTestCase):

    def setUp(self):
        super(NoBillNeededTests, self).setUp()
        grant(self.user, 'bill_event', 'view_events')
        self.gala = show('Gala')
        self.url = reverse('finance:no-bill-needed', args=[self.gala.pk])

    def test_decide_it_then_undo_it(self):
        resp = self.client.get(self.url)
        self.assertFalse(resp.context['form'].initial.get('reason'))
        resp = self.client.post(self.url, {'reason': NoBillNeeded.NOT_APPLICABLE, 'note': ''})
        self.assertRedirects(resp, reverse('finance:billing') + '?stage=ready')
        decided = NoBillNeeded.objects.get(event=self.gala)
        self.assertEqual((decided.reason, decided.decided_by), (NoBillNeeded.NOT_APPLICABLE, self.user))
        self.assertEqual(item(self.gala).stage, billing.NO_BILL_NEEDED)
        self.client.post(reverse('finance:no-bill-needed-undo', args=[self.gala.pk]))
        self.assertFalse(NoBillNeeded.objects.exists())
        self.assertEqual(item(self.gala).stage, billing.READY)

    def test_suggested_for_an_sga_funded_show_at_zero(self):
        sga = show('SGA show', is_sga_funded=True)
        resp = self.client.get(reverse('finance:no-bill-needed', args=[sga.pk]))
        self.assertEqual(resp.context['form'].initial['reason'], NoBillNeeded.SGA_FUNDED)
        self.assertContains(resp, 'Filled in: the event is marked SGA-funded')
        self.assertFalse(NoBillNeeded.objects.exists())  # only ever saved by the Treasurer

    def test_other_needs_a_note(self):
        resp = self.client.post(self.url, {'reason': NoBillNeeded.OTHER, 'note': ' '})
        self.assertFormError(resp.context['form'], 'note', "Say why, when the reason is Other.")

    def test_only_for_an_event_with_no_bill(self):
        bill(self.gala)
        self.client.post(self.url, {'reason': NoBillNeeded.LNL_EVENT})
        self.assertFalse(NoBillNeeded.objects.exists())

    def test_it_cannot_be_billed_until_undone(self):
        NoBillNeeded.objects.create(event=self.gala, reason=NoBillNeeded.LNL_EVENT)
        resp = self.client.get(reverse('finance:bill-new', args=[self.gala.pk]))
        self.assertRedirects(resp, reverse('events:detail', args=[self.gala.pk]) + '#billing',
                             fetch_redirect_response=False)
        self.gala.billed_in_bulk = True
        self.gala.save()
        self.assertNotIn(self.gala, billable_events(include_unmarked=True))

    def test_the_events_figures_say_so(self):
        self.assertEqual(event_financials(self.gala)['payment_state_label'], 'Not billed')
        NoBillNeeded.objects.create(event=self.gala, reason=NoBillNeeded.LNL_EVENT)
        self.assertEqual(event_financials(self.gala)['payment_state_label'], 'No bill needed')


# ---------------------------------------------------------------------------
# The event page's Next step box, and the menu
# ---------------------------------------------------------------------------

class NextStepBoxTests(ViewTestCase):

    def setUp(self):
        super(NextStepBoxTests, self).setUp()
        grant(self.user, 'view_events', 'view_event_billing', 'bill_event')

    def page(self, event):
        return self.client.get(reverse('events:detail', args=[event.pk]))

    def test_shows_the_stage_and_what_to_do_next(self):
        gala = show('Gala')
        resp = self.page(gala)
        self.assertContains(resp, 'id="billing-next-step"')
        self.assertContains(resp, 'Next step: Ready to bill.')
        made = bill(gala, emailed_days_ago=3)
        resp = self.page(gala)
        self.assertContains(resp, 'Next step: Waiting on client.')
        self.assertContains(resp, reverse('finance:bill-email', args=[gala.pk, made.pk]))

    def test_a_bill_not_sent_can_skip_the_email(self):
        gala = show('Gala')
        made = bill(gala)
        resp = self.page(gala)
        self.assertContains(resp, reverse('finance:bill-email', args=[gala.pk, made.pk]))
        self.assertContains(resp, reverse('finance:bill-sent', args=[gala.pk, made.pk]))
        self.assertContains(resp, reverse('finance:bill-worktag', args=[gala.pk, made.pk]))
        self.assertContains(resp, reverse('finance:bill-paid', args=[gala.pk, made.pk]))

    def test_a_bill_marked_sent_says_so(self):
        gala = show('Gala')
        made = bill(gala)
        made.sent_on, made.sent_note = TODAY, 'Handed over'
        made.save()
        resp = self.page(gala)
        self.assertContains(resp, 'Next step: Waiting on client.')
        self.assertContains(resp, '(Handed over), not by email.')

    def test_waiting_on_the_client_offers_mark_paid(self):
        gala = show('Gala')
        made = bill(gala, emailed_days_ago=3)
        self.assertContains(self.page(gala), reverse('finance:bill-paid', args=[gala.pk, made.pk]))

    def test_marked_to_bill_in_bulk_starts_a_multibill(self):
        film = show('Film', billed_in_bulk=True)
        self.assertContains(self.page(film), '%s?events=%s' % (reverse('finance:multibill-new'), film.pk))

    def test_create_isd_records_the_isd_and_comes_back(self):
        gala = show('Gala', worktag='1234-CC', workday_fund=110)
        made = bill(gala, '250.00', emailed_days_ago=3)
        resp = self.page(gala)
        self.assertContains(resp, 'The client sent the worktag 1234-CC (110-FD).')
        isd = reverse('finance:bill-isd', args=[gala.pk, made.pk])
        self.assertContains(resp, isd)
        here = reverse('events:detail', args=[gala.pk])
        self.assertRedirects(self.client.post(isd, {'next': here + '#billing', 'worktag': '1234-CC', 'fund': '110',
                                                    'amount': '250.00', 'entered_on': TODAY.isoformat(),
                                                    'isd_number': '25090179'}),
                             here + '#billing')
        resp = self.page(gala)
        self.assertContains(resp, 'Next step: Waiting on approval.')
        self.assertContains(resp, 'ISD 25090179-ISD is in Workday')

    def test_offers_no_bill_needed_and_its_undo(self):
        gala = show('Gala', is_sga_funded=True)
        resp = self.page(gala)
        self.assertContains(resp, 'It is marked SGA-funded and comes to $0, so it may need no bill.')
        self.assertContains(resp, reverse('finance:no-bill-needed', args=[gala.pk]))
        NoBillNeeded.objects.create(event=gala, reason=NoBillNeeded.SGA_FUNDED)
        resp = self.page(gala)
        self.assertContains(resp, 'Not being billed: SGA-funded.')
        self.assertContains(resp, reverse('finance:no-bill-needed-undo', args=[gala.pk]))

    def test_a_multibilled_event_points_to_its_bill(self):
        film = show('Film')
        bulk = multibill([film, show('Other film')], emailed_days_ago=2)
        resp = self.page(film)
        self.assertContains(resp, 'Billed on the multi-bill')
        self.assertContains(resp, reverse('finance:multibill-detail', args=[bulk.pk]))

    def test_not_shown_before_the_review(self):
        self.assertNotContains(self.page(Event2019Factory.create(event_name='Gala')), 'billing-next-step')

    def test_not_shown_without_the_permission_site_wide(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='bill_event'))
        self.assertNotContains(self.page(show('Gala')), 'billing-next-step')


class MenuTests(ViewTestCase):

    def test_billing_is_in_the_finance_menu_and_the_old_lists_are_gone(self):
        grant(self.user, 'bill_event', 'view_event_billing', 'view_subledger')
        resp = self.client.get(reverse('finance:billing'))
        self.assertContains(resp, 'href="%s"' % reverse('finance:billing'))
        self.assertContains(resp, 'Events Pending Review')
        for gone in ('Events to be Billed', 'Events Billed, Pending Payment', 'Events Awaiting Workday Entry',
                     'Events Entered Into Workday', 'Events Paid', '>MultiBills<'):
            self.assertNotContains(resp, gone)

    def test_the_billing_entries_are_only_for_whoever_can_bill(self):
        grant(self.user, 'view_subledger')
        resp = self.client.get(reverse('finance:dashboard'))
        self.assertNotContains(resp, 'href="%s"' % reverse('finance:billing'))

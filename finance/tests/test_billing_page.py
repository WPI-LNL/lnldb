"""
The Billing page, and the stages it lists bills by (:mod:`finance.billing`).

What stage each bill is at and since when, read off the bill, its emails, the
event's worktag and its history; the fiscal-year and partition filters; the
page's tabs and what each offers; starting a multi-bill from ticked events;
the event page's *Next step* box; and the site menu, where the events app's
billing lists gave way to the page.
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
from finance import billing
from finance.models import Billing, BillingEmail, MultiBilling, MultiBillingEmail

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
        self.assertEqual((found.stage, found.since, found.last_emailed),
                         (billing.WAITING_ON_CLIENT, days_ago(2), days_ago(2)))

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

    def test_entered_into_workday_waits_on_approval(self):
        gala = show('Gala', worktag='1234-CC', entered_into_workday=True)
        bill(gala, emailed_days_ago=5)
        self.assertEqual(item(gala).stage, billing.WAITING_ON_APPROVAL)

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
                         [('Ready to bill', 1), ('Waiting on client', 1), ('Create ISD', 1),
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
        for text in ('$250.00', 'data-copy="250.00"', '1234-CC', '110-FD', 'Ada Lovelace', 'ada@wpi.edu',
                     'Lens and Lights services for Gala', 'Spring budget, please', 'Event now $0.00',
                     reverse('events:bills:pdf', args=[gala.pk]), reverse('finance:workday-entered', args=[gala.pk])):
            self.assertContains(resp, text)

    def test_marking_it_entered_into_workday_moves_it_on_from_today(self):
        gala = show('Gala', worktag='1234-CC')
        bill(gala, emailed_days_ago=5)
        tab = self.url + '?stage=create-isd'
        self.assertRedirects(self.client.post(reverse('finance:workday-entered', args=[gala.pk]), {'next': tab}),
                             tab)
        found = item(gala)
        self.assertEqual((found.stage, found.since), (billing.WAITING_ON_APPROVAL, TODAY))

    def test_waiting_on_approval_offers_mark_paid(self):
        gala = show('Gala', worktag='1234-CC', entered_into_workday=True)
        made = bill(gala, emailed_days_ago=5)
        resp = self.client.get(self.url + '?stage=waiting-on-approval&fy=all')
        self.assertContains(resp, reverse('finance:bill-pay', args=[gala.pk, made.pk]))
        self.assertContains(resp, 'Mark paid')

    def test_a_multibill_waiting_on_the_client(self):
        soccomm = OrgFactory.create(name='SocComm')
        bulk = multibill([show('Film 1', soccomm), show('Film 2', soccomm)], soccomm, emailed_days_ago=3)
        resp = self.client.get(self.url + '?stage=waiting-on-client&fy=all')
        self.assertContains(resp, 'Fall films')
        self.assertContains(resp, 'Film 1, Film 2')
        self.assertContains(resp, reverse('finance:multibill-email', args=[bulk.pk]))
        self.assertContains(resp, reverse('finance:multibill-paid', args=[bulk.pk]))

    def test_paid_points_to_closing_the_event(self):
        gala = show('Gala')
        bill(gala, emailed_days_ago=30, paid_days_ago=2)
        resp = self.client.get(self.url + '?stage=paid&fy=all')
        self.assertContains(resp, 'Close it on its page')
        self.assertContains(resp, reverse('events:detail', args=[gala.pk]))


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

    def test_marked_to_bill_in_bulk_starts_a_multibill(self):
        film = show('Film', billed_in_bulk=True)
        self.assertContains(self.page(film), '%s?events=%s' % (reverse('finance:multibill-new'), film.pk))

    def test_create_isd_marks_it_entered_and_comes_back(self):
        gala = show('Gala', worktag='1234-CC', workday_fund=110)
        bill(gala, '250.00', emailed_days_ago=3)
        resp = self.page(gala)
        self.assertContains(resp, 'The client sent the worktag 1234-CC (110-FD).')
        self.assertContains(resp, reverse('finance:workday-entered', args=[gala.pk]))
        here = reverse('events:detail', args=[gala.pk])
        self.assertRedirects(self.client.post(reverse('finance:workday-entered', args=[gala.pk]),
                                              {'next': here + '#billing'}), here + '#billing')
        self.assertContains(self.page(gala), 'Next step: Waiting on approval.')

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

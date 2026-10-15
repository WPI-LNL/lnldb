"""
Where each bill stands, and what comes next.

Billing an event runs through the same steps every time. The Treasurer bills
the client, the client confirms the worktag to charge, the Treasurer creates
the Internal Service Delivery (ISD) in Workday, the client approves it, the
money arrives, and the event is closed. This module decides which of those
steps a bill is waiting on -- its *stage*. The Billing page lists bills by
stage, the event page's *Next step* box shows one event's, and the Owed to
LNL report labels each debt with it, so the three always agree.

Nothing here is stored. A stage is read off what the bill and its event
already record:

======================  =====================================================
Stage                   Read off
======================  =====================================================
Ready to bill           Reviewed, with no bill; or a bill that was never
                        emailed, which is shown as *Not sent*
Waiting on client       The bill has been emailed, and the client has not
                        sent a worktag through the bill's form
Create ISD              The client sent a worktag; the event is not yet
                        marked entered into Workday
Waiting on approval     Marked entered into Workday, and not yet paid
Paid                    The bill is paid and the event is still open
======================  =====================================================

Only events reviewed for billing and not yet closed have a stage: before the
review the event belongs to the VP, and closing it is the last step. The bill
that stands for an event is its latest own bill, else its latest multi-bill
(:func:`finance.calculators.latest_bill`), the same one finance's figures
read. A multi-bill is one row for all its events.

A multi-bill has no worktag form and no "entered into Workday" box, so until
the ISD is recorded on the bill itself it goes from *Waiting on client*
straight to *Paid*.
"""
import datetime
from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from finance.calculators import latest_bill
from finance.models import ZERO, MultiBilling, client_of, fiscal_year_for, money

READY = 'ready'
WAITING_ON_CLIENT = 'waiting-on-client'
CREATE_ISD = 'create-isd'
WAITING_ON_APPROVAL = 'waiting-on-approval'
PAID = 'paid'

#: Each stage's name, in the order a bill passes through them.
STAGES = OrderedDict((
    (READY, "Ready to bill"),
    (WAITING_ON_CLIENT, "Waiting on client"),
    (CREATE_ISD, "Create ISD"),
    (WAITING_ON_APPROVAL, "Waiting on approval"),
    (PAID, "Paid"),
))

#: What each stage is waiting for, as a sentence.
STAGE_HELP = {
    READY: "Reviewed for billing, and not yet sent a bill.",
    WAITING_ON_CLIENT: "The bill has been emailed. The client has not yet sent the worktag to charge.",
    CREATE_ISD: "The client sent a worktag. Create the Internal Service Delivery in Workday.",
    WAITING_ON_APPROVAL: "The ISD is in Workday, waiting for the client to approve it and the money to arrive.",
    PAID: "Paid. Close the event when nothing else is left to do on it.",
}

#: The memo an ISD is given in Workday: these words, then what is billed. The
#: ingestion queue reads the event back out of it when the payment arrives
#: (``finance.suggestions.ISD_MEMO_PREFIX``).
ISD_MEMO = "Lens and Lights services for %s"

#: How a change is described in the event's history when the client sends a
#: worktag through the bill's form, and when the event is marked entered into
#: Workday. The day each was last saved is the day the bill reached that stage.
WORKTAG_SENT_COMMENT = "Entered Workday billing info"
WORKDAY_ENTERED_COMMENT = "Marked entered into Workday"


class BillItem(object):
    """
    One row of the Billing page: an event billed on its own, or a multi-bill
    with every event on it.

    ``since`` is the day the item reached its stage, from which ``days`` is
    counted. ``not_sent`` marks a bill that exists but was never emailed,
    which is still ready to bill.
    """

    def __init__(self, stage, events, bill=None, since=None, not_sent=False):
        self.stage = stage
        self.events = events
        self.bill = bill
        self.since = since
        self.not_sent = not_sent

    def __repr__(self):
        return '<BillItem %s: %s>' % (self.stage, self.name)

    @property
    def is_multibill(self):
        return isinstance(self.bill, MultiBilling)

    @property
    def event(self):
        """ The event, for one billed on its own; the first, for a multi-bill. """
        return self.events[0] if self.events else None

    @property
    def name(self):
        return self.bill.display_name if self.is_multibill else self.event.event_name

    @property
    def stage_label(self):
        return STAGES[self.stage]

    @property
    def client(self):
        """ Who is billed: a multi-bill's *Bill to*, or the event's client. """
        if self.is_multibill:
            return self.bill.org
        return client_of(self.event)

    @property
    def date(self):
        """ The day the (first) event started, which decides its fiscal year. """
        if self.event is not None:
            return timezone.localtime(self.event.datetime_start).date()
        return self.bill.date_billed

    @property
    def fiscal_year(self):
        return fiscal_year_for(self.date)

    @property
    def url(self):
        if self.is_multibill:
            return reverse('finance:multibill-detail', args=(self.bill.pk,))
        return reverse('events:detail', args=(self.event.pk,))

    @property
    def days(self):
        """ Whole days the item has been at its stage, or ``None`` when that is not known. """
        if self.since is None:
            return None
        return (timezone.localdate() - self.since).days

    @property
    def price_now(self):
        """
        What the bill would come to if it were made today: the event's price,
        or what the multi-bill's events and charges add up to.
        """
        if not hasattr(self, '_price_now'):
            if self.is_multibill:
                self._price_now = self.bill.breakdown()['total']
            else:
                try:
                    self._price_now = money(self.event.cost_total)
                except Exception:
                    # A price the events app cannot work out is no price, not
                    # a crash on the Billing page.
                    self._price_now = None
        return self._price_now

    @property
    def amount(self):
        """ What was billed, or, before there is a bill, what would be. """
        if self.bill is not None:
            return money(self.bill.amount)
        return self.price_now

    @property
    def price_differs(self):
        """ Whether an unpaid bill no longer matches what its event(s) cost now. """
        if self.bill is None or self.bill.date_paid or self.price_now is None:
            return False
        return money(self.bill.amount) != self.price_now

    @property
    def last_emailed(self):
        """ When the bill was last emailed, or ``None``. """
        if self.bill is None:
            return None
        emails = (self.bill.multibillingemail_set.all() if self.is_multibill
                  else self.bill.billingemail_set.all())
        return _last_sent(emails)

    @property
    def memo(self):
        """ The ISD memo: "Lens and Lights services for" the event, or the multi-bill's name. """
        return ISD_MEMO % self.name

    @property
    def fund(self):
        """ The client's Workday fund, as Workday writes it ("810-FD"), or ``''``. """
        fund = getattr(self.event, 'workday_fund', None) if not self.is_multibill else None
        return '%s-FD' % fund if fund else ''

    @property
    def worktag(self):
        return (getattr(self.event, 'worktag', None) or '') if not self.is_multibill else ''


def _local_day(value):
    """ The local date of a datetime, or a date as it is. """
    if isinstance(value, datetime.datetime):
        return timezone.localdate(value) if timezone.is_aware(value) else value.date()
    return value


def _last_sent(emails):
    """ The day the latest of these bill emails went out, or ``None`` if none did. """
    sent = [email.sent_at for email in emails if email.sent_at is not None]
    return _local_day(max(sent)) if sent else None


def _reviewed_day(event):
    """ The day an event was reviewed for billing, or, with no record of it, the day it ended. """
    return _local_day(event.reviewed_on or event.datetime_end)


def _history_days(events, comment):
    """
    ``{event pk: day}`` of the latest change to each event saved under
    ``comment`` in its history, for the events that have one.
    """
    from reversion.models import Version
    from events.models import BaseEvent, Event2019

    if not events:
        return {}
    types = list(ContentType.objects.get_for_models(BaseEvent, Event2019).values())
    rows = (Version.objects.filter(content_type__in=types, object_id__in=[str(e.pk) for e in events],
                                   revision__comment__startswith=comment)
            .values('object_id').annotate(last=Max('revision__date_created')))
    return {int(row['object_id']): _local_day(row['last']) for row in rows}


def event_item(event, bill):
    """
    The item for an event billed on its own (or not yet billed at all), with
    its stage. ``since`` for *Create ISD* and *Waiting on approval* is filled
    in by :func:`_date_isd_stages`, which reads the event's history.
    """
    if bill is None:
        return BillItem(READY, [event], since=_reviewed_day(event))
    if bill.date_paid:
        return BillItem(PAID, [event], bill, since=bill.date_paid)
    if getattr(event, 'entered_into_workday', False):
        return BillItem(WAITING_ON_APPROVAL, [event], bill)
    if getattr(event, 'worktag', None):
        return BillItem(CREATE_ISD, [event], bill)
    sent = _last_sent(bill.billingemail_set.all())
    if sent is None:
        return BillItem(READY, [event], bill, since=bill.date_billed, not_sent=True)
    return BillItem(WAITING_ON_CLIENT, [event], bill, since=sent)


def multibill_item(bill):
    """ The item for a multi-bill and every event on it, with its stage. """
    events = sorted(bill.events.all(), key=lambda e: (e.datetime_start, e.pk))
    if bill.date_paid:
        return BillItem(PAID, events, bill, since=bill.date_paid)
    sent = _last_sent(bill.multibillingemail_set.all())
    if sent is None:
        return BillItem(READY, events, bill, since=bill.date_billed, not_sent=True)
    return BillItem(WAITING_ON_CLIENT, events, bill, since=sent)


def _date_isd_stages(items):
    """
    When each single bill at *Create ISD* or *Waiting on approval* got there:
    the day the client last sent the worktag, or the day the event was marked
    entered into Workday, from the event's history. An event with no such
    history -- one imported, or changed outside the site -- counts from the
    last step that left a date, back to the day it was billed.
    """
    isd = [item for item in items if item.stage in (CREATE_ISD, WAITING_ON_APPROVAL)]
    if not isd:
        return
    events = [item.event for item in isd]
    worktag_days = _history_days(events, WORKTAG_SENT_COMMENT)
    entered_days = _history_days([i.event for i in isd if i.stage == WAITING_ON_APPROVAL],
                                 WORKDAY_ENTERED_COMMENT)
    for item in isd:
        pk = item.event.pk
        fallback = worktag_days.get(pk) or item.last_emailed or item.bill.date_billed
        item.since = entered_days.get(pk, fallback) if item.stage == WAITING_ON_APPROVAL else fallback


def _billing_events(user=None):
    """
    Every event that has a stage: reviewed for billing and not yet closed,
    with what working out its stage reads. Hidden and test events are left out
    for a ``user`` who may not see them, as every event list does.
    """
    from events.models import BaseEvent

    events = (BaseEvent.objects.filter(reviewed=True, closed=False)
              .select_related('billing_org', 'contact')
              .prefetch_related('org', 'billings__billingemail_set', 'multibillings__org',
                                'multibillings__events', 'multibillings__multibillingemail_set'))
    if user is not None:
        if not user.has_perm('events.view_hidden_event'):
            events = events.exclude(sensitive=True)
        if not user.has_perm('events.view_test_event'):
            events = events.exclude(test_event=True)
    return events


def billing_items(user=None):
    """
    Everything with a stage, as :class:`BillItem`\\ s: one per event billed
    (or to be billed) on its own, and one per multi-bill that still has an
    open event on it.
    """
    items, multibills = [], OrderedDict()
    for event in _billing_events(user):
        bill = latest_bill(event)
        if isinstance(bill, MultiBilling):
            if bill.pk not in multibills:
                multibills[bill.pk] = multibill_item(bill)
            continue
        items.append(event_item(event, bill))
    items.extend(multibills.values())
    _date_isd_stages(items)
    return items


def item_for_event(event):
    """
    The item an event is part of, with its stage, or ``None`` when it has no
    stage: not yet reviewed for billing, or closed.
    """
    if event.closed or not event.reviewed:
        return None
    bill = latest_bill(event)
    item = multibill_item(bill) if isinstance(bill, MultiBilling) else event_item(event, bill)
    _date_isd_stages([item])
    return item


def stage_of(event, bill=None):
    """
    The stage an event's bill is at, or ``None`` when it has none. ``bill``
    saves looking it up again when the caller already has it.
    """
    if event.closed or not event.reviewed:
        return None
    bill = bill if bill is not None else latest_bill(event)
    if isinstance(bill, MultiBilling):
        return multibill_item(bill).stage
    return event_item(event, bill).stage


def projection_event_ids(event_ids):
    """
    Of these events, the ones on Projection's side of the partition: every
    service on them is a Projection service, as a film showing's is. An event
    that also had lighting or sound is Event Production's.
    """
    from events.models import BaseEvent, Category

    if not event_ids:
        return set()
    others = Category.objects.exclude(name='Projection').values_list('name', flat=True)
    events = BaseEvent.objects.filter(pk__in=event_ids)
    films = events.filter(Q(serviceinstance__service__category__name='Projection')
                          | Q(Event___projection__isnull=False))
    mixed = events.filter(Q(serviceinstance__service__category__name__in=others)
                          | Q(Event___lighting__isnull=False) | Q(Event___sound__isnull=False))
    return set(films.values_list('pk', flat=True)) - set(mixed.values_list('pk', flat=True))


def filter_items(items, fiscal_year=None, is_projection=None):
    """
    The items in a fiscal year (by the day their first event started) and on
    one side of the partition, as the finance filter bar asks. A multi-bill
    is Projection's when every event on it is.
    """
    if fiscal_year:
        items = [item for item in items if item.fiscal_year == fiscal_year]
    if is_projection is not None:
        films = projection_event_ids({event.pk for item in items for event in item.events})
        items = [item for item in items
                 if bool(item.events) and all(e.pk in films for e in item.events) == is_projection]
    return items


def by_stage(items):
    """ ``{stage: [items]}`` for every stage, each list longest-waiting first. """
    grouped = OrderedDict((stage, []) for stage in STAGES)
    for item in items:
        grouped[item.stage].append(item)
    for rows in grouped.values():
        rows.sort(key=lambda item: (item.since or datetime.date.max, item.date))
    return grouped


def ready_sections(items):
    """
    The *Ready to bill* items, split the way they are billed: bills made but
    never sent; events to bill on their own; and events marked to be billed
    in bulk, grouped by client, clients A to Z, as ``[{'client', 'items',
    'total'}]`` where ``total`` is what the group's events cost now.
    """
    not_sent = [item for item in items if item.not_sent]
    alone = [item for item in items if not item.not_sent and not item.event.billed_in_bulk]
    groups = OrderedDict()
    for item in items:
        if not item.not_sent and item.event.billed_in_bulk:
            groups.setdefault(item.client, []).append(item)
    bulk = [{'client': client, 'items': rows, 'total': sum((row.price_now or ZERO for row in rows), ZERO)}
            for client, rows in sorted(groups.items(), key=lambda pair: (
                pair[0] is None, pair[0].retname.lower() if pair[0] else ''))]
    return {'not_sent': not_sent, 'alone': alone, 'bulk': bulk}

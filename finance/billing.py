"""
Where each bill stands, and what comes next.

Billing an event runs through the same steps every time. The Treasurer bills
the client, the client confirms the worktag to charge, the Treasurer creates
the Internal Service Delivery (ISD) in Workday and records its number, the
client approves it, the money arrives, and the event is closed. This module
decides which of those steps a bill is waiting on -- its *stage*. The Billing
page lists bills by stage, the event page's *Next step* box shows one event's,
and the Owed to LNL report labels each debt with it, so the three always
agree.

A stage is read off what the bill and its event record:

======================  =====================================================
Stage                   Read off
======================  =====================================================
Ready to bill           Reviewed, with no bill; or a bill that was never
                        sent, which is shown as *Not sent*
No bill needed          The Treasurer decided the event is not billed
                        (:class:`~finance.models.NoBillNeeded`)
Waiting on client       The bill has been sent -- emailed, or marked sent
                        by the Treasurer -- and no worktag has come back
Create ISD              A worktag has come back: through the bill's form, onto
                        the event, or recorded on the bill by the Treasurer
Waiting on approval     The ISD's number is recorded on the bill -- or, for a
                        bill from before the number was kept, the event is
                        marked entered into Workday
Paid                    The bill is paid and the event is still open
======================  =====================================================

Only events reviewed for billing and not yet closed have a stage: before the
review the event belongs to the VP, and closing it is the last step. The bill
that stands for an event is its latest own bill, else its latest multi-bill
(:func:`finance.calculators.latest_bill`), the same one finance's figures
read. A multi-bill is one row for all its events. It has no form for the
client, so its worktag is always the one the Treasurer records.

A bill is paid when the Treasurer says so, never on its own. The ingestion
queue offers to mark it paid when the payment being filed covers it, and the
*Mark paid* form does it for anything else -- see *Payments* below. Then the
event is closed, from its own page or the Billing page (*Closing*), and the
weekly digest lists whatever has waited too long (*The weekly digest*).
"""
import datetime
from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from finance.calculators import bill_payments, days_owed, latest_bill, received_by_event
from finance.models import (ZERO, MultiBilling, books_start_date, client_of, dollars, finance_settings, fiscal_year_for,
                            money, no_bill_needed_for)

READY = 'ready'
NO_BILL_NEEDED = 'no-bill-needed'
WAITING_ON_CLIENT = 'waiting-on-client'
CREATE_ISD = 'create-isd'
WAITING_ON_APPROVAL = 'waiting-on-approval'
PAID = 'paid'

#: Each stage's name, in the order a bill passes through them. *No bill
#: needed* sits beside *Ready to bill*, as the other way out of it.
STAGES = OrderedDict((
    (READY, "Ready to bill"),
    (NO_BILL_NEEDED, "No bill needed"),
    (WAITING_ON_CLIENT, "Waiting on client"),
    (CREATE_ISD, "Create ISD"),
    (WAITING_ON_APPROVAL, "Waiting on approval"),
    (PAID, "Paid"),
))

#: What each stage is waiting for, as a sentence.
STAGE_HELP = {
    READY: "Reviewed for billing, and not yet sent a bill.",
    NO_BILL_NEEDED: "You decided these are not billed. Close each event when nothing else is left to do on it.",
    WAITING_ON_CLIENT: "The bill has been sent. The client has not yet sent the worktag to charge.",
    CREATE_ISD: "The client sent a worktag. Create the Internal Service Delivery in Workday, then record its "
                "number.",
    WAITING_ON_APPROVAL: "The ISD is in Workday, waiting for the client to approve it and the money to arrive.",
    PAID: "Paid. Close the event when nothing else is left to do on it.",
}

#: The memo an ISD is given in Workday: these words, then what is billed. The
#: ingestion queue reads the event back out of it when the payment arrives
#: (``finance.suggestions.ISD_MEMO_PREFIX``).
ISD_MEMO = "Lens and Lights services for %s"

#: How a change is described in the event's history when the client sends a
#: worktag through the bill's form, and when an event was marked entered into
#: Workday before ISD numbers were recorded. The day each was last saved is
#: the day the bill reached that stage, for a bill with no date of its own.
WORKTAG_SENT_COMMENT = "Entered Workday billing info"
WORKDAY_ENTERED_COMMENT = "Marked entered into Workday"


class BillItem(object):
    """
    One row of the Billing page: an event billed on its own, or a multi-bill
    with every event on it.

    ``since`` is the day the item reached its stage, from which ``days`` is
    counted. ``not_sent`` marks a bill that exists but was never sent,
    which is still ready to bill. ``no_bill`` is the event's *No bill needed*
    record, when it has one.

    ``received``, ``owed``, ``days_owed`` and ``last_payment`` are what has
    been filed against the bill, filled in by :func:`attach_payments`; ``None``
    until then, and for a bill whose payments were never imported.
    """

    def __init__(self, stage, events, bill=None, since=None, not_sent=False, no_bill=None):
        self.stage = stage
        self.events = events
        self.bill = bill
        self.since = since
        self.not_sent = not_sent
        self.no_bill = no_bill
        self.received = self.owed = self.days_owed = self.last_payment = None

    def __repr__(self):
        return '<BillItem %s: %s>' % (self.stage, self.name)

    @property
    def is_multibill(self):
        return isinstance(self.bill, MultiBilling)

    @property
    def key(self):
        """ What names the item in a form: ``e`` and the event's pk, or ``m`` and the multi-bill's. """
        if self.is_multibill:
            return 'm%s' % self.bill.pk
        return 'e%s' % self.event.pk

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
        """
        Whole days the item has been at its stage, or ``None`` when that is not
        known. Never fewer than none, whatever date was typed.
        """
        if self.since is None:
            return None
        return max((timezone.localdate() - self.since).days, 0)

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
    def suggest_no_bill(self):
        """
        Whether to suggest *No bill needed*, for SGA-funded: an event with no
        bill that is marked SGA-funded and comes to $0, which it does when it
        has no rentals or one-off charges. Only a suggestion; the Treasurer
        decides.
        """
        return (self.bill is None and self.no_bill is None
                and getattr(self.event, 'is_sga_funded', False) and self.price_now == ZERO)

    @property
    def last_sent(self):
        """ When the bill last went to the client, by email or otherwise, or ``None``. See :func:`sent_on`. """
        return None if self.bill is None else sent_on(self.bill)

    @property
    def sent_by_hand(self):
        """ Whether the bill last went out some other way than its email: marked sent by the Treasurer. """
        return self.bill is not None and self.bill.sent_on is not None and self.bill.sent_on == self.last_sent

    @property
    def memo(self):
        """ The ISD memo: "Lens and Lights services for" the event, or the multi-bill's name. """
        return ISD_MEMO % self.name

    @property
    def client_worktag(self):
        """ What the client sent through the bill's form: ``(worktag, fund)``, blank for a multi-bill. """
        if self.is_multibill:
            return '', None
        return (getattr(self.event, 'worktag', None) or ''), getattr(self.event, 'workday_fund', None)

    @property
    def worktag(self):
        """ The worktag to charge: the one recorded on the bill, else the one the client sent. """
        if self.bill is not None and self.bill.worktag_charged:
            return self.bill.worktag_charged
        return self.client_worktag[0]

    @property
    def fund_number(self):
        """ The Workday fund to charge, as a number, or ``None``. """
        if self.bill is not None and self.bill.worktag_charged:
            return self.bill.fund_charged
        return self.client_worktag[1]

    @property
    def fund(self):
        """ The fund to charge as Workday writes it ("810-FD"), or ``''``. """
        return '%s-FD' % self.fund_number if self.fund_number else ''

    @property
    def worktag_disagrees(self):
        """
        Whether the client's form says one worktag and the bill another: the
        Treasurer recorded one from an email, and the client then used the
        form as well.
        """
        sent = self.client_worktag[0]
        return bool(self.bill is not None and self.bill.worktag_charged and sent
                    and sent.upper() != self.bill.worktag_charged.upper())

    @property
    def requester(self):
        """
        Who asked for the work, for the ISD's requester: the event's contact,
        or, for a multi-bill, its client's person in charge, else its first
        event's contact.
        """
        if self.is_multibill and self.bill.org_id and self.bill.org.user_in_charge_id:
            return self.bill.org.user_in_charge
        return getattr(self.event, 'contact', None)

    @property
    def isd_differs(self):
        return self.bill is not None and self.bill.isd_differs

    @property
    def covered(self):
        """ Whether the payments filed against this unpaid bill add up to it. """
        return (self.bill is not None and not self.bill.date_paid
                and bool(self.received) and self.owed == ZERO)

    @property
    def close_refusal(self):
        """ Why the Billing page will not close this item, or ``None``. See :func:`close_refusal`. """
        return close_refusal(self)

    @property
    def paid_url(self):
        """ The *Mark paid* form. """
        if self.is_multibill:
            return reverse('finance:multibill-paid', args=(self.bill.pk,))
        return reverse('finance:bill-paid', args=(self.event.pk, self.bill.pk))

    @property
    def pdf_url(self):
        if self.is_multibill:
            return reverse('finance:multibill-pdf', args=(self.bill.pk,))
        return reverse('events:bills:pdf', args=(self.event.pk,))

    @property
    def sent_url(self):
        """ The *Mark sent* form, for a bill that reached the client some other way than its email. """
        if self.is_multibill:
            return reverse('finance:multibill-sent', args=(self.bill.pk,))
        return reverse('finance:bill-sent', args=(self.event.pk, self.bill.pk))

    @property
    def worktag_url(self):
        """ Where the Treasurer records the worktag a client sent by email. """
        if self.is_multibill:
            return reverse('finance:multibill-worktag', args=(self.bill.pk,))
        return reverse('finance:bill-worktag', args=(self.event.pk, self.bill.pk))

    @property
    def isd_url(self):
        """ Where the Treasurer records the ISD. """
        if self.is_multibill:
            return reverse('finance:multibill-isd', args=(self.bill.pk,))
        return reverse('finance:bill-isd', args=(self.event.pk, self.bill.pk))


def _local_day(value):
    """ The local date of a datetime, or a date as it is. """
    if isinstance(value, datetime.datetime):
        return timezone.localdate(value) if timezone.is_aware(value) else value.date()
    return value


def _last_emailed(emails):
    """ The day the latest of these bill emails went out, or ``None`` if none did. """
    sent = [email.sent_at for email in emails if email.sent_at is not None]
    return _local_day(max(sent)) if sent else None


def sent_on(bill):
    """
    The day a bill last went to its client: the latest email that sent it, or
    the day the Treasurer marked it sent some other way (``sent_on``),
    whichever is later. ``None`` if neither.
    """
    emails = bill.multibillingemail_set.all() if isinstance(bill, MultiBilling) else bill.billingemail_set.all()
    days = [day for day in (_last_emailed(emails), bill.sent_on) if day is not None]
    return max(days) if days else None


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


def event_item(event, bill, no_bill=None):
    """
    The item for an event billed on its own (or not yet billed at all), with
    its stage. ``since`` for a bill that reached *Create ISD* or *Waiting on
    approval* without a date of its own is filled in by
    :func:`_date_from_history`, which reads the event's history.
    """
    if bill is None:
        no_bill = no_bill if no_bill is not None else no_bill_needed_for(event)
        if no_bill is not None:
            return BillItem(NO_BILL_NEEDED, [event], since=_local_day(no_bill.decided_on), no_bill=no_bill)
        return BillItem(READY, [event], since=_reviewed_day(event))
    if bill.date_paid:
        return BillItem(PAID, [event], bill, since=bill.date_paid)
    sent = sent_on(bill)
    # A worktag on the event is only ever put there by the client's form; the
    # fund can be there without one, so it is not read.
    worktag_sent = bool(getattr(event, 'worktag', None))
    entered = getattr(event, 'entered_into_workday', False)
    if bill.isd_number:
        return BillItem(WAITING_ON_APPROVAL, [event], bill, since=bill.isd_entered_on)
    if entered:
        return BillItem(WAITING_ON_APPROVAL, [event], bill)
    if bill.worktag_charged:
        return BillItem(CREATE_ISD, [event], bill, since=bill.worktag_entered_on)
    if worktag_sent:
        return BillItem(CREATE_ISD, [event], bill)
    if sent is None:
        return BillItem(READY, [event], bill, since=bill.date_billed, not_sent=True)
    return BillItem(WAITING_ON_CLIENT, [event], bill, since=sent)


def multibill_item(bill):
    """ The item for a multi-bill and every event on it, with its stage. """
    events = sorted(bill.events.all(), key=lambda e: (e.datetime_start, e.pk))
    if bill.date_paid:
        return BillItem(PAID, events, bill, since=bill.date_paid)
    if bill.isd_number:
        return BillItem(WAITING_ON_APPROVAL, events, bill, since=bill.isd_entered_on)
    if bill.worktag_charged:
        return BillItem(CREATE_ISD, events, bill, since=bill.worktag_entered_on)
    sent = sent_on(bill)
    if sent is None:
        return BillItem(READY, events, bill, since=bill.date_billed, not_sent=True)
    return BillItem(WAITING_ON_CLIENT, events, bill, since=sent)


def _date_from_history(items):
    """
    When each single bill that reached *Create ISD* or *Waiting on approval*
    without a date of its own got there: the day the client last sent the
    worktag through the bill's form, or, for a bill from before ISD numbers
    were recorded, the day its event was marked entered into Workday -- both
    from the event's history. An event with no such history (one imported, or
    changed outside the site) counts from the last step that left a date, back
    to the day it was billed.
    """
    undated = [item for item in items if item.since is None and not item.is_multibill
               and item.stage in (CREATE_ISD, WAITING_ON_APPROVAL)]
    if not undated:
        return
    worktag_days = _history_days([item.event for item in undated], WORKTAG_SENT_COMMENT)
    entered_days = _history_days([item.event for item in undated if item.stage == WAITING_ON_APPROVAL],
                                 WORKDAY_ENTERED_COMMENT)
    for item in undated:
        pk = item.event.pk
        fallback = (worktag_days.get(pk) or item.bill.worktag_entered_on or item.last_sent
                    or item.bill.date_billed)
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
              .prefetch_related('org', 'no_bill_needed__decided_by', 'billings__billingemail_set',
                                'multibillings__org__user_in_charge', 'multibillings__events',
                                'multibillings__multibillingemail_set'))
    if user is not None:
        if not user.has_perm('events.view_hidden_event'):
            events = events.exclude(sensitive=True)
        if not user.has_perm('events.view_test_event'):
            events = events.exclude(test_event=True)
    return events


def billing_items(user=None):
    """
    Everything with a stage, as :class:`BillItem`\\ s: one per event billed
    (or to be billed, or not to be billed) on its own, and one per multi-bill
    that still has an open event on it.
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
    _date_from_history(items)
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
    _date_from_history([item])
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


# ---------------------------------------------------------------------------
# Payments
#
# The money for a bill arrives in Workday, and is filed against the bill's
# event (or, for a multi-bill, split across its events) from the ingestion
# queue. What has been filed is what the bill has received. Marking the bill
# paid stays the Treasurer's: the queue offers to when the payment it files
# covers the bill, dated the day the last of the money arrived, and the *Mark
# paid* form does it for anything else -- cash, a check, a bill from before
# the books start -- and asks how it was paid.
# ---------------------------------------------------------------------------

def bill_closed(bill):
    """ Whether an event the bill covers is closed, which locks the bill. """
    if isinstance(bill, MultiBilling):
        return any(event.closed for event in bill.events.all())
    return bill.event.closed


def payment_offer(bill, amount, arrived):
    """
    What filing a payment of ``amount`` against ``bill``, which reached Workday
    on ``arrived``, would do, for the box that offers to mark the bill paid.

    A dict of ``bill``, ``paid_on`` (the day the last of its money arrived,
    this payment's included), ``received`` (with this payment) and ``owed``,
    when the payments filed against the bill would then cover it. ``None``
    when they would not, or the bill is already paid, or an event on it is
    closed.
    """
    if bill is None or bill.date_paid or bill_closed(bill):
        return None
    received, last = bill_payments(bill)
    owed = money(bill.amount)
    received += money(amount)
    if owed <= ZERO or received < owed:
        return None
    paid_on = max(day for day in (last, arrived) if day is not None)
    return {'bill': bill, 'paid_on': paid_on, 'received': received, 'owed': owed}


def mark_paid_from_payments(bill):
    """
    Mark ``bill`` paid on the day the last of its money arrived, when the
    payments filed against it cover it. Returns that day, or ``None`` when the
    bill was left as it was: already paid, or not yet covered.
    """
    received, last = bill_payments(bill)
    owed = money(bill.amount)
    if bill.date_paid or last is None or owed <= ZERO or received < owed:
        return None
    bill.date_paid = last
    bill.paid_note = ''
    bill.save(update_fields=['date_paid', 'paid_note'])
    return last


def attach_payments(items, today=None, paid=False):
    """
    Give each unpaid bill among ``items`` -- and with ``paid``, each paid one
    too -- what has been received against it, what is still owed, how many
    days it has been owed and when the last payment arrived, in one query for
    them all.

    Received and owed are worked out as the Owed to LNL report works them
    out, and the days by the same :func:`~finance.calculators.days_owed`, so
    the Billing page and the report agree. Like the report, a bill for events
    from before the books start gets none of them: their payments were never
    imported.
    """
    billed = [item for item in items if item.bill is not None and (paid or not item.bill.date_paid)]
    if not billed:
        return
    start = books_start_date()
    today = today or timezone.localdate()
    filed = received_by_event({event.pk for item in billed for event in item.events})
    for item in billed:
        if start is not None and any(_local_day(event.datetime_start) < start for event in item.events):
            continue
        payments = [filed[event.pk] for event in item.events if event.pk in filed]
        days = [last for _, last in payments if last is not None]
        item.received = sum((received for received, _ in payments), ZERO)
        item.owed = max(item.amount - item.received, ZERO)
        item.days_owed = days_owed(item.bill, item.owed, today)
        item.last_payment = max(days) if days else None


# ---------------------------------------------------------------------------
# Closing
#
# Closing an event is the last step: it locks the event and takes it off every
# working list. Besides the event page's Close button, the Billing page closes
# events from its Paid and No bill needed tabs, one at a time or ticked
# together, and does exactly what that button does. Unlike the button, it will
# not close an event money is still owed on: a bill marked paid that the
# payments filed from Workday do not cover stays open, because closing it
# would hide the debt everywhere but the Owed to LNL report.
# ---------------------------------------------------------------------------

#: The stages the Billing page closes events from.
CLOSABLE = (PAID, NO_BILL_NEEDED)


def closable_items(user=None):
    """
    The items at a stage the Billing page closes events from, each with what
    has been filed against its bill (see :func:`attach_payments`).
    """
    items = [item for item in billing_items(user) if item.stage in CLOSABLE]
    attach_payments(items, paid=True)
    return items


def close_refusal(item):
    """
    Why the Billing page will not close ``item``, as a phrase, or ``None``
    when it will. The item needs :func:`attach_payments`, with ``paid``.

    Money is still owed when the payments filed against a paid bill come to
    less than it, counted as the Owed to LNL report counts it. A bill for
    events from before the books start has no payments on file to count, so
    its being marked paid is taken as it stands, as the report takes it.
    """
    if item.stage not in CLOSABLE:
        return "it is not paid"
    if item.owed and not item.received:
        return "none of the %s billed has been received" % dollars(item.amount)
    if item.owed:
        return "%s of the %s billed has not been received" % (dollars(item.owed), dollars(item.amount))
    return None


def close_item(item, user):
    """
    Close every event on ``item`` that is still open, as the event page's
    Close button does: marked closed, by ``user``, now. The caller names the
    change "Closed" in the events' history. Returns the events closed.
    """
    from events.models import BaseEvent

    now = timezone.now()
    closed = []
    # Fetched again through the polymorphic manager, as the event page fetches
    # the event it closes, so each is saved, and kept in its history, as the
    # kind of event it really is.
    events = (BaseEvent.objects.filter(pk__in=[event.pk for event in item.events], closed=False)
              .order_by('datetime_start', 'pk'))
    for event in events:
        event.closed = True
        event.closed_by = user
        event.closed_on = now
        event.save()
        closed.append(event)
    return closed


# ---------------------------------------------------------------------------
# The weekly digest
#
# What the billing_digest command emails the Treasurer each week: bills the
# client has not answered, ISDs not yet approved, and events ready to close.
# How long is too long is set in Finance Configuration. The digest only says
# who is due a reminder. Emailing a client again stays a button the Treasurer
# presses, because the Treasurer confirms every worktag personally.
# ---------------------------------------------------------------------------

def digest():
    """
    What the weekly billing digest lists, as a dict:

    * ``waiting_on_client``: bills the client has not answered at least
      ``client_days`` days after they were last sent (14 to start);
    * ``waiting_on_approval``: ISDs still waiting at least ``approval_days``
      days after they were recorded (21 to start);
    * ``to_close``: events paid, or needing no bill, that are still open.
      Each item's ``close_refusal`` says why the Billing page will not close
      it, if it will not.

    Each list is longest-waiting first, and every item has what has been
    filed against its bill (:func:`attach_payments`). Every fiscal year
    counts: a bill does not stop needing work when the year turns. Test
    events are left out.
    """
    config = finance_settings()
    items = [item for item in billing_items()
             if not all(getattr(event, 'test_event', False) for event in item.events)]
    stages = by_stage(items)
    client = [item for item in stages[WAITING_ON_CLIENT]
              if item.days is not None and item.days >= config.digest_client_days]
    approval = [item for item in stages[WAITING_ON_APPROVAL]
                if item.days is not None and item.days >= config.digest_approval_days]
    to_close = sorted(stages[PAID] + stages[NO_BILL_NEEDED],
                      key=lambda item: (item.since or datetime.date.max, item.date))
    attach_payments(client + approval + to_close, paid=True)
    return {'waiting_on_client': client, 'waiting_on_approval': approval, 'to_close': to_close,
            'client_days': config.digest_client_days, 'approval_days': config.digest_approval_days}

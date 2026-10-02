"""
Derived figures for the executive dashboard.

Everything here takes the same ``(fiscal_year, is_projection)`` pair the global
filter bar produces, so every widget on the page answers the same question for
the same slice of the ledger.
"""
import datetime
from collections import OrderedDict
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth

from finance.models import (ZERO, ClientType, FundingRequest, ParsedTransaction,
                            books_start_date, client_of, client_type_for, fiscal_year_bounds,
                            money, service_colors)

# ---------------------------------------------------------------------------
# Palette
#
# A colourblind-safe qualitative ramp for anything open-ended -- clients and
# projects cycle through it by rank. Spend categories carry their own colour on
# the SpendCategory row so the Treasurer can recolour a slice from the admin,
# and it stays the same slice on every chart.
# ---------------------------------------------------------------------------

SERIES_COLORS = (
    '#4E79A7', '#F28E2B', '#59A14F', '#E15759', '#B07AA1',
    '#76B7B2', '#EDC948', '#9C755F', '#FF9DA7', '#86BCB6',
)

FALLBACK_COLOR = '#BAB0AC'

# Service colours live in the ServiceColor table, keyed to the events app's own
# Category rows -- see finance.models.service_colors(). A category with no row
# falls back to the ramp below, so adding a service needs no code and no data.

CLIENT_TYPE_COLORS = {
    ClientType.STUDENT_ORG: '#59A14F',
    ClientType.DEPARTMENT: '#4E79A7',
    ClientType.UNKNOWN: FALLBACK_COLOR,
}


def series_color(index):
    """
    The ramp colour for the ``index``-th series, wrapping when it runs out.

    Callers pass a rank, not an id, so the biggest slice is always the same
    colour from one page load to the next.
    """
    return SERIES_COLORS[index % len(SERIES_COLORS)]


def _scoped(queryset, fiscal_year=None, is_projection=None):
    """ Apply the global filter bar to a ParsedTransaction queryset. """
    if fiscal_year:
        start, end = fiscal_year_bounds(fiscal_year)
        queryset = queryset.filter(effective_date__range=(start, end))
    if is_projection is not None:
        queryset = queryset.filter(is_projection=is_projection)
    return queryset


def _percent(part, whole):
    """
    ``part`` as a percentage of ``whole``, to one decimal place.

    A zero denominator yields ``0.0`` rather than raising: an empty year is a
    perfectly normal thing for the dashboard to be asked to draw.
    """
    if not whole:
        return Decimal('0.0')
    return (Decimal(part) / Decimal(whole) * 100).quantize(Decimal('0.1'))


# ---------------------------------------------------------------------------
# Spending by LNL category (the original pie)
# ---------------------------------------------------------------------------

def spend_by_category(fiscal_year=None, is_projection=None):
    """
    Spending grouped by LNL spend category. Positive figures, largest first,
    uncategorised excluded.
    """
    qs = _scoped(ParsedTransaction.objects.expenses().exclude(lnl_spend_category__isnull=True),
                 fiscal_year, is_projection)

    # Name, slug and colour all come from the category row, so renaming or
    # recolouring one in the admin flows straight through to the chart.
    rows = (qs.values('lnl_spend_category__slug', 'lnl_spend_category__name',
                      'lnl_spend_category__color')
              .annotate(total=Sum('amount')).order_by('total'))
    out = []
    for row in rows:
        amount = -money(row['total'])
        if amount <= 0:
            continue
        out.append({
            'key': row['lnl_spend_category__slug'],
            'label': row['lnl_spend_category__name'],
            'amount': amount,
            'color': row['lnl_spend_category__color'] or FALLBACK_COLOR,
        })
    grand = sum((r['amount'] for r in out), Decimal('0.00'))
    for row in out:
        row['percent'] = _percent(row['amount'], grand)
    return out


# ---------------------------------------------------------------------------
# Cash flow over time
# ---------------------------------------------------------------------------

def cash_flow_by_month(fiscal_year=None, is_projection=None, months=12):
    """
    Money in and money out per calendar month, oldest first.

    When a fiscal year is selected the series covers exactly that year so the
    columns line up with the rest of the dashboard; otherwise it shows the last
    ``months`` months up to today.
    """
    qs = _scoped(ParsedTransaction.objects.all(), fiscal_year, is_projection)

    if fiscal_year:
        start, end = fiscal_year_bounds(fiscal_year)
    else:
        end = datetime.date.today()
        # Step back whole months rather than approximating with 31-day jumps,
        # which overshoots and yields months + 1 buckets.
        ordinal = end.year * 12 + (end.month - 1) - (months - 1)
        start = datetime.date(ordinal // 12, ordinal % 12 + 1, 1)
        qs = qs.filter(effective_date__range=(start, end))

    # Money in and money out are summed separately -- netting them per month
    # would hide a month that had heavy activity in both directions.
    revenue_agg = (qs.revenue().annotate(month=TruncMonth('effective_date'))
                     .values('month').annotate(total=Sum('amount')))
    expense_agg = (qs.expenses().annotate(month=TruncMonth('effective_date'))
                     .values('month').annotate(total=Sum('amount')))

    revenue_by = {r['month']: money(r['total']) for r in revenue_agg}
    expense_by = {r['month']: -money(r['total']) for r in expense_agg}

    buckets = OrderedDict()
    cursor = datetime.date(start.year, start.month, 1)
    last = datetime.date(end.year, end.month, 1)
    while cursor <= last:
        buckets[cursor] = {'label': cursor.strftime('%b %y'),
                           'revenue': Decimal('0.00'), 'expense': Decimal('0.00')}
        cursor = datetime.date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)

    for month, amount in revenue_by.items():
        key = month.date() if hasattr(month, 'date') else month
        if key in buckets:
            buckets[key]['revenue'] = amount
    for month, amount in expense_by.items():
        key = month.date() if hasattr(month, 'date') else month
        if key in buckets:
            buckets[key]['expense'] = amount

    out = list(buckets.values())
    for row in out:
        row['net'] = row['revenue'] - row['expense']
    return out


# ---------------------------------------------------------------------------
# Revenue analysis
#
# Revenue routing is per-entry and depends on the linked Event's client and
# services, which live on a polymorphic model. Rather than three separate
# query passes, one enriched pass feeds every revenue widget.
# ---------------------------------------------------------------------------

def _service_costs(event):
    """
    ``{category name: list price}`` for a show, used purely as relative weights.

    List price (``Service.base_cost``) is deliberate: the pricelist lookup on
    ``ServiceInstance.cost`` issues a query per instance, and only the ratio
    between services matters here.
    """
    costs = {}
    instances = getattr(event, 'serviceinstance_set', None)
    if instances is not None:
        for instance in instances.all():
            service = instance.service
            if service is None:
                continue
            name = service.category.name if service.category_id else 'Other'
            costs[name] = costs.get(name, Decimal('0.00')) + (service.base_cost or Decimal('0.00'))
    if costs:
        return costs

    # Legacy Event: one flat service per slot.
    for attr, label in (('lighting', 'Lighting'), ('sound', 'Sound'), ('projection', 'Projection')):
        service = getattr(event, attr, None)
        if service is not None:
            costs[label] = costs.get(label, Decimal('0.00')) + (service.base_cost or Decimal('0.00'))
    return costs


def revenue_rows(fiscal_year=None, is_projection=None):
    """
    Every revenue slice with its Event resolved to a concrete subclass.

    ``select_related`` on a polymorphic FK hands back base instances, which
    would hide ``Event2019.workday_fund``, so the events are re-fetched through
    the polymorphic manager and joined up in Python.
    """
    from events.models import BaseEvent

    entries = list(_scoped(ParsedTransaction.objects.revenue(), fiscal_year, is_projection))
    event_ids = {e.linked_event_id for e in entries if e.linked_event_id}

    events = {}
    if event_ids:
        qs = (BaseEvent.objects.filter(pk__in=event_ids)
              .select_related('billing_org')
              .prefetch_related('org', 'serviceinstance_set__service__category'))
        events = {event.pk: event for event in qs}

    rows = []
    for entry in entries:
        event = events.get(entry.linked_event_id)
        rows.append({'entry': entry, 'event': event, 'amount': entry.amount})
    return rows


def revenue_by_client(fiscal_year=None, is_projection=None, limit=8, rows=None):
    """ Where the money came from, biggest first, with a rolled-up "Others". """
    rows = revenue_rows(fiscal_year, is_projection) if rows is None else rows

    totals, shows = {}, {}

    for row in rows:
        event = row['event']
        if event is not None:
            org = client_of(event)
            label = org.retname if org else '(no client on file)'
        else:
            source = row['entry'].non_event_revenue_type
            label = str(source) if source else 'Other non-event'
        totals[label] = totals.get(label, Decimal('0.00')) + row['amount']
        shows[label] = shows.get(label, 0) + 1

    ordered = sorted(totals.items(), key=lambda kv: -kv[1])
    grand = sum(totals.values(), Decimal('0.00'))

    out = []
    for index, (label, amount) in enumerate(ordered[:limit]):
        out.append({'label': label, 'amount': amount, 'entries': shows[label],
                    'color': series_color(index), 'percent': _percent(amount, grand)})

    remainder = ordered[limit:]
    if remainder:
        amount = sum((a for _, a in remainder), Decimal('0.00'))
        out.append({'label': '%s others' % len(remainder), 'amount': amount,
                    'entries': sum(shows[name] for name, _ in remainder),
                    'color': '#BAB0AC', 'percent': _percent(amount, grand)})
    return out


def client_type_breakdown(fiscal_year=None, is_projection=None, rows=None):
    """
    Department vs Student Organization, by revenue and by number of shows.

    Non-event revenue (SGA baseline, alumni gifts) has no client and is
    excluded rather than silently bucketed as "Unknown".
    """
    rows = revenue_rows(fiscal_year, is_projection) if rows is None else rows

    totals = OrderedDict((k, Decimal('0.00')) for k in
                         (ClientType.STUDENT_ORG, ClientType.DEPARTMENT, ClientType.UNKNOWN))
    events_seen = {k: set() for k in totals}

    for row in rows:
        event = row['event']
        if event is None:
            continue
        kind = client_type_for(event)
        totals[kind] += row['amount']
        events_seen[kind].add(event.pk)

    grand = sum(totals.values(), Decimal('0.00'))
    out = []
    for kind, amount in totals.items():
        if amount == 0 and not events_seen[kind]:
            continue
        out.append({
            'key': kind,
            'label': ClientType(kind).label,
            'amount': amount,
            'shows': len(events_seen[kind]),
            'color': CLIENT_TYPE_COLORS.get(kind, '#BAB0AC'),
            'percent': _percent(amount, grand),
        })
    return out


def service_mix(fiscal_year=None, is_projection=None, rows=None):
    """
    Revenue attributed to Lighting / Sound / Projection / other.

    A show's revenue is split across its service categories in proportion to
    their list prices, so a two-service show contributes to both rather than
    being filed under whichever service happens to be first. Shows with no
    recorded services are grouped as "Unspecified" instead of being dropped.
    """
    rows = revenue_rows(fiscal_year, is_projection) if rows is None else rows

    totals, shows = {}, {}
    for row in rows:
        event = row['event']
        if event is None:
            continue
        costs = _service_costs(event)
        if not costs:
            totals['Unspecified'] = totals.get('Unspecified', Decimal('0.00')) + row['amount']
            shows.setdefault('Unspecified', set()).add(event.pk)
            continue

        weight_total = sum(costs.values())
        names = list(costs.keys())
        for index, name in enumerate(names):
            if weight_total > 0:
                share = row['amount'] * (costs[name] / weight_total)
            else:
                share = row['amount'] / len(names)
            # Absorb rounding drift into the last slice so the parts still sum
            # exactly to the whole.
            share = share.quantize(Decimal('0.01'))
            totals[name] = totals.get(name, Decimal('0.00')) + share
            shows.setdefault(name, set()).add(event.pk)

    ordered = sorted(totals.items(), key=lambda kv: -kv[1])
    grand = sum(totals.values(), Decimal('0.00'))
    out = []
    for index, (name, amount) in enumerate(ordered):
        out.append({
            'label': name,
            'amount': amount,
            'shows': len(shows[name]),
            'color': service_colors().get(name, series_color(index + 3)),
            'percent': _percent(amount, grand),
        })
    return out


# ---------------------------------------------------------------------------
# What one event made or lost
#
# An event's P&L is what its linked entries say, set against what the events
# app says it was billed. Three things about it are decisions rather than
# arithmetic, and each is easy to get wrong:
#
# * **Which year.** An event belongs to the fiscal year it *ran* in, and all of
#   its entries come with it whenever they landed. A late-June show is billed
#   in July; filing its revenue and its rental under different years would
#   report half a show twice.
# * **What was billed.** The most recent bill, not the sum of them. A bill is
#   reissued when it was wrong, so two Billing rows for one show are usually
#   one bill and its correction. A multi-bill covers several shows with one
#   figure, so each show's share is split by what it would have cost alone.
# * **What counts as a cost.** Linked expenses that have reached Workday, net
#   of refunds. An encumbrance is reported beside it as *reserved*, because it
#   is money not yet spent, and adding it in would show a loss that may never
#   happen.
# ---------------------------------------------------------------------------

#: The three ways a linked entry can bear on an event, as filters over
#: ParsedTransaction. Kept in one place so the single-event figure and the
#: whole-year table cannot disagree about what a cost is.
_EVENT_REVENUE = Q(amount__gt=0, refund_of__isnull=True)
_EVENT_COST = Q(parent_transaction__isnull=False) & (Q(amount__lt=0) | Q(refund_of__isnull=False))
_EVENT_RESERVED = Q(parent_transaction__isnull=True, refund_of__isnull=True, amount__lt=0)
_EVENT_PASSTHROUGH = _EVENT_COST & Q(lnl_spend_category__is_event_passthrough=True)

#: How each flag reads on screen.
EVENT_FLAGS = OrderedDict((
    ('loss', 'Cost more than it brought in'),
    ('rental_under_billed', 'Rental cost more than was billed for it'),
    ('billed_not_received', 'Billed, not yet received'),
    ('received_without_bill', 'Received with no bill in lnldb'),
    ('not_marked_paid', 'Paid in full, bill not marked paid'),
    ('paid_not_received', 'Marked paid, no payment filed'),
))

#: Where an event's bill stands, as the P&L and the event page say it.
PAYMENT_STATES = {
    'not_billed': 'Not billed',
    'awaiting': 'Billed, nothing received',
    'part': 'Part received',
    'paid': 'Received in full',
    'unbilled_income': 'Received, no bill',
}


def _event_sums(queryset):
    """ The four sums an event's figures are built from, over its linked entries. """
    return queryset.aggregate(
        received=Sum('amount', filter=_EVENT_REVENUE),
        costs=Sum('amount', filter=_EVENT_COST),
        reserved=Sum('amount', filter=_EVENT_RESERVED),
        passthrough=Sum('amount', filter=_EVENT_PASSTHROUGH),
        entries=Count('pk'))


def multibill_shares(multibilling):
    """
    ``{event pk: share}`` of one multi-bill, splitting its single figure.

    Weighted by what each show would have been billed on its own
    (``cost_total``), and split evenly when none of them has a price. The last
    show takes whatever rounding is left, so the shares add up to the bill to
    the cent.
    """
    events = sorted(multibilling.events.all(), key=lambda e: e.pk)
    if not events:
        return {}
    weights = []
    for event in events:
        try:
            weights.append(max(money(getattr(event, 'cost_total', ZERO)), ZERO))
        except Exception:
            # A price the events app cannot work out is no price, not a crash
            # on a finance page.
            weights.append(ZERO)
    total = sum(weights, ZERO)
    amount = money(multibilling.amount)

    shares, allotted = {}, ZERO
    for index, event in enumerate(events):
        if index == len(events) - 1:
            share = amount - allotted
        elif total > 0:
            share = money(amount * weights[index] / total)
        else:
            share = money(amount / len(events))
        shares[event.pk] = share
        allotted += share
    return shares


def latest_bill(event):
    """
    The bill that stands for an event: its latest own bill, else its latest
    multi-bill, else ``None``. The same choice :func:`event_billed` makes.
    """
    bills = sorted(event.billings.all(), key=lambda b: (b.date_billed, b.pk))
    if bills:
        return bills[-1]
    multis = sorted(event.multibillings.all(), key=lambda m: (m.date_billed, m.pk))
    return multis[-1] if multis else None


def event_billed(event, _cache=None):
    """
    What lnldb says this event was billed, and how: ``(amount, source)``.

    ``source`` is ``'bill'`` for a bill of its own, ``'multibill'`` for its
    share of one covering several shows, or ``None`` with an amount of ``None``
    when it was never billed. See the section comment for why it is the most
    recent bill rather than the total of them.
    """
    bills = sorted(event.billings.all(), key=lambda b: (b.date_billed, b.pk))
    if bills:
        return money(bills[-1].amount), 'bill'

    multis = sorted(event.multibillings.all(), key=lambda m: (m.date_billed, m.pk))
    if multis:
        latest = multis[-1]
        cache = {} if _cache is None else _cache
        if latest.pk not in cache:
            cache[latest.pk] = multibill_shares(latest)
        return cache[latest.pk].get(event.pk, ZERO), 'multibill'
    return None, None


def _event_figures(event, sums, multibill_cache=None, books_start=None, today=None):
    """
    One event's row, from its sums and the events app's own records.

    ``books_start`` is when the ledger starts accounting for every line. A bill
    marked paid before then has no payment in the ledger to find, so it is not
    flagged for lacking one.
    """
    received = money(sums.get('received'))
    costs = -money(sums.get('costs'))
    reserved = -money(sums.get('reserved'))
    passthrough = -money(sums.get('passthrough'))
    billed, billed_source = event_billed(event, multibill_cache)

    rentals = list(event.rentals.all())
    rentals_billed = sum((money(r.totalcost) for r in rentals), ZERO)
    # Only an Event2019 charges a rental fee, and asking for it costs a query,
    # so it is asked only of a show that actually hired something in.
    rental_fee = money(getattr(event, 'rental_fee_total', ZERO)) if rentals else ZERO

    margin = received - costs
    org = client_of(event)
    kind = client_type_for(event)

    flags = []
    if costs > 0 and margin < 0:
        flags.append('loss')
    # The fee is part of what the client paid for the hire, so the hire is
    # covered when the two together are at least what the gear cost. Only
    # asked of an event that itemised its rentals: with none recorded there is
    # no billed figure to fall short of, and a hire nobody billed for already
    # shows up as the loss it is.
    rentals_recovered = rentals_billed + rental_fee
    if rentals and passthrough > rentals_recovered:
        flags.append('rental_under_billed')
    if billed is not None and billed > received:
        flags.append('billed_not_received')
    if billed is None and received > 0:
        flags.append('received_without_bill')

    # Where the bill stands. lnldb's own "paid" date is the events app's
    # record; the ledger's is what actually arrived. Each is checked against
    # the other, and neither is changed here -- marking a bill paid is a
    # button, pressed by a person.
    bill = latest_bill(event)
    paid_on = getattr(bill, 'date_paid', None)
    if billed is None:
        state = 'unbilled_income' if received > 0 else 'not_billed'
    elif received <= 0:
        state = 'awaiting'
    elif received < billed:
        state = 'part'
    else:
        state = 'paid'
    if state == 'paid' and bill is not None and paid_on is None:
        flags.append('not_marked_paid')
    in_books = books_start is None or event.datetime_start.date() >= books_start
    if paid_on is not None and received <= 0 and billed and in_books:
        flags.append('paid_not_received')
    owed = billed - received if billed is not None and billed > received else ZERO
    today = today or datetime.date.today()
    days_owed = ((today - bill.date_billed).days
                 if owed > 0 and bill is not None and bill.date_billed else None)

    return {
        'event': event,
        'client': org.retname if org else '',
        'client_type': ClientType(kind).label,
        'billed': billed,
        'billed_source': billed_source,
        'received': received,
        'costs': costs,
        'reserved': reserved,
        'margin': margin,
        'margin_percent': _percent(margin, received) if received > 0 else None,
        'rentals_billed': rentals_billed,
        'rental_fee': rental_fee,
        'rentals_recovered': rentals_recovered,
        'passthrough_cost': passthrough,
        'flags': [(key, EVENT_FLAGS[key]) for key in flags],
        'flag_keys': flags,
        'entries': sums.get('entries') or 0,
        'bill': bill,
        'bill_paid_on': paid_on,
        'payment_state': state,
        'payment_state_label': PAYMENT_STATES[state],
        'owed': owed,
        'days_owed': days_owed,
        'can_mark_paid': 'not_marked_paid' in flags,
    }


def _event_queryset():
    """ Events with everything the figures read, through the polymorphic manager. """
    from events.models import BaseEvent

    # Re-fetched through the polymorphic manager for the same reason as
    # revenue_rows(): a base BaseEvent hides Event2019's workday_fund, and with
    # it the client type, and its rental fee.
    return (BaseEvent.objects.select_related('billing_org')
            .prefetch_related('org', 'rentals', 'billings', 'multibillings__events'))


def event_financials(event, is_projection=None):
    """
    What one event was billed, brought in and cost, as a dict.

    Every linked entry counts whatever fiscal year it landed in; see the
    section comment above. ``is_projection`` narrows the entries to one side of
    the partition, as the filter bar does everywhere else.
    """
    entries = ParsedTransaction.objects.filter(linked_event_id=event.pk)
    if is_projection is not None:
        entries = entries.filter(is_projection=is_projection)
    fresh = _event_queryset().filter(pk=event.pk).first() or event
    return _event_figures(fresh, _event_sums(entries), books_start=books_start_date())


def event_pnl_rows(fiscal_year=None, is_projection=None, include_unlinked=False, since=None):
    """
    Every event's figures for the year it ran in, worst margin first.

    By default only events with something linked to them: those are the ones
    with a story to tell. ``include_unlinked`` adds every event that was billed
    but has nothing filed against it yet, which is mostly a list of revenue
    still waiting in the queue -- useful, but it buries the costs.

    ``since`` keeps only events that ran on or after a date, whatever the year:
    what is still owed is a question about every year the books cover.
    """
    entries = ParsedTransaction.objects.filter(linked_event__isnull=False)
    if is_projection is not None:
        entries = entries.filter(is_projection=is_projection)
    if fiscal_year:
        start, end = fiscal_year_bounds(fiscal_year)
        entries = entries.filter(linked_event__datetime_start__date__range=(start, end))
    if since is not None:
        entries = entries.filter(linked_event__datetime_start__date__gte=since)

    sums = {}
    for row in (entries.values('linked_event')
                .annotate(received=Sum('amount', filter=_EVENT_REVENUE),
                          costs=Sum('amount', filter=_EVENT_COST),
                          reserved=Sum('amount', filter=_EVENT_RESERVED),
                          passthrough=Sum('amount', filter=_EVENT_PASSTHROUGH),
                          entries=Count('pk'))):
        sums[row['linked_event']] = row

    event_ids = set(sums)
    if include_unlinked:
        from events.models import BaseEvent

        billed = BaseEvent.objects.filter(
            Q(billings__isnull=False) | Q(multibillings__isnull=False),
            cancelled=False, test_event=False)
        if fiscal_year:
            billed = billed.filter(datetime_start__date__range=(start, end))
        if since is not None:
            billed = billed.filter(datetime_start__date__gte=since)
        event_ids.update(billed.values_list('pk', flat=True))

    if not event_ids:
        return []

    cache = {}
    books_start = books_start_date()
    rows = [_event_figures(event, sums.get(event.pk, {}), cache, books_start)
            for event in _event_queryset().filter(pk__in=event_ids)]
    rows.sort(key=lambda r: (r['margin'], r['event'].datetime_start))
    return rows


def event_pnl_totals(rows):
    """ The figures summed across a set of rows, for the strip above the table. """
    totals = {key: sum((r[key] for r in rows), ZERO)
              for key in ('received', 'costs', 'reserved', 'margin', 'passthrough_cost',
                          'rentals_billed')}
    totals['billed'] = sum((r['billed'] for r in rows if r['billed'] is not None), ZERO)
    totals['events'] = len(rows)
    totals['losses'] = sum(1 for r in rows if 'loss' in r['flag_keys'])
    totals['owed'] = sum((r['owed'] for r in rows), ZERO)
    return totals


# ---------------------------------------------------------------------------
# Where the money comes from
#
# Three questions the revenue charts above do not answer: which kind of income
# it was (event billing, or one of SGA's three kinds of payment, or a gift);
# how much of event billing LNL actually kept once the gear it hired in for
# the show was paid for; and whether the clients paying are new.
# ---------------------------------------------------------------------------

#: The colour event billing is drawn in, wherever income is broken down.
EVENT_BILLING_COLOR = '#59A14F'


def revenue_by_source(fiscal_year=None, is_projection=None):
    """
    Income by kind, biggest first: event billing, then each non-event source.

    Money SGA took back -- a reimbursement it paid twice, reclaimed -- is
    netted off the source that repays funding requests, because it is that
    income being undone rather than anything LNL spent. The row says how much
    was netted, so the figure never hides a correction.
    """
    from finance.models import reimbursement_source

    entries = _scoped(ParsedTransaction.objects.all(), fiscal_year, is_projection)
    income = entries.revenue()

    rows = []
    event = income.filter(linked_event__isnull=False).aggregate(
        t=Sum('amount'), n=Count('pk'))
    if event['n']:
        rows.append({'key': 'event', 'label': 'Event billing', 'amount': money(event['t']),
                     'taken_back': ZERO, 'entries': event['n'], 'source': None})

    by_source = (income.filter(linked_event__isnull=True,
                               non_event_revenue_type__isnull=False)
                 .values('non_event_revenue_type', 'non_event_revenue_type__name',
                         'non_event_revenue_type__slug')
                 .annotate(t=Sum('amount'), n=Count('pk')))
    source_rows = {}
    for row in by_source:
        source_rows[row['non_event_revenue_type']] = {
            'key': row['non_event_revenue_type__slug'],
            'label': row['non_event_revenue_type__name'], 'amount': money(row['t']),
            'taken_back': ZERO, 'entries': row['n'],
            'source': row['non_event_revenue_type']}

    taken = entries.filter(amount__lt=0, refund_of__isnull=True,
                           funding_request__isnull=False).aggregate(t=Sum('amount'))['t']
    taken = -money(taken)
    if taken:
        repays = reimbursement_source()
        if repays is not None:
            target = source_rows.setdefault(repays.pk, {
                'key': repays.slug, 'label': repays.name, 'amount': ZERO,
                'taken_back': ZERO, 'entries': 0, 'source': repays.pk})
            target['amount'] -= taken
            target['taken_back'] += taken
        else:
            source_rows[None] = {'key': 'taken_back', 'label': 'Taken back by SGA',
                                 'amount': -taken, 'taken_back': taken, 'entries': 0,
                                 'source': None}
    rows.extend(source_rows.values())

    rows.sort(key=lambda r: -r['amount'])
    grand = sum((r['amount'] for r in rows if r['amount'] > 0), ZERO)
    biggest = max([r['amount'] for r in rows] + [ZERO])
    index = 0
    for row in rows:
        if row['key'] == 'event':
            row['color'] = EVENT_BILLING_COLOR
        else:
            row['color'] = series_color(index)
            index += 1
        row['percent'] = _percent(max(row['amount'], ZERO), grand)
        row['bar'] = _percent(max(row['amount'], ZERO), biggest)
    return rows


def event_billing_kept(fiscal_year=None, is_projection=None):
    """
    Event billing, and how much of it LNL kept after passing hired gear through.

    A show that hires a $26,000 video wall bills its client for it, and that
    money goes straight back out to the rental house. Counted as revenue it
    makes LNL look like a much bigger business than it is, so the dashboard
    sets every cost filed to the pass-through category against the billing.
    Costs filed there with no event still count: a missing link should not
    make a cost disappear from the figure.
    """
    entries = _scoped(ParsedTransaction.objects.all(), fiscal_year, is_projection)
    gross = money(entries.revenue().filter(linked_event__isnull=False)
                  .aggregate(t=Sum('amount'))['t'])
    passthrough = -money(entries.filter(_EVENT_PASSTHROUGH).aggregate(t=Sum('amount'))['t'])
    kept = gross - passthrough
    return {'gross': gross, 'passthrough': passthrough, 'kept': kept,
            'kept_percent': _percent(kept, gross) if gross > 0 else None}


def client_retention(fiscal_year=None, is_projection=None, rows=None, limit=5):
    """
    The clients who paid for events this year, split into new and returning.

    Returning means LNL worked a show for them in an earlier fiscal year --
    asked of the events app, which goes back much further than the ledger.
    ``None`` with no year selected: "new" means nothing across all of them.
    """
    from events.models import BaseEvent

    if not fiscal_year:
        return None
    rows = revenue_rows(fiscal_year, is_projection) if rows is None else rows
    clients = {}
    for row in rows:
        event = row['event']
        org = client_of(event) if event is not None else None
        if org is None:
            continue
        entry = clients.setdefault(org.pk, {'name': org.retname, 'amount': ZERO})
        entry['amount'] += row['amount']
    if not clients:
        return {'new': {'count': 0, 'amount': ZERO}, 'returning': {'count': 0, 'amount': ZERO},
                'new_clients': []}

    start, _ = fiscal_year_bounds(fiscal_year)
    earlier = set()
    previous = (BaseEvent.objects
                .filter(Q(billing_org__in=list(clients)) | Q(org__in=list(clients)),
                        datetime_start__date__lt=start, cancelled=False, test_event=False)
                .values_list('billing_org', 'org'))
    for billing_org, org in previous:
        earlier.update(pk for pk in (billing_org, org) if pk in clients)

    out = {'new': {'count': 0, 'amount': ZERO}, 'returning': {'count': 0, 'amount': ZERO}}
    for pk, entry in clients.items():
        bucket = out['returning'] if pk in earlier else out['new']
        bucket['count'] += 1
        bucket['amount'] += entry['amount']
    newcomers = sorted((entry for pk, entry in clients.items() if pk not in earlier),
                       key=lambda e: -e['amount'])
    out['new_clients'] = newcomers[:limit]
    return out


# ---------------------------------------------------------------------------
# What LNL is owed
#
# Two kinds of money LNL has earned and not yet been paid: SGA's reimbursement
# for funding-request spending, and clients' payment of their bills. Both are
# worked out from the ledger against lnldb's own records, never stored.
# ---------------------------------------------------------------------------

def sga_receivables(today=None, statement_=None):
    """
    Every funding request SGA still owes on, or has overpaid, oldest first.

    Returns ``{'rows', 'owed', 'overpaid', 'fund_owed', 'difference'}``. Each
    row is ``{'request', 'awaiting', 'since', 'days'}``, where ``since`` is the
    oldest charge SGA has not yet paid for.

    ``fund_owed`` is the same question asked of the balance page: how far below
    zero the funds that draw on requests are today. The two should agree, and
    ``difference`` is how far they do not -- usually an opening balance entered
    on one side only, or a write-off, which moves the fund and not the request.
    """
    from finance.balances import statement
    from finance.models import current_fiscal_year

    today = today or datetime.date.today()
    books_start = books_start_date()
    rows = []
    for request in FundingRequest.objects.with_totals().order_by('fiscal_year', 'reference'):
        awaiting = request.awaiting_sga
        if not awaiting:
            continue
        since = request.unreimbursed_since(books_start) if awaiting > 0 else None
        rows.append({'request': request, 'awaiting': awaiting, 'since': since,
                     'days': (today - since).days if since else None})
    rows.sort(key=lambda r: (r['awaiting'] <= 0, r['since'] or datetime.date.max))

    owed = sum((r['awaiting'] for r in rows if r['awaiting'] > 0), ZERO)
    overpaid = -sum((r['awaiting'] for r in rows if r['awaiting'] < 0), ZERO)

    year = statement_ or statement(current_fiscal_year(), today=today)
    fund_balance = ZERO
    for account in year.accounts:
        for row in account.rows:
            if (row.fund is not None and row.fund.requires_funding_request
                    and row.closing is not None):
                fund_balance += row.closing
    fund_owed = -fund_balance
    return {'rows': rows, 'owed': owed, 'overpaid': overpaid, 'fund_owed': fund_owed,
            'difference': (owed - overpaid) - fund_owed}


def billing_receivables(is_projection=None):
    """
    Events billed since the books started and not yet paid in full.

    Each row is an event P&L row (see :func:`event_pnl_rows`) with something
    still owed on it, longest-owed first. Events before the books start are
    left out: their payments, if any, were never imported.
    """
    since = books_start_date()
    rows = [row for row in event_pnl_rows(None, is_projection, include_unlinked=True,
                                          since=since)
            if row['owed'] > 0]
    rows.sort(key=lambda r: -(r['days_owed'] or 0))
    return rows


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def project_composition(fiscal_year=None, is_projection=None, limit=6):
    """
    Top-level projects as stacked bars, segmented by child asset.

    Answers "what did this programme cost, and which asset ate the budget?"
    in one read. Spending tagged straight to the parent shows as a "direct"
    segment so the bar total always matches the project's fully-loaded cost.
    """
    from finance.models import ProjectTag

    roots = ProjectTag.objects.filter(archived=False, parent__isnull=True)
    if is_projection is not None:
        roots = roots.filter(is_projection=is_projection)

    projects = []
    for root in roots:
        segments = []

        direct = root.total_cost(include_descendants=False, fiscal_year=fiscal_year)
        if direct:
            segments.append({'label': 'Direct', 'amount': direct})

        for child in root.get_children():
            amount = child.total_cost(fiscal_year=fiscal_year)
            if amount:
                segments.append({'label': child.name, 'amount': amount, 'code': child.code})

        total = sum((s['amount'] for s in segments), Decimal('0.00'))
        if total <= 0:
            continue

        segments.sort(key=lambda s: -s['amount'])
        for index, segment in enumerate(segments):
            segment['color'] = series_color(index)
            segment['percent'] = _percent(segment['amount'], total)

        projects.append({'node': root, 'label': root.name, 'code': root.code,
                         'total': total, 'segments': segments})

    projects.sort(key=lambda p: -p['total'])
    return projects[:limit]

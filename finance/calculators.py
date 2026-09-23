"""
Derived figures for the executive dashboard.

Everything here takes the same ``(fiscal_year, is_projection)`` pair the global
filter bar produces, so every widget on the page answers the same question for
the same slice of the ledger.
"""
import datetime
from collections import OrderedDict
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncMonth

from finance.models import (ClientType, ParsedTransaction, client_of, client_type_for,
                            fiscal_year_bounds, money, service_colors)

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

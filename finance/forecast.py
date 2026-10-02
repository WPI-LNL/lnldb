"""
Where LNL's money is heading: today's balances carried forward, month by month,
to the end of next fiscal year.

Worked out on every page load and never stored, like the balances it starts
from. Every projected movement says where it came from, so the forecast can be
checked line by line rather than taken on trust. There are six kinds, and each
can be switched off to see what it contributes:

* **Reserved purchases** -- encumbrances, on their dates.
* **Owed to LNL** -- what SGA still owes on each funding request, and what
  clients owe on their bills, paid after the wait the ledger shows is usual.
* **Booked events** -- approved shows still to come. A department's show
  brings in its quote and pays for the gear hired in for it. From FY27 a
  student organization's show brings in nothing: what its hired gear costs
  is spent from a funding request and paid back by SGA later, which only
  shows as the wait.
* **A typical year** -- what the most recent whole years did, month by month,
  for LNL's billing, the gear it hires in, and each category of running
  costs. See :class:`TypicalYear`.
* **Planned purchases** -- the Treasurer's list, and any "what if" being
  asked.
* **Year end** -- a budget's unspent balance going back to SGA on June 30.

Equipment is chosen, not incurred, so it is never projected from the past:
a category marked *forecast from plans only* counts only what is reserved or
planned. The forecast's answer to "how much can we spend?" is
:attr:`Forecast.room`.

The figure that matters is **LNL's own money**: the account's own fund
(Legacy) and anything not filed yet. A funding request's money is SGA's, and
running it down only makes LNL wait to be paid back, so it moves the cash but
never the verdict.
"""
import calendar
import datetime
import statistics
from collections import OrderedDict, defaultdict
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from finance import history
from finance.models import (DEPARTMENTS_ONLY_FROM, ZERO, ClientType, FundBehaviour, FundSource,
                            HistoryKind, ParsedTransaction, PartitionCode, PlannedPurchase,
                            TransactionStatus, client_type_for, current_fiscal_year,
                            finance_settings, fiscal_year_bounds, fiscal_year_for, money,
                            own_fund_for_account)

ONE_DAY = datetime.timedelta(days=1)

#: How many whole years make a typical year. The most recent ones: LNL's
#: billing nearly quadrupled between FY19 and FY26, and a median over every
#: year since would be the business it used to be.
TYPICAL_YEARS = 3

#: The waits assumed until the ledger has enough of its own to measure, and
#: how many it takes.
DEFAULT_SGA_DAYS = 30
DEFAULT_BILL_DAYS = 30
MEASURED_AFTER = 2

#: The account's own money: its own fund, plus anything not filed yet.
OWN = 'own'

#: The parts of a forecast, in the order the page lists them.
COMPONENTS = OrderedDict((
    ('reserved', "Reserved purchases"),
    ('owed', "Owed to LNL"),
    ('events', "Booked events"),
    ('typical', "A typical year"),
    ('planned', "Planned purchases"),
    ('year_end', "Year end"),
))

#: The parts of a typical year that are not spending categories.
BILLING, PASSTHROUGH = 'billing', 'passthrough'


# ---------------------------------------------------------------------------
# A typical year
# ---------------------------------------------------------------------------

def stream_for(flow, categories):
    """
    Which part of a typical year a flow belongs to, or ``None``.

    Billing; the gear hired in for shows (the category marked for costs billed
    to an event); and each running-cost category. Left out: SGA's money, which
    pays for particular things; transfers and gifts; spending SGA pays for;
    equipment and anything else forecast from plans; and lines the Treasurer
    left out.
    """
    if flow.left_out:
        return None
    if flow.kind == HistoryKind.BILLING:
        return BILLING
    if flow.kind != HistoryKind.SPENDING or flow.sga_paid:
        return None
    category = categories.get(flow.category)
    if category is not None and category.forecast_from_plans:
        return None
    if category is not None and category.is_event_passthrough:
        return PASSTHROUGH
    return ('category', flow.category)


def stream_label(stream, categories):
    """ A part of a typical year, in words. """
    if stream == BILLING:
        return "Billing"
    if stream == PASSTHROUGH:
        return "Gear hired in for shows"
    category = categories.get(stream[1])
    return category.name if category is not None else "Spending not worked out"


def _stream_order(stream, categories):
    """ Billing, then hired gear, then the categories in their admin order. """
    if stream == BILLING:
        return (0, 0, '')
    if stream == PASSTHROUGH:
        return (1, 0, '')
    category = categories.get(stream[1])
    if category is None:
        return (3, 0, '')
    return (2, category.sort_order, category.name)


def _median(values):
    """ The median of some money, as money. """
    return money(statistics.median(values)) if values else ZERO


class TypicalYear(object):
    """
    What a year looks like, month by month, from the most recent whole years.

    Each part of the year is the **median** of those years' totals, spread over
    the calendar the way those years spread it between them. The median, so
    one odd year -- a $15,000 chain-motor repair -- does not set the pattern;
    the spread, so orientation's billing lands in August and not a twelfth of
    it every month.

    From FY27 LNL bills departments only. A year from before that is scaled to
    the departments' share for billing and for the gear hired in for shows,
    when the forecast is for FY27 or later; with no share known those two
    parts are left out altogether rather than guessed at (see ``dropped``).
    """

    def __init__(self, flows, categories, target_year, whole_years, share=None,
                 count=TYPICAL_YEARS):
        self.target_year = target_year
        self.share = share
        self.categories = categories
        self.years = sorted(whole_years, reverse=True)[:count]
        self.dropped = set()
        self.scaled = False

        actual = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: ZERO)))
        for flow in flows:
            year = flow.fiscal_year
            if year not in self.years:
                continue
            stream = stream_for(flow, categories)
            if stream is not None:
                actual[stream][year][flow.day.month] += flow.amount

        for stream in (BILLING, PASSTHROUGH):
            if stream not in actual:
                continue
            for year in self.years:
                factor = self.factor(year)
                if factor is None:
                    self.dropped.add(stream)
                    break
                if factor != 1:
                    self.scaled = True
                    months = actual[stream][year]
                    for month in list(months):
                        months[month] = money(months[month] * factor)
        for stream in self.dropped:
            actual.pop(stream, None)

        #: ``{stream: {year: {calendar month: amount}}}``: what each year did.
        self.actual = actual
        #: ``{stream: typical year's total}``.
        self.annual = {}
        #: ``{stream: {calendar month: share of the year}}``.
        self.weights = {}
        for stream, by_year in actual.items():
            totals = [sum(by_year[year].values(), ZERO) for year in self.years]
            self.annual[stream] = _median(totals)
            pooled = sum(totals, ZERO)
            self.weights[stream] = (
                {month: sum((by_year[year].get(month, ZERO) for year in self.years), ZERO)
                 / pooled for month in range(1, 13)} if pooled else {})

    def factor(self, year):
        """
        What a year's billing is multiplied by to stand for a year in which
        only departments are billed: 1, the share, or ``None`` when it is
        needed and not known.
        """
        if year >= DEPARTMENTS_ONLY_FROM or self.target_year < DEPARTMENTS_ONLY_FROM:
            return Decimal(1)
        if self.share is not None and self.share.known:
            return self.share.share
        return None

    @property
    def streams(self):
        """ Every part of the year, in the order the page lists them. """
        return sorted(self.annual, key=lambda s: _stream_order(s, self.categories))

    def month(self, stream, month):
        """ What a typical year does in one calendar month. """
        weight = self.weights.get(stream, {}).get(month)
        if not weight:
            return ZERO
        return money(self.annual[stream] * weight)

    def in_year(self, stream, year, month):
        """ What ``year`` actually did in one calendar month. """
        return self.actual.get(stream, {}).get(year, {}).get(month, ZERO)

    def label(self, stream):
        """ A part of the year, in words. """
        return stream_label(stream, self.categories)

    @property
    def span(self):
        """ The years it is made from, as the page says them: "FY24-FY26". """
        if not self.years:
            return ''
        first, last = min(self.years), max(self.years)
        if first == last:
            return 'FY%s' % str(first)[-2:]
        return 'FY%s-FY%s' % (str(first)[-2:], str(last)[-2:])


# ---------------------------------------------------------------------------
# How long money takes
# ---------------------------------------------------------------------------

class Wait(object):
    """ A number of days money takes to arrive, and whether it was measured. """

    def __init__(self, days, measured, default):
        self.days = days
        self.measured = measured
        self.default = default

    @property
    def is_measured(self):
        """ Whether the ledger had enough cases to measure it. """
        return self.measured >= MEASURED_AFTER

    @property
    def how(self):
        """ Where the figure came from, in words. """
        if self.is_measured:
            return "the median of %s in the ledger" % self.measured
        return "assumed until the ledger has %s to measure" % MEASURED_AFTER

    def after(self, what):
        """ "30 days after the show (assumed until ...)": the wait in a sentence. """
        return "%s days after %s (%s)" % (self.days, what, self.how)


def sga_wait():
    """
    How long SGA takes to pay back a funding request: the median number of
    days from the last spending on a request before each of its payments.
    """
    spent = defaultdict(list)
    for request, day in (ParsedTransaction.objects
                         .filter(parent_transaction__isnull=False, amount__lt=0,
                                 fr_line_target__isnull=False)
                         .values_list('fr_line_target__funding_request_id',
                                      'parent_transaction__accounting_date')):
        spent[request].append(day)
    waits = []
    for request, day in (ParsedTransaction.objects
                         .filter(parent_transaction__isnull=False, amount__gt=0,
                                 funding_request__isnull=False)
                         .values_list('funding_request_id', 'parent_transaction__accounting_date')):
        before = [d for d in spent.get(request, []) if d <= day]
        if before:
            waits.append((day - max(before)).days)
    return _wait(waits, DEFAULT_SGA_DAYS)


def bill_wait():
    """ How long a client takes to pay: the median days from a show to its payment. """
    waits = []
    for start, day in (ParsedTransaction.objects
                       .filter(parent_transaction__isnull=False, amount__gt=0,
                               refund_of__isnull=True, linked_event__isnull=False)
                       .values_list('linked_event__datetime_start',
                                    'parent_transaction__accounting_date')):
        waits.append(max(0, (day - start.date()).days))
    return _wait(waits, DEFAULT_BILL_DAYS)


def _wait(waits, default):
    """ The median of some waits, or the default with too few to go on. """
    if len(waits) >= MEASURED_AFTER:
        return Wait(int(statistics.median(waits)), len(waits), default)
    return Wait(default, len(waits), default)


# ---------------------------------------------------------------------------
# The projection
# ---------------------------------------------------------------------------

class Item(object):
    """
    One projected movement of money: when, how much, which fund, and why.

    ``fund`` is :data:`OWN` or a fund's pk. ``stream`` is set on spending in a
    running-cost category, which a typical year already counts some of.
    """

    __slots__ = ('day', 'amount', 'fund', 'component', 'label', 'detail', 'url', 'stream',
                 'is_revenue_for_shows')

    def __init__(self, day, amount, fund, component, label, detail='', url='', stream=None,
                 is_revenue_for_shows=False):
        self.day = day
        self.amount = amount
        self.fund = fund
        self.component = component
        self.label = label
        self.detail = detail
        self.url = url
        self.stream = stream
        self.is_revenue_for_shows = is_revenue_for_shows

    @property
    def component_label(self):
        """ The part of the forecast it belongs to, in words. """
        return COMPONENTS[self.component]

    def __repr__(self):
        return "<Item %s %s %s %s>" % (self.day, self.amount, self.component, self.label)


class Month(object):
    """ One month of the forecast: what moves, and where each fund ends it. """

    def __init__(self, first, last, start):
        self.first = first
        self.last = last
        #: The first day of the month the forecast covers: later than
        #: ``first`` in the month the forecast starts in.
        self.start = start
        self.flows = defaultdict(lambda: ZERO)
        self.money_in = ZERO
        self.money_out = ZERO
        self.funds = {}
        self.own = ZERO
        self.cash = ZERO
        self.low = None
        self.high = None
        self.below_reserve = False

    @property
    def label(self):
        """ "Oct 2026". """
        return date_format(self.first, 'M Y')

    @property
    def fiscal_year(self):
        """ The fiscal year the month falls in. """
        return fiscal_year_for(self.first)

    @property
    def fraction(self):
        """ How much of the month is still to come. """
        days = (self.last - self.first).days + 1
        return Decimal((self.last - self.start).days + 1) / Decimal(days)

    @property
    def is_year_end(self):
        """ Whether the month ends a fiscal year. """
        return fiscal_year_for(self.last + ONE_DAY) != self.fiscal_year


class Forecast(object):
    """
    The forecast for one account, and everything the page says about it.

    ``available`` is false when it cannot be made, and ``problem`` says why --
    with no Workday balance entered, nobody knows what the account holds now.
    """

    def __init__(self, account, today):
        self.account = account
        self.today = today
        self.available = False
        self.problem = ''
        self.since = today
        self.horizon = fiscal_year_bounds(fiscal_year_for(today) + 1)[1]
        self.opening = {}
        self.fund_names = {}
        self.months = []
        self.items = []
        self.typical = None
        self.typical_rows = []
        self.share = None
        self.waits = {}
        self.reserve = money(finance_settings().minimum_reserve)
        self.without = set()
        self.scenarios = {}
        self.warnings = []
        self.notes = []
        self.events_booked = 0
        self.events_counted = 0
        self.actual = []

    # -- the headline figures ---------------------------------------------------
    @property
    def code(self):
        """ The account's code, e.g. 226-AG. """
        return self.account.code

    @property
    def opening_own(self):
        """ LNL's own money in this account now. """
        return self.opening.get(OWN, ZERO)

    @property
    def opening_cash(self):
        """ Everything in the account now, whoever it belongs to. """
        return sum(self.opening.values(), ZERO)

    @property
    def has_band(self):
        """
        Whether there are enough years to show a range: the lowest and highest
        LNL's own money would be if the rest of the forecast went like each of
        the years the typical year is made from.
        """
        return len(self.scenarios) >= 2

    @property
    def low_point(self):
        """ The month LNL's own money is lowest at the end of. """
        return min(self.months, key=lambda m: (m.own, m.last)) if self.months else None

    @property
    def lowest_in_band(self):
        """ The lowest the weakest of the past years would take LNL's own money. """
        lows = [m.low for m in self.months if m.low is not None]
        return min(lows) if lows else None

    @property
    def room(self):
        """
        How much more LNL could spend today and still never go below the
        reserve before the forecast ends. Spending now lowers every month after
        it, so it is the smallest gap between a month and the reserve.
        """
        if not self.months:
            return ZERO
        return min([self.opening_own] + [m.own for m in self.months]) - self.reserve

    @property
    def year_ends(self):
        """ Each June 30 in the forecast: ``[Month]``. """
        return [m for m in self.months if m.is_year_end]

    @property
    def months_below_reserve(self):
        """ The months LNL's own money ends below the reserve. """
        return [m for m in self.months if m.below_reserve]

    @property
    def verdict(self):
        """
        ``'yes'`` if LNL's own money stays above the reserve even if the year
        goes like the weakest recent one; ``'tight'`` if only a typical year
        keeps it there; ``'no'`` if not even that does.
        """
        if not self.months:
            return None
        if self.low_point.own < self.reserve:
            return 'no'
        if self.has_band and self.lowest_in_band < self.reserve:
            return 'tight'
        return 'yes'

    @property
    def components(self):
        """ ``[(key, label, included)]`` for every part, for the switches. """
        return [(key, label, key not in self.without) for key, label in COMPONENTS.items()]

    def items_in(self, component):
        """ The dated items of one part. """
        return [item for item in self.items if item.component == component]

    def totals_by_component(self):
        """ ``{component: total over the whole forecast}``. """
        out = OrderedDict((key, ZERO) for key in COMPONENTS)
        for month in self.months:
            for key, amount in month.flows.items():
                out[key] += amount
        return out

    def chart(self):
        """
        What the chart draws, as plain numbers: Workday's cash at the end of
        each of the last twelve months, then from the last line imported the
        forecast -- the account's cash, LNL's own money, and the range.
        """
        past = [None] * max(len(self.actual) - 1, 0)

        def ahead(values, now):
            return past + [now] + [None if v is None else float(v) for v in values]

        now_own = float(self.opening_own)
        return {
            'labels': [label for label, _ in self.actual[:-1]] + [
                "Now" if self.since == self.today
                else date_format(self.since, 'M j')] + [m.label for m in self.months],
            'actual': [float(v) for _, v in self.actual] + [None] * len(self.months),
            'cash': ahead([m.cash for m in self.months], float(self.opening_cash)),
            'own': ahead([m.own for m in self.months], now_own),
            'low': ahead([m.low for m in self.months], now_own) if self.has_band else [],
            'high': ahead([m.high for m in self.months], now_own) if self.has_band else [],
            'reserve': float(self.reserve),
        }


def _months(since, horizon):
    """ Every month from the one after ``since`` begins in to the horizon's. """
    out = []
    start = since + ONE_DAY
    first = start.replace(day=1)
    while first <= horizon:
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        out.append(Month(first, last, max(first, start)))
        first = last + ONE_DAY
    return out


def _after(day, since):
    """ A day in the forecast: ``day``, or the first day of it if that has passed. """
    return max(day, since + ONE_DAY)


class _Funds(object):
    """ Which fund key a fund on this account is, and which funds SGA repays. """

    def __init__(self, code):
        self.code = code
        own = own_fund_for_account(code)
        self.own_id = own.pk if own is not None else None
        self.funds = {fund.pk: fund for fund in FundSource.objects.select_related('account')}
        repaid = [fund for fund in self.funds.values()
                  if fund.behaviour == FundBehaviour.REIMBURSED and fund.is_active
                  and fund.account is not None and fund.account.code == code]
        self.repaid = repaid[0].pk if repaid else None

    def key(self, fund_id):
        """ The key a fund's money is kept under, or ``None`` if it is held elsewhere. """
        if fund_id is None or fund_id == self.own_id:
            return OWN
        fund = self.funds.get(fund_id)
        if fund is None or fund.account is None or fund.account.code != self.code:
            return None
        return fund_id

    def is_repaid(self, fund_id):
        """ Whether SGA pays this fund's spending back. """
        fund = self.funds.get(fund_id)
        return fund is not None and fund.behaviour == FundBehaviour.REIMBURSED


def _category_stream(category_id, categories):
    """ The typical-year part a dated purchase in a category stands in for. """
    category = categories.get(category_id)
    if category is None or category.forecast_from_plans or category.is_event_passthrough:
        return None
    return ('category', category_id)


def _spend(items, day, amount, fund_id, funds, component, label, detail, url, stream, wait):
    """
    Spending on a date, from whichever fund pays. Spending a funding request's
    money is paid back by SGA after ``wait``, so it comes with its repayment.
    """
    key = funds.key(fund_id)
    if key is None:
        return
    items.append(Item(day, -amount, key, component, label, detail, url,
                      stream=stream if key == OWN else None))
    if key != OWN and funds.is_repaid(fund_id):
        items.append(Item(day + datetime.timedelta(days=wait.days), amount, key, component,
                          "SGA paying back: %s" % label,
                          "SGA repays a funding request's spending %s"
                          % wait.after("it is spent"), url))


def _reserved(funds, since, horizon, categories, wait):
    """ Every encumbrance still waiting, on its date. """
    items = []
    entries = (ParsedTransaction.objects
               .filter(parent_transaction__isnull=True, status=TransactionStatus.PENDING)
               .select_related('fund_source', 'lnl_spend_category'))
    for entry in entries:
        if entry.effective_date > horizon or not entry.amount:
            continue
        amount = -money(entry.amount)
        day = _after(entry.effective_date, since)
        overdue = entry.effective_date <= since
        _spend(items, day, amount, entry.fund_source_id, funds, 'reserved',
               entry.description or "Reserved purchase",
               "Reserved for %s%s" % (date_format(entry.effective_date, 'M j, Y'),
                                      ", and still waiting" if overdue else ""),
               reverse('finance:entry-detail', args=[entry.pk]),
               _category_stream(entry.lnl_spend_category_id, categories), wait)
    return items


def _owed(funds, since, horizon, sga, bills, today, year=None):
    """ What SGA and clients owe, paid after the usual wait. """
    from finance.calculators import billing_receivables, sga_receivables

    items = []
    if funds.repaid is not None:
        for row in sga_receivables(today=today, statement_=year)['rows']:
            if row['awaiting'] <= 0:
                continue
            request = row['request']
            due = (row['since'] + datetime.timedelta(days=sga.days)) if row['since'] else since
            day = _after(due, since)
            if day > horizon:
                continue
            items.append(Item(
                day, money(row['awaiting']), funds.repaid, 'owed',
                "SGA paying %s" % (request.reference or request.name),
                "Owed since %s; SGA pays %s" % (
                    date_format(row['since'], 'M j, Y') if row['since'] else 'the books started',
                    sga.after("the spending")),
                request.get_absolute_url()))
    for row in billing_receivables(today=today):
        if not row['owed'] or funds.code != event_account_code():
            continue
        event = row['event']
        due = event.datetime_start.date() + datetime.timedelta(days=bills.days)
        day = _after(due, since)
        if day > horizon:
            continue
        items.append(Item(
            day, money(row['owed']), OWN, 'owed',
            "%s paying for %s" % (row['client'] or "The client", event.event_name),
            "Billed and not yet paid; clients pay %s" % bills.after("the show"),
            reverse('finance:ledger') + '?event=%s' % event.pk, is_revenue_for_shows=True))
    return items


def event_account_code():
    """ The account event production money goes through: the first that is not Projection. """
    account = PartitionCode.objects.filter(is_projection=False).order_by('code').first()
    return account.code if account is not None else None


def _rentals(event):
    """ What the gear hired in for an event costs. """
    return sum((money(rental.totalcost) for rental in event.rentals.all()), ZERO)


def _quote(event):
    """ What the events app would bill for an event, or nothing if it cannot say. """
    try:
        return max(money(event.cost_total), ZERO)
    except Exception:
        # A price the events app cannot work out is no price, not a crash.
        return ZERO


def _events(forecast, funds, since, horizon, sga, bills):
    """
    Approved shows still to come that nobody has billed yet.

    A department's show brings in what the events app quotes for it, and the
    gear hired in for it goes out on the day. From FY27 a student
    organization's show brings in nothing and its hired gear is a funding
    request's spending, repaid by SGA. A show whose client is not on file
    brings in nothing and pays for its gear itself, which is the cautious
    reading of not knowing.
    """
    from finance.calculators import _event_queryset, event_billed

    if funds.code != event_account_code():
        return []
    items = []
    events = (_event_queryset()
              .filter(approved=True, cancelled=False, test_event=False,
                      datetime_start__date__gt=since, datetime_start__date__lte=horizon)
              .order_by('datetime_start'))
    cache = {}
    for event in events:
        forecast.events_booked += 1
        if event_billed(event, cache)[0] is not None:
            # Billed already: what is owed on it is under "Owed to LNL".
            continue
        day = event.datetime_start.date()
        kind = client_type_for(event)
        rentals = _rentals(event)
        name = "%s (%s)" % (event.event_name, date_format(day, 'M j'))
        url = reverse('events:detail', args=[event.pk])
        counted = False
        if kind == ClientType.DEPARTMENT:
            quote = _quote(event)
            if quote:
                items.append(Item(
                    day + datetime.timedelta(days=bills.days), quote, OWN, 'events', name,
                    "A department's show, quoted %s; clients pay %s"
                    % (_dollars(quote), bills.after("the show")), url,
                    is_revenue_for_shows=True))
                counted = True
            if rentals:
                items.append(Item(day, -rentals, OWN, 'events', "Gear hired in: %s" % name,
                                  "Billed on to the department with the show", url,
                                  stream=PASSTHROUGH))
                counted = True
        elif rentals:
            counted = True
            if (kind == ClientType.STUDENT_ORG and fiscal_year_for(day) >= DEPARTMENTS_ONLY_FROM
                    and funds.repaid is not None):
                _spend(items, day, rentals, funds.repaid, funds, 'events',
                       "Gear hired in: %s" % name,
                       "A student organization's show: not billed, so its hired gear is spent "
                       "from a funding request", url, None, sga)
            else:
                items.append(Item(
                    day, -rentals, OWN, 'events', "Gear hired in: %s" % name,
                    "Nobody on file to bill for this show, so LNL pays for its gear" if
                    kind == ClientType.UNKNOWN else "Hired in for a student organization's show",
                    url, stream=PASSTHROUGH))
        if counted:
            forecast.events_counted += 1
    return items


def _planned(funds, since, horizon, categories, wait, saved=True, extra=()):
    """
    The Treasurer's planned purchases, unless ``saved`` is off, and any "what
    if" being asked, which is counted whatever the switches say.
    """
    items = []
    purchases = (list(PlannedPurchase.objects.filter(status__in=PlannedPurchase.COUNTED)
                      .select_related('fund_source', 'spend_category')) if saved else [])
    for purchase in purchases + list(extra):
        if purchase.expected_date > horizon:
            continue
        is_what_if = purchase.pk is None
        _spend(items, _after(purchase.expected_date, since), money(purchase.amount),
               purchase.fund_source_id, funds, 'planned',
               ("What if: %s" if is_what_if else "%s") % purchase.name,
               "%s for %s" % ("Asked about" if is_what_if else purchase.get_status_display(),
                              date_format(purchase.expected_date, 'M j, Y')),
               '' if is_what_if else reverse('finance:plan-edit', args=[purchase.pk]),
               _category_stream(purchase.spend_category_id, categories), wait)
    return items


def _dollars(amount):
    """ A whole-dollar figure for a sentence. """
    return '${:,.0f}'.format(amount)


def _typical_values(typical, stream, month, year=None):
    """
    What the typical year -- or one past ``year`` -- puts in a forecast month,
    for the part of the month still to come.
    """
    base = (typical.month(stream, month.first.month) if year is None
            else typical.in_year(stream, year, month.first.month))
    return money(base * month.fraction)


def _typical_items(forecast, typical, dated, year=None):
    """
    ``{month index: {stream: amount}}`` a typical year adds on top of what is
    dated, for the typical year or for one past ``year``.

    Two rules keep anything from counting twice:

    * **Billing and hired gear**: a month brings in whichever is more, what is
      dated for it -- booked shows and bills owed -- or what a typical month
      does; the typical month adds only the difference. Hired gear the same.
    * **Running costs**: a reserved or planned purchase in a category is part
      of that category's year, so the rest of that year is scaled down by it.
    """
    months = forecast.months
    booked = defaultdict(lambda: ZERO)
    hired = defaultdict(lambda: ZERO)
    committed = defaultdict(lambda: ZERO)
    index_of = {}
    for index, month in enumerate(months):
        index_of[(month.first.year, month.first.month)] = index
    for item in dated:
        index = index_of.get((item.day.year, item.day.month))
        if index is None or item.fund != OWN:
            continue
        if item.is_revenue_for_shows:
            booked[index] += item.amount
        elif item.stream == PASSTHROUGH:
            hired[index] += item.amount
        elif item.stream is not None:
            committed[(item.stream, fiscal_year_for(item.day))] += item.amount

    values = defaultdict(dict)
    for stream in typical.streams:
        raw = [_typical_values(typical, stream, month, year) for month in months]
        if stream == BILLING:
            raw = [max(ZERO, value - booked[i]) if value > 0 else value
                   for i, value in enumerate(raw)]
        elif stream == PASSTHROUGH:
            raw = [min(ZERO, value - hired[i]) if value < 0 else value
                   for i, value in enumerate(raw)]
        else:
            by_year = defaultdict(lambda: ZERO)
            for month, value in zip(months, raw):
                by_year[month.fiscal_year] += value
            for (committed_stream, fy), amount in committed.items():
                if committed_stream != stream or not by_year.get(fy):
                    continue
                remaining = by_year[fy]
                factor = max(ZERO, 1 - (amount / remaining)) if remaining < 0 else Decimal(1)
                raw = [money(value * factor) if month.fiscal_year == fy else value
                       for month, value in zip(months, raw)]
        for index, value in enumerate(raw):
            if value:
                values[index][stream] = value
    return values


def project(account=None, today=None, without=(), extra=(), ledger=None, books=None):
    """
    The forecast for one account -- the event account unless another is named
    -- from today to the end of next fiscal year.

    ``without`` names parts of the forecast to leave out (see
    :data:`COMPONENTS`); ``extra`` is purchases being asked about, as unsaved
    :class:`~finance.models.PlannedPurchase` objects.
    """
    from finance.balances import Books, statement

    today = today or timezone.localdate()
    if account is None:
        account = PartitionCode.objects.filter(code=event_account_code()).first()
    forecast = Forecast(account, today)
    forecast.without = set(without) & set(COMPONENTS)
    if account is None:
        forecast.problem = "No Workday account is set up."
        return forecast
    code = account.code
    books = books or Books()
    ledger = ledger or history.Ledger()

    year = statement(fiscal_year_for(today), books, today)
    statement_ = year.account(code)
    if statement_ is None or not statement_.cash_known:
        forecast.problem = (
            "Nobody has entered what Workday says %s holds, so there is nothing to carry "
            "forward. Enter a Workday balance on the Balances tab." % code)
        return forecast

    funds = _Funds(code)
    for row in statement_.rows:
        key = funds.key(row.fund.pk if row.fund is not None else None) or OWN
        forecast.opening[key] = forecast.opening.get(key, ZERO) + (row.closing or ZERO)
        forecast.fund_names[key] = (str(row.fund) if key != OWN and row.fund is not None
                                    else None)
    forecast.opening[OWN] = forecast.opening.get(OWN, ZERO) + statement_.unfiled_closing
    own = funds.funds.get(funds.own_id)
    forecast.fund_names[OWN] = "%s and anything not filed" % own if own else "Not filed"

    latest = max((day for day, _, line_code in books.lines.values()
                  if line_code == code and day <= today), default=None)
    forecast.since = min(latest, today) if latest is not None else today
    forecast.months = _months(forecast.since, forecast.horizon)
    forecast.available = True

    categories = history.spending_categories()
    sga, bills = sga_wait(), bill_wait()
    forecast.waits = {'sga': sga, 'bill': bills}

    # -- what is dated ------------------------------------------------------------
    dated = []
    if 'reserved' not in forecast.without:
        dated += _reserved(funds, forecast.since, forecast.horizon, categories, sga)
    if 'owed' not in forecast.without:
        dated += _owed(funds, forecast.since, forecast.horizon, sga, bills, today, year)
    if 'events' not in forecast.without:
        dated += _events(forecast, funds, forecast.since, forecast.horizon, sga, bills)
    dated += _planned(funds, forecast.since, forecast.horizon, categories, sga,
                      saved='planned' not in forecast.without, extra=extra)
    dated.sort(key=lambda item: (item.day, item.component, item.label))
    forecast.items = dated

    # -- a typical year -----------------------------------------------------------
    flows = ledger.for_account(code)
    forecast.share = history.department_share(ledger.flows)
    typical = TypicalYear(flows, categories, fiscal_year_for(today),
                          ledger.whole_years(code, before=fiscal_year_for(today)),
                          share=forecast.share)
    forecast.typical = typical
    use_typical = 'typical' not in forecast.without and typical.years
    typical_values = _typical_items(forecast, typical, dated) if use_typical else {}
    forecast.scenarios = ({year: _typical_items(forecast, typical, dated, year)
                           for year in typical.years} if use_typical else {})
    forecast.typical_rows = _typical_rows(forecast, typical, typical_values)

    # -- month by month -------------------------------------------------------------
    balances = dict(forecast.opening)
    by_month = defaultdict(list)
    for item in dated:
        by_month[(item.day.year, item.day.month)].append(item)
    scenario_own = {year: forecast.opening_own for year in forecast.scenarios}
    for index, month in enumerate(forecast.months):
        moving = list(by_month.get((month.first.year, month.first.month), []))
        for stream, amount in typical_values.get(index, {}).items():
            moving.append(Item(month.last, amount, OWN, 'typical', typical.label(stream),
                               stream=stream))
        if month.is_year_end and 'year_end' not in forecast.without:
            moving += _year_end(month, balances, moving, funds)
        for item in moving:
            balances[item.fund] = balances.get(item.fund, ZERO) + item.amount
            month.flows[item.component] += item.amount
            if item.amount > 0:
                month.money_in += item.amount
            else:
                month.money_out -= item.amount
        month.funds = dict(balances)
        month.own = balances.get(OWN, ZERO)
        month.cash = sum(balances.values(), ZERO)
        month.below_reserve = month.own < forecast.reserve
        for year, values in forecast.scenarios.items():
            scenario_own[year] += (sum(values.get(index, {}).values(), ZERO)
                                   + sum((item.amount for item in moving
                                          if item.fund == OWN and item.component != 'typical'),
                                         ZERO))
        if len(forecast.scenarios) >= 2:
            # The typical year is a median of each part separately, so it need
            # not fall between the years it came from; the range takes it in.
            paths = list(scenario_own.values()) + [month.own]
            month.low = min(paths)
            month.high = max(paths)
        forecast.items += [item for item in moving if item.component == 'year_end']

    forecast.actual = _actual_cash(books, code, forecast.since)
    _explain(forecast, typical)
    return forecast


def _year_end(month, balances, moving, funds):
    """
    June 30: a budget's unspent balance goes back to SGA. The money that
    carries forward, and a funding request still owed, stay as they are.
    """
    items = []
    for key, balance in balances.items():
        if key == OWN:
            continue
        fund = funds.funds.get(key)
        if fund is None or fund.behaviour != FundBehaviour.RETURNS:
            continue
        ending = balance + sum((item.amount for item in moving if item.fund == key), ZERO)
        if ending > 0:
            items.append(Item(month.last, -ending, key, 'year_end',
                              "Unspent %s goes back to SGA" % fund,
                              "A budget's unspent balance returns to SGA on June 30"))
    return items


def _typical_rows(forecast, typical, values):
    """
    ``[{'stream', 'label', 'annual', 'by_year': {fiscal year: amount}, 'past':
    {year: total}}]``: each part of a typical year, what it adds to each year
    of the forecast, and what the years it came from did.
    """
    rows = []
    for stream in typical.streams:
        by_year = defaultdict(lambda: ZERO)
        for index, month in enumerate(forecast.months):
            by_year[month.fiscal_year] += values.get(index, {}).get(stream, ZERO)
        rows.append({
            'stream': stream,
            'label': typical.label(stream),
            'annual': typical.annual[stream],
            'by_year': dict(by_year),
            'past': {year: sum(typical.actual[stream][year].values(), ZERO)
                     for year in typical.years},
        })
    return rows


def _actual_cash(books, code, since, months=12):
    """ ``[(label, cash)]`` at the end of each of the last ``months`` months. """
    out = []
    last = since.replace(day=1) - ONE_DAY
    for _ in range(months):
        cash = books.cash_on(code, last)
        if cash is None:
            break
        out.append((date_format(last, 'M Y'), cash))
        last = last.replace(day=1) - ONE_DAY
    out.reverse()
    if out:
        out.append(("Now", books.cash_on(code, since)))
    return out


def _explain(forecast, typical):
    """ The warnings and notes the page shows above and below the figures. """
    share = forecast.share
    if typical.dropped and 'typical' not in forecast.without:
        forecast.warnings.append(
            "Billing is left out of the typical year, and so is the gear hired in for shows. "
            "Until FY27 LNL billed student organizations too, and nothing yet says how much of "
            "that came from departments: %s. Set the departments' share in Finance "
            "Configuration, or file FY26's billing against its events, and the forecast will "
            "count it. Until then it shows LNL's running costs with only booked shows "
            "bringing anything in." % share.detail)
    elif typical.scaled:
        forecast.notes.append(
            "Billing before FY27, and the gear hired in for it, count at %s%%: the departments' "
            "share, %s." % (share.percent,
                            "as set in Finance Configuration" if share.source == 'set'
                            else "since %s" % share.detail))
    if not typical.years and 'typical' not in forecast.without:
        forecast.warnings.append(
            "There is not a whole year of lines on %s yet, so there is no typical year to go "
            "on. Import older Workday exports to give the forecast one." % forecast.code)
    elif len(typical.years) < 2:
        forecast.notes.append("Only one whole year is on file, so there is no range to show.")
    if typical.years:
        forecast.notes.append(
            "A typical year is the median of %s, spread over the months as those years spread "
            "it. No growth is assumed: next year looks like a typical recent one."
            % typical.span)
    forecast.notes.append(
        "Equipment is never projected from past years. Only what is reserved or on the "
        "planned purchases list counts.")
    if forecast.since < forecast.today:
        forecast.notes.append(
            "Workday lines are imported up to %s; the forecast takes over from the day after."
            % date_format(forecast.since, 'M j, Y'))


# ---------------------------------------------------------------------------
# How well a typical year would have done
# ---------------------------------------------------------------------------

def _same_day(day, year):
    """ ``day`` moved to the fiscal year ``year``, Feb 29 becoming Feb 28. """
    shift = year - fiscal_year_for(day)
    try:
        return day.replace(year=day.year + shift)
    except ValueError:
        return day.replace(year=day.year + shift, day=28)


def back_test(ledger, code, today=None, count=TYPICAL_YEARS, share=None):
    """
    What a typical year, made only from the years before, would have said
    about the rest of each past year -- beside what that year actually did.

    Asked on the same day of the year as today, of every whole year with at
    least two whole years before it. The typical year alone is tested:
    nothing was booked or reserved in the past to add to it. Before FY27 every
    client was billed, so nothing is scaled; a part the typical year has to
    leave out (see :attr:`TypicalYear.dropped`) is left out of what the year
    did too.

    ``[{'year', 'as_of', 'predicted', 'actual', 'difference', 'from'}]``.
    """
    today = today or timezone.localdate()
    categories = history.spending_categories()
    flows = ledger.for_account(code)
    whole = ledger.whole_years(code, before=fiscal_year_for(today))
    rows = []
    for year in sorted(whole):
        prior = [y for y in whole if y < year]
        if len(prior) < 2:
            continue
        as_of = _same_day(today, year)
        last = fiscal_year_bounds(year)[1]
        typical = TypicalYear(flows, categories, year, prior, share=share, count=count)
        predicted = ZERO
        for month in _months(as_of, last):
            for stream in typical.streams:
                predicted += _typical_values(typical, stream, month)
        actual = sum((flow.amount for flow in flows
                      if as_of < flow.day <= last
                      and stream_for(flow, categories) not in (None,) + tuple(typical.dropped)),
                     ZERO)
        rows.append({'year': year, 'as_of': as_of, 'predicted': predicted, 'actual': actual,
                     'difference': predicted - actual, 'from': typical.span})
    return rows


def back_test_summary(rows):
    """ The typical miss, in dollars and as a share of the typical year's swing. """
    if not rows:
        return None
    misses = [abs(row['difference']) for row in rows]
    swings = [abs(row['actual']) for row in rows]
    miss = _median(misses)
    swing = _median(swings)
    return {'miss': miss,
            'percent': int((miss / swing * 100).quantize(Decimal('1'))) if swing else None,
            'years': len(rows)}


def current_year():
    """ The fiscal year a forecast made today starts in. """
    return current_fiscal_year()

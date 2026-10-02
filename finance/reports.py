"""
Reports: the subledger's figures laid out to print, hand over, and open in a
spreadsheet.

Every report here is a pure function returning a :class:`Report` -- a title,
the period it covers, a few headline figures, one or more tables, and the
notes a reader needs before trusting them. Nothing here renders or responds:
one template draws every report and :func:`as_csv` writes any of them out, so
a new report is a function and nothing else, and the printed page and the
download cannot disagree about a figure.

The figures come from the same places the rest of the app takes them:
:mod:`finance.balances` for what each fund holds, :mod:`finance.calculators`
for events and what LNL is owed. The one report that groups the ledger itself,
:func:`income_and_spending`, does so by the rules the dashboard uses: income
is money in that is not a refund, spending is net of refunds, and money SGA
took back undoes a reimbursement rather than being spent.
"""
import csv
import datetime
import io
import statistics
from collections import OrderedDict, defaultdict
from decimal import ROUND_CEILING, Decimal

from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from finance import activity, balances, history
from finance.calculators import (_percent, billing_receivables, event_pnl_rows,
                                 event_pnl_totals, sga_receivables)
from finance.models import (ZERO, ClientType, FiscalYearClose, FundBehaviour, ParsedTransaction,
                            RevenueSource, SpendCategory, WorkdayTransaction, books_start_date,
                            client_type_for, fiscal_year_bounds, fiscal_year_for, money,
                            reimbursement_source)


# ---------------------------------------------------------------------------
# What a report is
# ---------------------------------------------------------------------------

class Column(object):
    """
    One column of a report's tables: the key its cells are stored under, its
    heading, and what kind of value it holds, which decides how the value is
    drawn on the page and written to the CSV.

    ``signed`` money is a change, drawn with a plus sign when it is one.
    ``coloured`` money is green above zero and red below -- right for a
    margin, wrong for a change in spending, where more is not better.
    """

    MONEY, TEXT, DATE, PERCENT, NUMBER = 'money', 'text', 'date', 'percent', 'number'

    def __init__(self, key, label, kind=TEXT, title='', signed=False, coloured=False):
        self.key = key
        self.label = label
        self.kind = kind
        self.title = title
        self.signed = signed
        self.coloured = coloured

    @property
    def is_numeric(self):
        """ Right-aligned on the page. """
        return self.kind in (self.MONEY, self.PERCENT, self.NUMBER)


class Row(object):
    """
    One line of a table.

    ``cells`` maps column keys to values, and a key left out is a blank cell
    rather than a zero. ``url`` links one cell -- the first, or the column
    ``link`` names -- and ``note`` is a muted line beneath it; neither reaches
    the CSV, which carries figures only.
    """

    def __init__(self, cells, url=None, note='', tone='', link=None):
        self.cells = cells
        self.url = url
        self.note = note
        self.tone = tone
        self.link = link

    def values(self, columns):
        """ The row's cells in column order. """
        return [self.cells.get(column.key) for column in columns]


class Section(object):
    """
    A table under a heading, with an optional total line. ``columns`` gives it
    columns of its own; without them it has the report's.
    """

    def __init__(self, title, rows, total=None, empty='', columns=None):
        self.title = title
        self.rows = rows
        self.total = total
        self.empty = empty
        self.columns = columns


class Stat(object):
    """ A headline figure above the tables. """

    def __init__(self, label, value, sub='', kind=Column.MONEY, tone=''):
        self.label = label
        self.value = value
        self.sub = sub
        self.kind = kind
        self.tone = tone


class Report(object):
    """
    A finished report: everything the page and the CSV need, and nothing else.

    ``period`` is the words for what the report covers ("FY27 to date"), and
    ``dates`` the dates themselves; ``file_part`` is the same thing as it goes
    into a file name. ``warnings`` are things that make a figure incomplete;
    ``notes`` say how the figures were reached.
    """

    def __init__(self, slug, title, period, dates, file_part, columns, sections, stats=(),
                 notes=(), warnings=()):
        self.slug = slug
        self.title = title
        self.period = period
        self.dates = dates
        self.file_part = file_part
        self.columns = columns
        self.sections = sections
        self.stats = list(stats)
        self.notes = list(notes)
        self.warnings = list(warnings)
        # What the template walks: each row beside its cells, column by column.
        for section in sections:
            section.columns = section.columns or columns
            own = section.columns
            for row in section.rows:
                row.link = row.link or (own[0].key if own else None)
            section.lines = [(row, list(zip(own, row.values(own)))) for row in section.rows]
            section.total_cells = (list(zip(own, section.total.values(own)))
                                   if section.total is not None else None)

    @property
    def filename(self):
        """ The download's file name, e.g. ``lnl-income-and-spending-fy27.csv``. """
        return 'lnl-%s-%s.csv' % (self.slug, self.file_part)


# ---------------------------------------------------------------------------
# The CSV
# ---------------------------------------------------------------------------

def _csv_value(column, value):
    """
    A cell as a spreadsheet wants it: plain numbers with a minus sign, ISO
    dates, and nothing at all for a blank, so a column of figures sums.
    """
    if value is None or value == '':
        return ''
    if column.kind == Column.MONEY:
        return '%.2f' % money(value)
    if column.kind == Column.DATE:
        return value.isoformat()
    return str(value)


def as_csv(report):
    """
    The report's tables as CSV text, one header row and one line per row.

    A report with more than one table gets a first column naming the table
    each line is from, so the whole thing still filters and pivots as one
    sheet. Tables with columns of their own cannot share a header, so each is
    written as a block instead: its title, its header and its rows, then a
    blank line. It starts with a byte-order mark: without one Excel reads the
    file as Windows-1252 and an en dash in a name arrives as three characters.
    """
    out = io.StringIO()
    out.write('\ufeff')
    writer = csv.writer(out)

    def lines(section):
        rows = list(section.rows) + ([section.total] if section.total is not None else [])
        columns = section.columns or report.columns
        return [[_csv_value(c, v) for c, v in zip(columns, row.values(columns))]
                for row in rows]

    if any((section.columns or report.columns) is not report.columns
           for section in report.sections):
        for section in report.sections:
            writer.writerow([section.title])
            writer.writerow([c.label for c in (section.columns or report.columns)])
            writer.writerows(lines(section))
            writer.writerow([])
        return out.getvalue()

    several = len(report.sections) > 1
    writer.writerow((['Section'] if several else []) + [c.label for c in report.columns])
    for section in report.sections:
        for cells in lines(section):
            writer.writerow(([section.title] if several else []) + cells)
    return out.getvalue()


# ---------------------------------------------------------------------------
# The stretch of time a report covers
# ---------------------------------------------------------------------------

def _short(fiscal_year):
    """ ``2027`` as ``FY27``. """
    return 'FY%02d' % (fiscal_year % 100)


def _day(value):
    """ A date as the app writes it everywhere else. """
    return date_format(value, 'M j, Y')


def _year_back(value):
    """ The same day a year earlier; February 29 becomes the 28th. """
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


class Period(object):
    """
    The days a report covers: a fiscal year, the part of one so far, a range of
    dates, or every year (``first`` and ``last`` both ``None``).

    ``name`` overrides the words for it -- "FY26, same dates" reads better
    than the bare dates in a comparison column.
    """

    def __init__(self, first=None, last=None, fiscal_year=None, to_date=False, name=None):
        self.first = first
        self.last = last
        self.fiscal_year = fiscal_year
        self.to_date = to_date
        self.name = name

    @classmethod
    def for_fiscal_year(cls, fiscal_year, today=None):
        """ A fiscal year, cut off at today while it is still running. """
        first, last = fiscal_year_bounds(fiscal_year)
        today = today or timezone.localdate()
        if first <= today < last:
            return cls(first, today, fiscal_year, to_date=True)
        return cls(first, last, fiscal_year)

    @property
    def is_bounded(self):
        """ Whether the period has dates at all. """
        return self.first is not None

    @property
    def label(self):
        """ What the period is called on the page. """
        if self.name:
            return self.name
        if self.fiscal_year:
            return '%s to date' % _short(self.fiscal_year) if self.to_date \
                else _short(self.fiscal_year)
        if not self.is_bounded:
            return 'All years'
        return self.dates

    @property
    def dates(self):
        """ The first and last day, or nothing for every year. """
        if not self.is_bounded:
            return ''
        return '%s – %s' % (_day(self.first), _day(self.last))

    @property
    def file_part(self):
        """ The period as it goes into a file name. """
        if self.fiscal_year and not self.name:
            return _short(self.fiscal_year).lower() + ('-to-date' if self.to_date else '')
        if not self.is_bounded:
            return 'all-years'
        return '%s-to-%s' % (self.first.isoformat(), self.last.isoformat())

    def year_earlier(self):
        """
        The same dates a year before, to compare against, or ``None`` when the
        period has no dates or is too long for a year back to mean anything.
        """
        if not self.is_bounded or (self.last - self.first).days > 366:
            return None
        first, last = _year_back(self.first), _year_back(self.last)
        if self.fiscal_year and not self.to_date:
            return Period(first, last, self.fiscal_year - 1)
        if self.fiscal_year:
            return Period(first, last, self.fiscal_year - 1,
                          name='%s, same dates' % _short(self.fiscal_year - 1))
        return Period(first, last)

    def previous_full_year(self):
        """ For a fiscal year still running, the whole of the one before. """
        if not (self.fiscal_year and self.to_date):
            return None
        first, last = fiscal_year_bounds(self.fiscal_year - 1)
        return Period(first, last, self.fiscal_year - 1,
                      name='%s in full' % _short(self.fiscal_year - 1))


def parse_period(fiscal_year, raw_from='', raw_to='', today=None):
    """
    The period a request asks for, and an error to show if it asked badly.

    ``from`` and ``to`` (``YYYY-MM-DD``) give any range and win over the
    fiscal year; with neither, it is the fiscal year, and with no fiscal year
    it is every year. A range given wrongly falls back to the fiscal year and
    says why, rather than quietly reporting something nobody asked for.
    """
    raw_from, raw_to = (raw_from or '').strip(), (raw_to or '').strip()
    error = ''
    if raw_from or raw_to:
        try:
            first = datetime.date.fromisoformat(raw_from)
            last = datetime.date.fromisoformat(raw_to)
        except ValueError:
            error = "Give both dates, as YYYY-MM-DD, to report on a range of dates."
        else:
            if first <= last:
                return Period(first, last), ''
            error = "The first date comes after the last, so the range is empty."
    if fiscal_year:
        return Period.for_fiscal_year(fiscal_year, today), error
    return Period(), error


def _partition_words(is_projection):
    """ How the partition filter reads in a report's notes. """
    if is_projection is None:
        return ''
    return 'Projection only.' if is_projection else 'Event Production only.'


# ---------------------------------------------------------------------------
# Income and spending, year over year
# ---------------------------------------------------------------------------

#: The three kinds of event billing, in the order they are listed.
EVENT_BILLING_LINES = (
    (ClientType.DEPARTMENT, 'Event billing: departments'),
    (ClientType.STUDENT_ORG, 'Event billing: student organizations'),
    (ClientType.UNKNOWN, 'Event billing: client not on file'),
)


def _filed(period, is_projection=None, fund=None):
    """
    Slices of bank lines in the period: money that has actually moved.
    Encumbrances are left out, because nothing has been spent yet.
    """
    entries = ParsedTransaction.objects.filter(parent_transaction__isnull=False)
    if period.is_bounded:
        entries = entries.filter(effective_date__range=(period.first, period.last))
    if is_projection is not None:
        entries = entries.filter(is_projection=is_projection)
    if fund is not None:
        entries = entries.filter(fund_source=fund)
    return entries


def _money_in(entries):
    """
    ``({line key: amount}, taken back)`` for the money that came in.

    Event billing is split by who paid, which is the events app's answer, not
    the ledger's. Money SGA took back is netted off the source that repays
    funding requests: it is that income undone, not spending.
    """
    from events.models import BaseEvent

    out = defaultdict(lambda: ZERO)
    income = entries.filter(amount__gt=0, refund_of__isnull=True)

    by_event = {row['linked_event']: money(row['t']) for row in
                income.filter(linked_event__isnull=False)
                .values('linked_event').annotate(t=Sum('amount'))}
    found = set()
    for event in (BaseEvent.objects.filter(pk__in=list(by_event))
                  .select_related('billing_org').prefetch_related('org')):
        out[('event', client_type_for(event))] += by_event[event.pk]
        found.add(event.pk)
    for pk, amount in by_event.items():
        if pk not in found:
            out[('event', ClientType.UNKNOWN)] += amount

    for row in (income.filter(linked_event__isnull=True)
                .values('non_event_revenue_type').annotate(t=Sum('amount'))):
        out[('source', row['non_event_revenue_type'])] += money(row['t'])

    taken = -money(entries.filter(Q(amount__lt=0) | Q(refund_of__isnull=False),
                                  funding_request__isnull=False)
                   .aggregate(t=Sum('amount'))['t'])
    if taken:
        repays = reimbursement_source()
        out[('source', repays.pk if repays is not None else 'taken_back')] -= taken
    return out, taken


def _money_out(entries):
    """
    ``{line key: amount}`` spent, by spend category, net of refunds. SGA's
    reclaiming money is not here; see :func:`_money_in`.
    """
    out = defaultdict(lambda: ZERO)
    for row in (entries.filter(Q(amount__lt=0) | Q(refund_of__isnull=False),
                               funding_request__isnull=True)
                .values('lnl_spend_category').annotate(t=Sum('amount'))):
        out[('category', row['lnl_spend_category'])] -= money(row['t'])
    return out


def _income_lines():
    """ ``[(key, label)]`` for every line money in can have, in order. """
    lines = [(('event', kind), label) for kind, label in EVENT_BILLING_LINES]
    lines += [(('source', source.pk), source.name)
              for source in RevenueSource.objects.order_by('sort_order', 'name')]
    lines += [(('source', 'taken_back'), 'Taken back by SGA'),
              (('source', None), 'Other income, no source named')]
    return lines


def _spending_lines():
    """ ``[(key, label)]`` for every line money out can have, in order. """
    lines = [(('category', category.pk), category.name)
             for category in SpendCategory.objects.order_by('sort_order', 'name')]
    return lines + [(('category', None), 'No spend category')]


def _unfiled(period, is_projection=None):
    """
    ``(lines, amount)`` of bank lines in the period that are not fully filed:
    how many, and the net of what is left to file on them.
    """
    from finance.filters import PARTITION_EVENT, PARTITION_PROJECTION, FilterState

    lines = WorkdayTransaction.objects.in_ledger()
    if period.is_bounded:
        lines = lines.filter(accounting_date__range=(period.first, period.last))
    if is_projection is not None:
        partition = PARTITION_PROJECTION if is_projection else PARTITION_EVENT
        lines = FilterState(None, partition).apply_to_workday(lines)
    count, amount = 0, ZERO
    filed_lines = lines.annotate(filed=Sum('slices__amount'))
    for net, filed in filed_lines.values_list('net_amount', 'filed'):
        left = money(net) - money(filed)
        if left:
            count += 1
            amount += left
    return count, amount


def income_and_spending(period, is_projection=None, fund=None):
    """
    What came in and what went out over the period, set beside the same dates
    a year earlier -- and, while a year is still running, beside the whole of
    the last one, which is what a budget for next year would start from.
    """
    start = books_start_date()
    earlier = period.year_earlier()
    full = period.previous_full_year()
    # A comparison wholly before the books start would be a column of zeros
    # and a "change" equal to this year: worse than no comparison at all.
    skipped = [stretch for stretch in (earlier, full)
               if stretch is not None and start is not None and stretch.last < start]
    if earlier in skipped:
        earlier = None
    if full in skipped:
        full = None
    periods = [('current', period)]
    if earlier is not None:
        periods.append(('earlier', earlier))
    if full is not None:
        periods.append(('full', full))

    figures = {}
    taken_back = ZERO
    for key, stretch in periods:
        entries = _filed(stretch, is_projection, fund)
        money_in, taken = _money_in(entries)
        figures[key] = (money_in, _money_out(entries))
        if key == 'current':
            taken_back = taken

    columns = [Column('line', 'Line'), Column('current', period.label, Column.MONEY)]
    if earlier is not None:
        columns += [Column('earlier', earlier.label, Column.MONEY),
                    Column('change', 'Change', Column.MONEY, signed=True,
                           title="This period less the same dates a year earlier")]
    if full is not None:
        columns.append(Column('full', full.label, Column.MONEY))

    def section(title, lines, side, total_label):
        rows = []
        totals = defaultdict(lambda: ZERO)
        for line_key, label in lines:
            cells = {'line': label}
            for key, _ in periods:
                cells[key] = figures[key][side].get(line_key, ZERO)
                totals[key] += cells[key]
            if not any(cells[key] for key, _ in periods):
                continue
            if earlier is not None:
                cells['change'] = cells['current'] - cells['earlier']
            rows.append(Row(cells))
        total = {'line': total_label}
        total.update(totals)
        for key, _ in periods:
            total.setdefault(key, ZERO)
        if earlier is not None:
            total['change'] = total['current'] - total['earlier']
        return Section(title, rows, Row(total), empty="Nothing in this period.")

    money_in = section('Money in', _income_lines(), 0, 'Total money in')
    money_out = section('Money out', _spending_lines(), 1, 'Total money out')
    net = {'line': 'Money in less money out'}
    for key in [k for k, _ in periods] + (['change'] if earlier is not None else []):
        net[key] = money_in.total.cells[key] - money_out.total.cells[key]
    sections = [money_in, money_out, Section('Net', [], Row(net))]

    def compared(cells):
        """ The same figure a year earlier, as the line under a headline. """
        if earlier is None:
            return ''
        return '%s for %s' % (_dollars(cells['earlier']), earlier.label)

    stats = [
        Stat('Money in', money_in.total.cells['current'], compared(money_in.total.cells),
             tone='text-success'),
        Stat('Money out', money_out.total.cells['current'], compared(money_out.total.cells),
             tone='text-danger'),
        Stat('Net', net['current'], compared(net),
             tone='text-success' if net['current'] >= 0 else 'text-danger'),
    ]

    notes = ["Money in is income filed in the ledger: event billing, split by who was "
             "billed, and each other source. Money out is spending that has reached "
             "Workday, net of refunds, by spend category. Reserved money that has not "
             "been charged yet is not counted.",
             "Each entry counts on its own date, so an event billed after it ran counts "
             "when the money arrived."]
    if taken_back:
        notes.append("Money in is after %s SGA took back, which undoes a reimbursement "
                     "rather than being spending." % _dollars(taken_back))
    if fund is not None:
        notes.append("Only money filed to %s." % fund.name)
    if _partition_words(is_projection):
        notes.append(_partition_words(is_projection))

    warnings = []
    count, left = _unfiled(period, is_projection)
    if count:
        warnings.append("%s Workday line%s from these dates %s still not fully filed (%s "
                        "net), so %s not counted here yet."
                        % (count, '' if count == 1 else 's', 'is' if count == 1 else 'are',
                           _dollars(left), 'it is' if count == 1 else 'they are'))
    if start is not None:
        for _, stretch in periods[1:]:
            if stretch.is_bounded and stretch.first < start:
                warnings.append("The ledger starts on %s, so the %s column has nothing "
                                "from before then." % (_day(start), stretch.label))
    if skipped:
        notes.append("Nothing is compared with %s: the ledger starts on %s, after it ended."
                     % (' or '.join(stretch.label for stretch in skipped), _day(start)))

    return Report('income-and-spending', 'Income and spending', period.label, period.dates,
                  period.file_part + (('-' + fund.slug) if fund is not None else ''),
                  columns, sections, stats, notes, warnings)


def _dollars(value):
    """ A figure as words in a sentence, e.g. ``$1,250.00``. """
    from django.contrib.humanize.templatetags.humanize import intcomma

    value = money(value)
    body = intcomma('%.2f' % abs(value))
    return ('-$%s' if value < 0 else '$%s') % body


# ---------------------------------------------------------------------------
# Fund balances
# ---------------------------------------------------------------------------

def fund_balances(fiscal_year, today=None):
    """
    What each fund in each account held at the start and end of the year, what
    moved, and what it means: the balance page, laid out to hand over.
    """
    today = today or timezone.localdate()
    year = balances.statement(fiscal_year, today=today)
    period = Period(year.first, year.last, fiscal_year, to_date=not year.year_over)

    columns = [
        Column('fund', 'Fund'),
        Column('kind', 'How it works'),
        Column('opening', 'Opening', Column.MONEY),
        Column('received', 'Money in', Column.MONEY),
        Column('spent', 'Money out', Column.MONEY, title="Net of refunds"),
        Column('transferred', 'Transfers', Column.MONEY, signed=True),
        Column('closing', 'Closing', Column.MONEY),
        Column('reserved', 'Reserved', Column.MONEY,
               title="Encumbered for purchases not yet charged"),
        Column('available', 'Available', Column.MONEY, title="Closing less reserved"),
        Column('status', 'What it means'),
    ]

    sections, stats, notes, warnings = [], [], [], []
    carries = unspent = awaiting = ZERO
    for account in year.accounts:
        rows = []
        for row in account.rows:
            rows.append(Row({
                'fund': row.name,
                'kind': row.fund.get_behaviour_display() if row.fund is not None else '',
                'opening': row.opening,
                'received': row.received,
                'spent': row.spent,
                'transferred': row.transferred,
                'closing': row.closing,
                'reserved': row.encumbered,
                'available': row.available,
                'status': row.status,
            }, note="the account's own money" if row.is_own else ''))
            if row.closing is None:
                continue
            if row.behaviour == FundBehaviour.CARRIES:
                carries += row.closing
            elif row.behaviour == FundBehaviour.RETURNS and row.closing > 0:
                unspent += row.closing
            elif row.behaviour == FundBehaviour.REIMBURSED and row.closing < 0:
                awaiting -= row.closing
        if account.unfiled_closing:
            warnings.append("%s of %s's lines (net) are still in the queue. Until they are "
                            "filed, the funds they belong to are short or over by that much; "
                            "the account total is right." % (_dollars(account.unfiled_closing),
                                                             account.code))
        if account.unfiled_opening or account.unfiled_closing:
            rows.append(Row({'fund': 'Not yet filed', 'opening': account.unfiled_opening,
                             'closing': account.unfiled_closing,
                             'status': 'Lines still in the queue'}, tone='muted'))
        reserved = sum((row.encumbered for row in account.rows), ZERO)
        total = Row({
            'fund': 'Account total',
            'opening': account.opening_cash,
            'received': sum((row.received for row in account.rows), ZERO),
            'spent': sum((row.spent for row in account.rows), ZERO),
            'transferred': sum((row.transferred for row in account.rows), ZERO),
            'closing': account.closing_cash,
            'reserved': reserved,
            'available': (account.closing_cash - reserved) if account.cash_known else None,
            'status': 'What Workday holds' if account.cash_known
                      else 'Enter a Workday balance to see this',
        })
        side = 'Projection' if account.account.is_projection else 'Event Production'
        sections.append(Section('%s: %s account' % (account.code, side), rows, total))

        if account.cash_known:
            stats.append(Stat('%s cash' % account.code, account.closing_cash,
                              'on %s' % _day(account.last)))
        else:
            warnings.append("No Workday balance has been entered for %s, so its own fund's "
                            "opening and closing, and the account total, are unknown. Its "
                            "movements are still right." % account.code)
        for checkpoint in account.checkpoints:
            said = money(checkpoint.checkpoint.balance)
            if checkpoint.difference:
                warnings.append("%s: Workday said %s on %s, but the ledger makes it %s -- %s "
                                "apart. Lines are missing or were imported twice."
                                % (account.code, _dollars(said),
                                   _day(checkpoint.checkpoint.as_of),
                                   _dollars(checkpoint.computed),
                                   _dollars(abs(checkpoint.difference))))
            else:
                notes.append("%s: Workday said %s on %s, and the ledger agrees."
                             % (account.code, _dollars(said), _day(checkpoint.checkpoint.as_of)))
        if account.out_of_balance:
            warnings.append("%s's funds add up to %s less than its cash. That should never "
                            "happen; report it." % (account.code,
                                                    _dollars(account.out_of_balance)))

    stats.append(Stat('Carries forward', carries, "in the funds that roll into next year"))
    if unspent:
        stats.append(Stat('Goes back to SGA' if year.year_over else 'SGA budget unspent',
                          unspent, "unspent at year end returns to SGA"))
    if awaiting:
        stats.append(Stat('Awaiting SGA', awaiting, "spent on funding requests, not yet repaid",
                          tone='text-warning'))

    if year.before_books:
        warnings.append("%s is before the books start, so there is nothing to report."
                        % period.label)
    if year.books_start is not None:
        notes.insert(0, "The books start on %s.%s Balances count every filed line, whichever "
                        "side of the partition it was for."
                     % (_day(year.books_start),
                        " The newest imported line is from %s." % _day(year.latest_line_date)
                        if year.latest_line_date else ''))
    if year.unassigned_lines:
        warnings.append("%s imported line%s carr%s no account code lnldb knows, so %s left "
                        "out." % (year.unassigned_lines,
                                  '' if year.unassigned_lines == 1 else 's',
                                  'ies' if year.unassigned_lines == 1 else 'y',
                                  'it is' if year.unassigned_lines == 1 else 'they are'))

    close = FiscalYearClose.objects.filter(fiscal_year=fiscal_year).first()
    if close is not None:
        changes = balances.drift(close, year)
        notes.append("%s was closed on %s." % (_short(fiscal_year), _day(close.closed_on)))
        for code, what, then, now in changes:
            warnings.append("Changed since %s was closed: %s %s was %s, now %s."
                            % (_short(fiscal_year), code, what, _dollars(then), _dollars(now)))

    return Report('fund-balances', 'Fund balances', period.label, period.dates,
                  period.file_part, columns, sections, stats, notes, warnings)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

#: Who an event was for, in the order the tables come.
EVENT_SECTIONS = (
    (ClientType.DEPARTMENT, 'Departments'),
    (ClientType.STUDENT_ORG, 'Student organizations'),
    (ClientType.UNKNOWN, 'Client not on file'),
)


def _event_cells(row):
    """ One event's figures as report cells. """
    return {
        'billed': row['billed'],
        'received': row['received'],
        'costs': row['costs'],
        'sga': row['sga_funded'],
        'margin': row['margin'],
        'margin_percent': row['margin_percent'],
    }


def event_report(period, is_projection=None, today=None):
    """
    Every event that ran in the period: billed, received, what it cost, and
    who paid for that, grouped by who the client was.

    Events that ran before the books start are left out, because their
    payments were never imported and every one of them would look unpaid.
    """
    today = today or timezone.localdate()
    start = books_start_date()
    rows = event_pnl_rows(None, is_projection, include_unlinked=True, since=start,
                          between=(period.first, period.last) if period.is_bounded else None,
                          today=today)

    columns = [
        Column('event', 'Event'),
        Column('date', 'Date', Column.DATE),
        Column('client', 'Client'),
        Column('billed', 'Billed', Column.MONEY, title="The latest bill, or the event's share "
                                                       "of a multi-bill"),
        Column('received', 'Received', Column.MONEY),
        Column('costs', 'Costs', Column.MONEY, title="Linked costs that reached Workday, net "
                                                     "of refunds"),
        Column('sga', 'Paid by SGA', Column.MONEY,
               title="The part of the costs filed to a funding request or the SGA budget"),
        Column('margin', 'Margin', Column.MONEY, coloured=True,
               title="Received less the costs LNL paid itself"),
        Column('margin_percent', 'Margin %', Column.PERCENT),
        Column('flags', 'Flags'),
    ]

    # A row carries its client type as the words for it, so the tables are
    # keyed by those words and titled from EVENT_SECTIONS.
    grouped = OrderedDict((ClientType(kind).label, []) for kind, _ in EVENT_SECTIONS)
    for row in rows:
        grouped.setdefault(row['client_type'], []).append(row)
    by_label = {ClientType(kind).label: title for kind, title in EVENT_SECTIONS}

    sections = []
    for label, members in list(grouped.items()):
        if not members:
            continue
        members.sort(key=lambda r: (r['event'].datetime_start, r['event'].pk))
        table = []
        for row in members:
            event = row['event']
            cells = _event_cells(row)
            cells.update({
                'event': event.event_name,
                'date': timezone.localtime(event.datetime_start).date(),
                'client': row['client'],
                'flags': '; '.join(text for _, text in row['flags']),
            })
            table.append(Row(cells, url=reverse('events:detail', args=[event.pk]),
                             note='share of a multi-bill' if row['billed_source'] == 'multibill'
                             else ''))
        totals = event_pnl_totals(members)
        count = totals['events']
        total = {'event': 'Total, %s event%s' % (count, '' if count == 1 else 's'),
                 'billed': totals['billed'], 'received': totals['received'],
                 'costs': totals['costs'], 'sga': totals['sga_funded'],
                 'margin': totals['margin'],
                 'margin_percent': (_percent(totals['margin'], totals['received'])
                                    if totals['received'] > 0 else None)}
        sections.append(Section(by_label.get(label, label), table, Row(total)))

    totals = event_pnl_totals(rows)
    billed_rows = [r for r in rows if r['billed'] is not None]
    billed_received = sum((r['received'] for r in billed_rows), ZERO)
    billed_margin = sum((r['margin'] for r in billed_rows), ZERO)
    hired = [r for r in rows if r['rentals_billed'] or r['passthrough_cost']]
    stats = [
        Stat('Events', totals['events'], '%s billed' % len(billed_rows), kind=Column.NUMBER),
        Stat('Received', totals['received'], 'of %s billed' % _dollars(totals['billed']),
             tone='text-success'),
        Stat("LNL's costs", totals['lnl_costs'],
             '%s more paid by SGA' % _dollars(totals['sga_funded']) if totals['sga_funded']
             else 'none paid by SGA', tone='text-danger'),
        Stat('Margin', totals['margin'],
             '%s event%s lost money' % (totals['losses'], '' if totals['losses'] == 1 else 's'),
             tone='text-success' if totals['margin'] >= 0 else 'text-danger'),
    ]
    if billed_received > 0:
        stats.append(Stat('Margin on billed events', _percent(billed_margin, billed_received),
                          'of what billed events brought in', kind=Column.PERCENT))
    if hired:
        under = sum(1 for r in hired if 'rental_under_billed' in r['flag_keys'])
        stats.append(Stat('Hired-in gear', sum((r['passthrough_cost'] for r in hired), ZERO),
                          'cost LNL, against %s billed for it%s'
                          % (_dollars(sum((r['rentals_recovered'] for r in hired), ZERO)),
                             '; %s under-billed' % under if under else '')))

    notes = ["An event belongs to the period it ran in, and every entry linked to it counts, "
             "whenever it landed.",
             "Billed is the latest bill, since a re-issued bill replaces the one before. A "
             "multi-bill is shared between its events by what each would have cost alone.",
             "A cost filed to a funding request or the SGA budget is paid by SGA. It is shown, "
             "but not counted against the margin. From FY27 LNL bills departments only; a "
             "student organization's show is funded through SGA."]
    if start is not None:
        notes.append("Events before the books start (%s) are left out: their payments were "
                     "never imported." % _day(start))
    if is_projection is not None:
        notes.append("Only entries on the %s side count."
                     % ('Projection' if is_projection else 'Event Production'))

    return Report('events', 'Events', period.label, period.dates, period.file_part,
                  columns, sections, stats, notes)


# ---------------------------------------------------------------------------
# What LNL is owed
# ---------------------------------------------------------------------------

#: Age bands, by days owed: up to 30, up to 60, up to 90, and older.
AGE_BANDS = ((30, '0-30 days'), (60, '31-60 days'), (90, '61-90 days'), (None, 'Over 90 days'))


def age_band(days):
    """ The band a debt ``days`` old falls in, or ``None`` when its age is unknown. """
    if days is None:
        return None
    for limit, label in AGE_BANDS:
        if limit is None or days <= limit:
            return label
    return None


def owed_to_lnl(is_projection=None, today=None):
    """
    Everything LNL is owed today, and how long it has been owed: SGA for each
    funding request's spending, and clients for each bill.
    """
    today = today or timezone.localdate()
    columns = [
        Column('who', 'Owed by'),
        Column('what', 'For'),
        Column('since', 'Owed since', Column.DATE,
               title="SGA: the oldest spending it has not paid for. A client: the day the "
                     "bill went out."),
        Column('charged', 'Charged', Column.MONEY,
               title="SGA: spending that reached Workday, plus anything owed when the books "
                     "started. A client: the bill."),
        Column('paid', 'Paid', Column.MONEY),
        Column('owed', 'Owed', Column.MONEY),
        Column('days', 'Days', Column.NUMBER),
        Column('age', 'Age'),
    ]

    receivables = sga_receivables(today=today)
    sga_rows, overpaid = [], []
    for item in receivables['rows']:
        request = item['request']
        if is_projection is not None and request.is_projection != is_projection:
            continue
        if item['awaiting'] < 0:
            overpaid.append(item)
            continue
        label = ('%s %s' % (request.reference, request.name)).strip()
        sga_rows.append(Row({
            'who': 'SGA', 'what': label, 'since': item['since'],
            'charged': money(request.owed_at_books_start) + request.total_charged,
            'paid': request.total_received, 'owed': item['awaiting'],
            'days': item['days'], 'age': age_band(item['days']),
        }, url=reverse('finance:fr-detail', args=[request.pk]), link='what',
            note=_short(request.fiscal_year) + (' (closed)' if request.closed else '')))
    sga_rows.sort(key=lambda r: -(r.cells['days'] or 0))

    client_rows = []
    for row in billing_receivables(is_projection, today=today):
        event = row['event']
        bill = row['bill']
        client_rows.append(Row({
            'who': row['client'] or 'No client on file', 'what': event.event_name,
            'since': getattr(bill, 'date_billed', None), 'charged': row['billed'],
            'paid': row['received'], 'owed': row['owed'], 'days': row['days_owed'],
            'age': age_band(row['days_owed']),
        }, url=reverse('events:detail', args=[event.pk]), link='what',
            note=row['client_type']))

    def total(rows, label):
        return Row({'who': label, 'owed': sum((r.cells['owed'] for r in rows), ZERO)})

    sections = [
        Section('SGA: funding requests', sga_rows, total(sga_rows, 'Total owed by SGA'),
                empty="SGA owes nothing: every request's spending has been repaid."),
        Section('Clients: event bills', client_rows, total(client_rows, 'Total owed by clients'),
                empty="No client owes anything on a bill sent since the books started."),
    ]

    everything = sga_rows + client_rows
    grand = sum((r.cells['owed'] for r in everything), ZERO)
    stats = [Stat('Owed to LNL', grand, '%s from SGA, %s from clients'
                  % (_dollars(sections[0].total.cells['owed']),
                     _dollars(sections[1].total.cells['owed'])), tone='text-warning')]
    for limit, label in AGE_BANDS:
        amount = sum((r.cells['owed'] for r in everything if r.cells['age'] == label), ZERO)
        stats.append(Stat(label, amount, tone='text-danger' if limit is None and amount else ''))

    notes = ["As of %s. SGA is aged from the oldest spending it has not yet paid for, since "
             "it repays spending in order; a client from the day the bill went out."
             % _day(today)]
    start = books_start_date()
    if start is not None:
        notes.append("Bills for events before the books start (%s) are left out: their "
                     "payments were never imported." % _day(start))
    if _partition_words(is_projection):
        notes.append(_partition_words(is_projection))
    warnings = []
    for item in overpaid:
        request = item['request']
        warnings.append("SGA has paid %s more than was spent on %s %s. LNL may be asked to "
                        "return it." % (_dollars(-item['awaiting']), request.reference,
                                        request.name))
    if receivables['difference'] and is_projection is None:
        warnings.append("The requests say SGA owes %s net, but the funding-request fund on the "
                        "balance page says %s. That is usually an opening balance entered on "
                        "one side only, or a year-end write-off."
                        % (_dollars(receivables['owed'] - receivables['overpaid']),
                           _dollars(receivables['fund_owed'])))

    return Report('owed-to-lnl', 'Owed to LNL', 'As of %s' % _day(today), '',
                  today.isoformat(), columns, sections, stats, notes, warnings)


# ---------------------------------------------------------------------------
# Student organizations and departments
#
# Both reports below read the events app, not the ledger: what LNL did and
# what it was worth at full rates, whether or not anybody paid for it. See
# finance.activity for how a show is priced.
# ---------------------------------------------------------------------------

SERVICE_VALUE_NOTE = ("Service value is what the events app would charge for LNL's own "
                      "services and extras at the event's price list, after its discounts "
                      "and fees -- what the work is worth at full rates, whether or not "
                      "anybody was billed for it. Hired-in gear and one-off charges are left "
                      "out: neither is LNL's work or LNL's gear.")
CLIENT_TYPE_NOTE = ("A client whose Workday fund is 810 is a student organization; any other "
                    "fund is a department or an outside client, billed at full rates. The "
                    "fund is read from the event, or else from its client.")
EVENTS_COUNTED_NOTE = ("Every approved event that ran, up to today; cancelled and test events "
                       "are left out. The Event Production / Projection switch does not apply: "
                       "films count under the Projection service.")


def _client_label(org):
    return org.name if org is not None else 'No client on file'


def work_split(period, today=None):
    """
    How LNL's work divides between student organizations and departments (with
    outside clients), by the value of what each used rather than by what was
    billed. From FY27 a student organization's show is invoiced at nothing, but
    it wears the gear like any other.

    The *external wear percentage* is the departmental and outside share of
    that value, over the work that can be placed:
    departments and external / (student organizations + departments and
    external).
    """
    today = today or timezone.localdate()
    work = activity.load_work(period.first, period.last, today)
    student, external, unplaced = (ClientType.STUDENT_ORG, ClientType.DEPARTMENT,
                                   ClientType.UNKNOWN)

    groups = OrderedDict((kind, {'events': 0, 'value': ZERO, 'billed': ZERO})
                         for kind in activity.CLIENT_GROUPS)
    by_category = OrderedDict((name, defaultdict(lambda: ZERO))
                              for name in activity.category_names())
    clients = OrderedDict()
    for item in work:
        group = groups[item.client_type]
        group['events'] += 1
        group['value'] += item.value
        group['billed'] += item.billed or ZERO
        for line in item.lines:
            by_category.setdefault(line.category_name, defaultdict(lambda: ZERO))
            by_category[line.category_name][item.client_type] += line.net
        key = item.client.pk if item.client is not None else None
        entry = clients.setdefault(key, {'client': item.client, 'type': item.client_type,
                                         'events': 0, 'value': ZERO, 'billed': ZERO})
        entry['events'] += 1
        entry['value'] += item.value
        entry['billed'] += item.billed or ZERO

    events = len(work)
    value = sum((group['value'] for group in groups.values()), ZERO)
    placed = groups[student]['value'] + groups[external]['value']
    wear = _percent(groups[external]['value'], placed) if placed else None

    who = [Column('group', 'Client type'), Column('events', 'Events', Column.NUMBER),
           Column('events_share', 'Share of events', Column.PERCENT),
           Column('value', 'Service value', Column.MONEY),
           Column('value_share', 'Share of value', Column.PERCENT),
           Column('billed', 'Billed', Column.MONEY,
                  title="The latest bill for each event, or its share of a multi-bill")]
    rows = []
    for kind, label in activity.CLIENT_GROUPS.items():
        group = groups[kind]
        if kind == unplaced and not group['events']:
            continue
        rows.append(Row({'group': label, 'events': group['events'],
                         'events_share': _percent(group['events'], events) if events else None,
                         'value': group['value'],
                         'value_share': _percent(group['value'], value) if value else None,
                         'billed': group['billed']}))
    total = Row({'group': 'All events', 'events': events, 'value': value,
                 'billed': sum((group['billed'] for group in groups.values()), ZERO)})
    sections = [Section('Who the work was for', rows, total, columns=who)]

    show_unplaced = bool(groups[unplaced]['value'])
    service = [Column('category', 'Service'),
               Column('student', 'Student organizations', Column.MONEY),
               Column('external', 'Departments and external', Column.MONEY)]
    if show_unplaced:
        service.append(Column('unplaced', 'Not classified', Column.MONEY))
    service += [Column('total', 'Total', Column.MONEY),
                Column('wear', 'External wear %', Column.PERCENT,
                       title="Departments and external, over student organizations and "
                             "departments together")]
    rows, totals = [], defaultdict(lambda: ZERO)
    for name, values in by_category.items():
        cells = {'category': name, 'student': values[student], 'external': values[external],
                 'unplaced': values[unplaced],
                 'total': values[student] + values[external] + values[unplaced]}
        if not cells['total']:
            continue
        both = values[student] + values[external]
        cells['wear'] = _percent(values[external], both) if both else None
        for key in ('student', 'external', 'unplaced', 'total'):
            totals[key] += cells[key]
        rows.append(Row(cells))
    total = {'category': 'All services', 'wear': wear}
    total.update(totals)
    sections.append(Section('By service', rows, Row(total), columns=service,
                            empty="No service was booked on these events."))

    client_columns = [Column('client', 'Client'), Column('type', 'Type'),
                      Column('events', 'Events', Column.NUMBER),
                      Column('value', 'Service value', Column.MONEY),
                      Column('billed', 'Billed', Column.MONEY),
                      Column('share', 'Share of value', Column.PERCENT)]
    ordered = sorted(clients.values(),
                     key=lambda c: (-c['value'], -c['events'], _client_label(c['client'])))
    rows = [Row({'client': _client_label(entry['client']),
                 'type': activity.CLIENT_GROUPS[entry['type']], 'events': entry['events'],
                 'value': entry['value'], 'billed': entry['billed'],
                 'share': _percent(entry['value'], value) if value else None},
                url=(reverse('orgs:detail', args=[entry['client'].pk])
                     if entry['client'] is not None else None))
            for entry in ordered]
    sections.append(Section('Clients', rows, columns=client_columns,
                            empty="No events in this period."))

    def described(kind):
        group = groups[kind]
        return '%s event%s, %s billed' % (group['events'], '' if group['events'] == 1 else 's',
                                          _dollars(group['billed']))

    stats = [
        Stat('Service value', value, '%s event%s' % (events, '' if events == 1 else 's')),
        Stat('Student organizations', groups[student]['value'], described(student)),
        Stat('Departments and external', groups[external]['value'], described(external)),
        Stat('External wear percentage', wear,
             'departments and external, over all the work that can be placed',
             kind=Column.PERCENT, tone='text-primary'),
    ]

    warnings = []
    if groups[unplaced]['events']:
        count, amount = groups[unplaced]['events'], groups[unplaced]['value']
        everything = placed + amount
        warning = ("%s event%s worth %s cannot be placed: neither the event nor its client "
                   "has a Workday fund on file, so %s left out of the external wear "
                   "percentage." % (count, '' if count == 1 else 's', _dollars(amount),
                                    'it is' if count == 1 else 'they are'))
        if amount and everything:
            warning += (" Counting them all as departmental would make it %s%%; all as "
                        "student organizations, %s%%. Setting the client's Workday fund in "
                        "lnldb places them."
                        % (_percent(groups[external]['value'] + amount, everything),
                           _percent(groups[external]['value'], everything)))
        elif not amount:
            warning += " None of them has a service booked, so the percentage is the same."
        warnings.append(warning)

    notes = [SERVICE_VALUE_NOTE, CLIENT_TYPE_NOTE,
             "Each show's discounts and fees are shared out across the services they "
             "apply to, so the services add up to the show's value to the cent.",
             "Billed is the events app's latest bill for each event. From FY27 LNL bills "
             "departments only; a student organization's show is funded through SGA.",
             EVENTS_COUNTED_NOTE]
    return Report('work-split', 'Student organizations and departments', period.label,
                  period.dates, period.file_part, who, sections, stats, notes, warnings)


# ---------------------------------------------------------------------------
# Event activity, term over term and year over year
# ---------------------------------------------------------------------------

#: How the columns are cut, and what each cell counts.
TREND_GROUPINGS = OrderedDict((('term', 'Term over term'), ('year', 'Year over year')))
TREND_MEASURES = OrderedDict((('events', 'How many'), ('value', 'Service value')))

#: How many clients are listed before the rest are rolled up.
TREND_CLIENTS = 15


def _trend_periods(fiscal_year, by, today):
    """
    The columns: the selected fiscal year and the four before it, or every term
    of the selected year and the one before, never past today.
    """
    if by == 'year':
        return [Period.for_fiscal_year(year, today)
                for year in range(fiscal_year - 4, fiscal_year + 1)
                if fiscal_year_bounds(year)[0] <= today]
    first = fiscal_year_bounds(fiscal_year - 1)[0]
    last = min(fiscal_year_bounds(fiscal_year)[1], today)
    periods = []
    for term in activity.terms_between(first, last):
        if term.first < first:
            continue
        partial = term.last > today
        periods.append(Period(term.first, min(term.last, today), to_date=partial,
                              name=term.code + (' to date' if partial else '')))
    return periods


def _comparison(latest, by):
    """ The same stretch a year before the latest column, to measure the change from. """
    first, last = _year_back(latest.first), _year_back(latest.last)
    if by == 'year':
        base = _short(latest.fiscal_year - 1)
    else:
        term = activity.term_for(first).code
        base = term
    return Period(first, last, name=base + (', same dates' if latest.to_date else ''))


def _item_label(line):
    """ How a service or an extra reads as a row. """
    item = line.item
    if line.kind == activity.Line.EXTRA:
        return '%s (add-on)' % item.name
    if item.longname.startswith(item.shortname):
        return item.longname
    return '%s: %s' % (item.shortname, item.longname)


def activity_trends(fiscal_year, by='term', measure='events', today=None):
    """
    What LNL has been doing more or less of, term over term or year over year:
    who it worked for, which services, which service tiers and add-ons, which
    clients. ``measure`` is ``'events'`` to count -- events, bookings, items --
    or ``'value'`` for the service value of each.
    """
    today = today or timezone.localdate()
    counting = measure != 'value'
    periods = _trend_periods(fiscal_year, by, today)
    started = activity.earliest_event_date()
    if started is not None:
        kept = [p for p in periods if p.last >= started]
        periods = kept or periods[-1:]
    latest = periods[-1] if periods else None
    compared = _comparison(latest, by) if latest is not None else None
    if compared is not None and (started is None or compared.last < started):
        compared = None

    stretches = periods + ([compared] if compared is not None else [])
    work = (activity.load_work(min(p.first for p in stretches), max(p.last for p in stretches),
                               today) if stretches else [])
    categories = activity.category_names()
    labels, order, clients = {}, {}, {}

    def tally(stretch):
        out = defaultdict(lambda: 0 if counting else ZERO)
        for item in work:
            if not (stretch.first <= item.day <= stretch.last):
                continue
            weight = 1 if counting else item.value
            out[('all',)] += weight
            out[('group', item.client_type)] += weight
            key = item.client.pk if item.client is not None else None
            clients[key] = item.client
            out[('client', key)] += weight
            used = set()
            for line in item.lines:
                name = line.category_name
                if counting:
                    if name not in used:
                        out[('category', name)] += 1
                        used.add(name)
                    out[('item',) + line.key] += line.quantity
                else:
                    out[('category', name)] += line.net
                    out[('item',) + line.key] += line.net
                labels[line.key] = _item_label(line)
                rank = categories.index(name) if name in categories else len(categories)
                order[line.key] = (rank, line.kind != activity.Line.SERVICE, labels[line.key])
            out[('rentals',)] += item.rental_items if counting else item.rental_cost
        return out

    columns_tallies = [tally(p) for p in periods]
    change_tally = tally(compared) if compared is not None else None
    kind = Column.NUMBER if counting else Column.MONEY

    columns = [Column('line', 'Line')]
    columns += [Column('p%s' % index, period.label, kind) for index, period in enumerate(periods)]
    if change_tally is not None:
        columns.append(Column('change', 'Change from %s' % compared.label, kind, signed=True,
                              title="The latest column less the same dates a year before"))

    def row(label, key, url=None, note=''):
        cells = {'line': label}
        for index, counts in enumerate(columns_tallies):
            cells['p%s' % index] = counts.get(key, 0 if counting else ZERO)
        if change_tally is not None:
            cells['change'] = cells['p%s' % (len(periods) - 1)] - change_tally.get(
                key, 0 if counting else ZERO)
        return Row(cells, url=url, note=note)

    def busy(item):
        return any(item.cells['p%s' % index] for index in range(len(periods))) or \
            item.cells.get('change')

    everything = row('All events', ('all',))
    who = [row(label, ('group', kind)) for kind, label in activity.CLIENT_GROUPS.items()]
    who = [item for item in who if busy(item) or item.cells['line'] != 'Not classified']
    sections = [Section('Who it was for', who, everything,
                        empty="No events in these periods.")]

    names = categories + sorted({key[1] for counts in columns_tallies for key in counts
                                 if key[0] == 'category' and key[1] not in categories})
    services = [row(name, ('category', name)) for name in names]
    sections.append(Section('Services', [item for item in services if busy(item)],
                            row('All events', ('all',)),
                            empty="No service was booked in these periods."))

    tiers = [row(labels[key], ('item',) + key) for key in sorted(order, key=order.get)]
    rentals = row('Hired-in gear' + (' (items)' if counting else ', at cost'), ('rentals',),
                  note='' if counting else 'not part of service value')
    tiers = [item for item in tiers + [rentals] if busy(item)]
    sections.append(Section('Service tiers and add-ons', tiers,
                            empty="Nothing was booked in these periods."))

    ranked = sorted(clients, key=lambda key: (
        -sum(counts.get(('client', key), 0) for counts in columns_tallies),
        _client_label(clients[key])))
    shown = [row(_client_label(clients[key]), ('client', key),
                 url=reverse('orgs:detail', args=[key]) if key is not None else None)
             for key in ranked[:TREND_CLIENTS]]
    shown = [item for item in shown if busy(item)]
    rest = [row('', ('client', key)) for key in ranked[TREND_CLIENTS:]]
    if rest:
        other = {'line': '%s other clients' % len(rest)}
        for column in columns[1:]:
            other[column.key] = sum((item.cells[column.key] for item in rest),
                                    0 if counting else ZERO)
        shown.append(Row(other))
    sections.append(Section('Clients', shown, row('All events', ('all',)),
                            empty="No events in these periods."))

    stats = []
    if latest is not None:
        def during(stretch):
            return [item for item in work if stretch.first <= item.day <= stretch.last]

        def earlier(text):
            return '%s in %s' % (text, compared.label) if compared is not None else ''

        shows, before = during(latest), during(compared) if compared is not None else []
        value_now = sum((item.value for item in shows), ZERO)
        value_before = sum((item.value for item in before), ZERO)
        placed = [item for item in shows if item.client_type != ClientType.UNKNOWN]
        placed_value = sum((item.value for item in placed), ZERO)
        external = sum((item.value for item in placed
                        if item.client_type == ClientType.DEPARTMENT), ZERO)
        stats = [
            Stat('Events, %s' % latest.label, len(shows), earlier(len(before)),
                 kind=Column.NUMBER),
            Stat('Service value, %s' % latest.label, value_now,
                 earlier(_dollars(value_before))),
            Stat('External wear percentage, %s' % latest.label,
                 _percent(external, placed_value) if placed_value else None,
                 'departments and external, over work that can be placed',
                 kind=Column.PERCENT, tone='text-primary'),
        ]

    counted = ("Each cell counts events; under Services, the events that used it; under "
               "service tiers and add-ons, how many were booked; for hired-in gear, how many "
               "items were hired." if counting else
               "Each cell is service value, except hired-in gear, which is what it cost.")
    notes = [counted, SERVICE_VALUE_NOTE, CLIENT_TYPE_NOTE, EVENTS_COUNTED_NOTE]
    if by == 'term':
        notes.append("WPI's terms move by a few days each year, so each one is taken to start "
                     "on a fixed day in the break before it: C on January 1, D on March 10, E "
                     "(summer) on May 20, A on August 15 -- so new student orientation counts "
                     "as A term -- and B on October 15.")
    if compared is not None:
        notes.append("The change compares %s with %s." % (latest.label, compared.label))
    file_part = '%s-%s-%s' % (by, 'value' if not counting else 'count',
                              _short(fiscal_year).lower())
    return Report('activity', 'Event activity', TREND_GROUPINGS.get(by, ''),
                  '%s to %s' % (periods[0].label, periods[-1].label) if periods else '',
                  file_part, columns, sections, stats, notes)


# ---------------------------------------------------------------------------
# The forecast, to print and download
# ---------------------------------------------------------------------------

def forecast_report(result):
    """
    A forecast from :func:`finance.forecast.project`, laid out as a report:
    the headline figures, each month, every dated movement, and the typical
    year it rests on.
    """
    from finance.forecast import COMPONENTS, OWN

    period = 'To %s' % _day(result.horizon)
    file_part = 'to-%s' % _short(fiscal_year_for(result.horizon)).lower()
    if not result.available:
        return Report('forecast', "Forecast", period, '', file_part,
                      [Column('what', '')], [], warnings=[result.problem])

    code = result.code
    columns = ([Column('month', 'Month')]
               + [Column(key, label, Column.MONEY, coloured=True)
                  for key, label in COMPONENTS.items()]
               + [Column('own', "LNL's own money", Column.MONEY)]
               + ([Column('low', 'Weakest year', Column.MONEY),
                   Column('high', 'Strongest year', Column.MONEY)] if result.has_band else [])
               + [Column('cash', 'All of %s' % code, Column.MONEY)])
    months = []
    for month in result.months:
        cells = {'month': month.label, 'own': month.own, 'low': month.low,
                 'high': month.high, 'cash': month.cash}
        cells.update({key: month.flows.get(key) or None for key in COMPONENTS})
        months.append(Row(cells, tone='danger' if month.below_reserve else ''))

    dated_columns = [Column('day', 'When', Column.DATE), Column('what', 'What'),
                     Column('part', 'Part'), Column('fund', 'Fund'),
                     Column('amount', 'Amount', Column.MONEY, coloured=True)]
    dated = [Row({'day': item.day, 'what': item.label, 'part': item.component_label,
                  'fund': ("Own money" if item.fund == OWN
                           else result.fund_names.get(item.fund) or ''),
                  'amount': item.amount}, url=item.url or None, note=item.detail)
             for item in result.items]

    typical = result.typical
    year_ends = result.year_ends
    typical_columns = ([Column('part', 'Part')]
                       + [Column('fy%s' % year, _short(year), Column.MONEY)
                          for year in sorted(typical.years)]
                       + [Column('annual', 'Typical year', Column.MONEY)]
                       + [Column('to%s' % month.fiscal_year, 'Counted to %s' % _short(
                           month.fiscal_year), Column.MONEY, coloured=True)
                          for month in year_ends])
    typical_rows = []
    for row in result.typical_rows:
        cells = {'part': row['label'], 'annual': row['annual']}
        cells.update({'fy%s' % year: amount for year, amount in row['past'].items()})
        cells.update({'to%s' % month.fiscal_year: row['by_year'].get(month.fiscal_year)
                      for month in year_ends})
        typical_rows.append(Row(cells))

    low = result.low_point
    stats = [Stat("LNL's own money now", result.opening_own,
                  sub='%s holds %s in all' % (code, _dollars(result.opening_cash)))]
    for month in year_ends:
        stats.append(Stat('June 30, %s' % month.last.year, month.own,
                          sub=('Range %s to %s' % (_dollars(month.low), _dollars(month.high))
                               if month.low is not None else ''),
                          tone='text-danger' if month.below_reserve else ''))
    stats.append(Stat('Lowest point', low.own, sub='End of %s' % low.label,
                      tone='text-danger' if low.below_reserve else ''))
    stats.append(Stat('Room to spend', result.room,
                      sub='and keep %s to %s' % (_dollars(result.reserve),
                                                 _day(result.horizon)),
                      tone='text-danger' if result.room < 0 else ''))

    notes = ["The figure that matters is LNL's own money: %s." % result.fund_names.get(OWN),
             "SGA pays back a funding request %s." % result.waits['sga'].after("the spending"),
             "Clients pay %s." % result.waits['bill'].after("the show")] + list(result.notes)
    if result.without:
        notes.insert(0, "Left out: %s." % ', '.join(
            label for key, label in COMPONENTS.items() if key in result.without))
    return Report(
        'forecast', "Forecast for %s" % code, period,
        'from the books as of %s' % _day(result.since), file_part, columns,
        [Section('Each month', months),
         Section('Dated, one by one', dated, empty='Nothing dated is ahead.',
                 columns=dated_columns),
         Section('A typical year: the median of %s' % typical.span, typical_rows,
                 empty='No whole years on file.', columns=typical_columns)],
        stats=stats, notes=notes, warnings=result.warnings)


# ---------------------------------------------------------------------------
# A first budget request
# ---------------------------------------------------------------------------

#: How many whole years a draft budget is worked out from.
BUDGET_YEARS = 3

#: A proposed line is rounded up to a multiple of this.
BUDGET_ROUNDING = Decimal('50')


def _round_up(amount):
    """ Up to the next multiple of :data:`BUDGET_ROUNDING`. """
    if amount <= 0:
        return ZERO
    return (amount / BUDGET_ROUNDING).to_integral_value(rounding=ROUND_CEILING) * BUDGET_ROUNDING


def budget_draft(today=None, ledger=None):
    """
    Next fiscal year's SGA budget request, drafted from what LNL spent.

    An SGA budget is a set of lines of expected spending, by general
    category and split between Event Production and Projection, with one
    approved figure for each. So each line here is a spend category on one
    side: what the last three whole years spent on it, net of refunds, this
    year so far, the median of the three, and that median rounded up to the
    next $50 as the figure to propose.

    Every year is counted the way the forecast counts it -- filed where the
    books cover it, read where they do not -- and spending SGA paid for
    through funding requests is included, because with a budget that is what
    the budget would pay for.

    The categories forecast from plans -- equipment -- are one line. A line
    read from Workday cannot tell a capital purchase from the rest, so the
    years before the books would put all of it in one and the years since in
    the other, and neither line's median would mean anything.
    """
    from finance.forecast import event_account_code

    today = today or timezone.localdate()
    ledger = ledger or history.Ledger()
    current = fiscal_year_for(today)
    target = current + 1
    code = event_account_code()
    years = sorted(ledger.whole_years(code, before=current)[:BUDGET_YEARS]) if code else []
    categories = history.spending_categories()

    planned = [category for category in categories.values() if category.forecast_from_plans]
    spent = defaultdict(lambda: defaultdict(lambda: ZERO))
    for flow in ledger.flows:
        if flow.kind != 'spending' or flow.left_out:
            continue
        year = flow.fiscal_year
        if year in years or year == current:
            category = categories.get(flow.category)
            line = 'plans' if category is not None and category.forecast_from_plans else flow.category
            spent[(flow.is_projection, line)][year] -= flow.amount

    year_columns = [Column('fy%s' % year, _short(year), Column.MONEY) for year in years]
    columns = ([Column('line', 'Line')] + year_columns
               + [Column('so_far', '%s so far' % _short(current), Column.MONEY),
                  Column('median', 'Median', Column.MONEY),
                  Column('proposed', 'Proposed for %s' % _short(target), Column.MONEY)])

    def order(key):
        if key[1] == 'plans':
            return (False, min(c.sort_order for c in planned), '')
        category = categories.get(key[1])
        return (key[1] is None, getattr(category, 'sort_order', 0), str(category or ''))

    def label(key):
        if key[1] == 'plans':
            return ' and '.join(c.name for c in sorted(planned, key=lambda c: c.sort_order))
        category = categories.get(key[1])
        return category.name if category is not None else 'Not worked out'

    sections, stats, grand = [], [], ZERO
    for is_projection, side in ((False, 'Event Production'), (True, 'Projection')):
        keys = sorted((key for key in spent if key[0] == is_projection), key=order)
        rows = []
        totals = defaultdict(lambda: ZERO)
        for key in keys:
            by_year = spent[key]
            if not any(by_year.values()):
                continue
            median = (money(statistics.median([by_year.get(year, ZERO) for year in years]))
                      if years else ZERO)
            proposed = _round_up(median)
            cells = {'line': label(key), 'so_far': by_year.get(current, ZERO), 'median': median,
                     'proposed': proposed}
            cells.update({'fy%s' % year: by_year.get(year, ZERO) for year in years})
            for column, value in cells.items():
                if column != 'line':
                    totals[column] += value
            rows.append(Row(cells, note=('Chosen one purchase at a time: the request should '
                                         'name what will be bought' if key[1] == 'plans'
                                         else '')))
        if not rows:
            continue
        total = dict(totals)
        total['line'] = 'Total'
        sections.append(Section(side, rows, total=Row(total)))
        stats.append(Stat('%s, %s' % (side, _short(target)), total['proposed'],
                          sub='median of %s' % ', '.join(_short(y) for y in years)))
        grand += total['proposed']
    if len(stats) > 1:
        stats.append(Stat('Whole request', grand))

    warnings = []
    if len(years) < BUDGET_YEARS:
        warnings.append(
            "Only %s whole year%s on file. Import older Workday exports for a draft built on %s."
            % (len(years), '' if len(years) == 1 else 's', BUDGET_YEARS))
    notes = [
        "A draft to argue from, not a request: each proposed line is the median of the years "
        "beside it, rounded up to the next $%s." % BUDGET_ROUNDING,
        "Spending is net of refunds. Spending SGA paid for through funding requests is "
        "included, because with a budget it is what the budget would pay for.",
        "A budget covers expected spending only; nothing here counts what LNL brings in.",
        "Years before the books start are read from the Workday lines, not filed: see the "
        "History page, where any line can be corrected.",
    ]
    return Report('budget-draft', "Draft budget request for %s" % _short(target),
                  _short(target), '', _short(target).lower(), columns, sections,
                  stats=stats, notes=notes, warnings=warnings)


# ---------------------------------------------------------------------------
# The list the Reports page shows
# ---------------------------------------------------------------------------

#: ``slug: (title, what it answers, what period it takes)``. The period is
#: ``'range'`` for any dates, ``'year'`` for a fiscal year only, and
#: ``'today'`` for a report that is always as of today.
REPORTS = OrderedDict((
    ('income-and-spending', ("Income and spending",
                             "What came in, by source and client, and what went out, by "
                             "spend category, beside the same dates a year earlier. The "
                             "starting point for a budget request.", 'range')),
    ('fund-balances', ("Fund balances",
                       "What each fund in each account held at the start and end of the year, "
                       "what moved, and what carries forward or goes back to SGA.", 'year')),
    ('events', ("Events",
                "Every event's billing, payments, costs and margin, by client type, with the "
                "costs SGA paid for shown separately.", 'range')),
    ('owed-to-lnl', ("Owed to LNL",
                     "What SGA owes on each funding request and what each client owes on their "
                     "bill, and how long each has been owed.", 'today')),
    ('work-split', ("Student organizations and departments",
                    "The value of LNL's work for student organizations against departments and "
                    "outside clients, at full rates whether billed or not, service by service: "
                    "the external wear percentage.", 'range')),
    ('activity', ("Event activity",
                  "What LNL is doing more or less of, term over term or year over year: who for, "
                  "which services, which service tiers and add-ons, and which clients.",
                  'trend')),
    ('forecast', ("Forecast",
                  "Where LNL's own money is heading, month by month to the end of next fiscal "
                  "year: what is reserved, owed, booked and planned, and a typical year.",
                  'today')),
    ('budget-draft', ("Draft budget request",
                      "Next year's SGA budget request, line by line: each spend category's "
                      "spending over the last three whole years, and a figure to propose.",
                      'next')),
))

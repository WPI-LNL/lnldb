"""
Every bank line LNL has, reduced to what it was: the forecast's raw material.

Two kinds of line make up the past. Lines from the books start on are filed in
the queue, and their slices say exactly what each one was. Lines from before
it are **history**: imported from older Workday exports so the forecast can
learn what a year looks like, and never filed, because years of old lines is
not work anybody should have to do to get a forecast.

So history is *read* instead, by the lookups the queue fills its boxes from
-- the memo naming a category, Workday's own spend category, the ledger
account -- and never by the wording rules, which are guesses. A line nothing
looks up is "not worked out" rather than guessed into a category, and a
reading is an estimate, labelled as one wherever it shows. The Treasurer can
correct any of them, or leave a one-off out, with a
:class:`~finance.models.HistoryOverride`.

Everything here ends as a :class:`Flow` -- one amount of money on one day,
and what it was -- so the forecast, the History page and the draft budget
never need to know which kind of line they are looking at. Nothing is stored:
change a rule in the admin and the next page load reads the history again.
"""
import datetime
from collections import defaultdict
from decimal import Decimal

from finance.models import (ZERO, FundBehaviour, HistoryKind, HistoryOverride,
                            ParsedTransaction, SpendCategory, WorkdayTransaction,
                            books_start_date, fiscal_year_bounds, fiscal_year_for, money,
                            partition_codes)

#: Ledger accounts LNL's client billing posts to: Internal Service Provider
#: Revenue, and, before FY20, the interdepartmental transfers LNL invoiced
#: through.
BILLING_ACCOUNTS = ('70050', '70000')

#: Event Sponsorship: the account SGA's journal entries post to, paying in
#: and taking back alike.
SGA_ACCOUNTS = ('74600',)

#: A fiscal year counts as a whole year once its lines cover this many
#: months. FY18's export is one day of conversion entries; FY19's starts in
#: September.
WHOLE_YEAR_MONTHS = 9

#: Funds SGA pays for, so that spending from them is not LNL's own. The same
#: rule the event P&L uses.
SGA_PAID_BEHAVIOURS = (FundBehaviour.REIMBURSED, FundBehaviour.RETURNS)


# ---------------------------------------------------------------------------
# Reading one line nobody filed
# ---------------------------------------------------------------------------

class Reading(object):
    """
    What a line nobody filed was taken to be, and why.

    ``category`` is a :class:`SpendCategory` pk, for spending only, or
    ``None`` when no lookup says. ``reference`` is the SGA request the memo
    quotes, which makes spending SGA's to pay back rather than LNL's.
    ``corrected`` is set when the Treasurer's correction decided it, and
    ``estimate`` then holds what the line itself said, so the page can show
    both.
    """

    def __init__(self, kind, category=None, reason='', corrected=False, left_out=False,
                 note='', estimate=None, reference=''):
        self.kind = kind
        self.category = category
        self.reason = reason
        self.reference = reference
        self.corrected = corrected
        self.left_out = left_out
        self.note = note
        self.estimate = estimate

    @property
    def kind_label(self):
        """ The kind in words. """
        return HistoryKind(self.kind).label


def lookup_rules():
    """
    The queue's suggestion rules that are lookups, in priority order.

    Wording rules are left out: a word found in prose is a guess, and a guess
    nobody confirms has no business deciding years of a category.
    """
    from finance.suggestions import active_suggestion_rules

    return [rule for rule in active_suggestion_rules() if rule.is_lookup]


def read_line(txn, rules=None):
    """
    What a line was, from the line alone, as a :class:`Reading`.

    Tried in order:

    1. **SGA**: anything on the SGA account, or shaped like SGA's own journal
       entries (see :func:`finance.suggestions.is_sga_transfer`). Both ways:
       paying in, and taking back.
    2. **Client billing**: money in on a billing account, or on an Internal
       Service Delivery.
    3. **Other**: money in from no supplier and no person -- a transfer from
       another of LNL's accounts, a gift.
    4. **Spending**: money out, and money back from whoever was paid (a
       refund, which un-spends), in the category the lookups give. A memo
       quoting an SGA request number makes it a funding request's spending,
       which SGA pays back -- the queue fills the fund in the same way.
    """
    from finance.suggestions import (ISD_DOCUMENT_TYPE, is_sga_transfer, memo_fields,
                                     suggest_spend_category)

    account = (txn.ledger_account or '').strip()
    if account.startswith(SGA_ACCOUNTS) or is_sga_transfer(txn):
        return Reading(HistoryKind.SGA, reason='SGA account %s' % account if account
                       else 'SGA journal entry quoting a request')
    if txn.net_amount > 0:
        if account.startswith(BILLING_ACCOUNTS):
            return Reading(HistoryKind.BILLING, reason='Billing account %s' % account)
        if (txn.document_type or '').strip().lower() == ISD_DOCUMENT_TYPE:
            return Reading(HistoryKind.BILLING, reason='An Internal Service Delivery')
        if not (txn.supplier or txn.employee):
            return Reading(HistoryKind.OTHER, reason='Money in from no supplier or person')

    fields = memo_fields(txn)
    suggestion = suggest_spend_category(txn, rules=lookup_rules() if rules is None else rules,
                                        fields=fields)
    if suggestion is not None and suggestion.is_lookup:
        category, reason = suggestion.value, suggestion.reason
    else:
        category, reason = None, 'No lookup says which category'
    if txn.net_amount > 0:
        reason = 'Money back on a purchase. %s' % reason
    if fields.reference:
        reason = '%s; memo quotes %s, so SGA pays it back' % (reason, fields.reference)
    return Reading(HistoryKind.SPENDING, category, reason, reference=fields.reference)


def reading_for(txn, override=None, rules=None):
    """
    How a history line is read, with the Treasurer's correction applied.

    A correction may change what the line was, its category, or both, and may
    leave it out; whatever it does not say, the line's own reading still does.
    """
    estimate = read_line(txn, rules)
    if override is None:
        return estimate
    kind = override.kind or estimate.kind
    if kind != HistoryKind.SPENDING:
        category = None
    elif override.spend_category_id:
        category = override.spend_category_id
    else:
        category = estimate.category if estimate.kind == HistoryKind.SPENDING else None
    changed = (kind != estimate.kind or category != estimate.category)
    return Reading(kind, category,
                   reason='Corrected by the Treasurer' if changed else estimate.reason,
                   corrected=changed, left_out=override.leave_out, note=override.note,
                   estimate=estimate,
                   reference=estimate.reference if kind == HistoryKind.SPENDING else '')


# ---------------------------------------------------------------------------
# Every line, as flows
# ---------------------------------------------------------------------------

class Flow(object):
    """
    One amount of money on one day, and what it was.

    ``day`` is the bank's date, because what the forecast learns is when money
    moves. ``account`` is the account code the line came out of, ``None`` when
    no account claims it. ``estimated`` is set on anything read rather than
    filed. ``sga_paid`` marks spending SGA pays for: filed to a fund SGA pays, or,
    on a line read rather than filed, one whose memo quotes an SGA request.
    """

    __slots__ = ('day', 'amount', 'kind', 'category', 'account', 'line', 'estimated',
                 'left_out', 'sga_paid', 'is_projection')

    def __init__(self, day, amount, kind, category=None, account=None, line=None,
                 estimated=False, left_out=False, sga_paid=False, is_projection=False):
        self.day = day
        self.amount = amount
        self.kind = kind
        self.category = category
        self.account = account
        self.line = line
        self.estimated = estimated
        self.left_out = left_out
        self.sga_paid = sga_paid
        self.is_projection = is_projection

    @property
    def fiscal_year(self):
        """ The fiscal year the money moved in. """
        return fiscal_year_for(self.day)

    def __repr__(self):
        return "<Flow %s %s %s %s>" % (self.day, self.amount, self.kind, self.category)


def _account_of(worktags, codes):
    """ ``(account code, is_projection)`` for a line's worktags. """
    from finance.balances import account_code_for

    code = account_code_for(worktags, codes)
    projection = any(entry['code'] == code and entry['is_projection'] for entry in codes)
    return code, projection


def _slice_kind(amount, refund_of, event, request, credits_fund):
    """ What a filed slice was, in the forecast's terms. """
    if amount > 0 and refund_of is None:
        if event is not None:
            return HistoryKind.BILLING
        if request is not None or credits_fund is not None:
            return HistoryKind.SGA
        return HistoryKind.OTHER
    if request is not None:
        # SGA taking back a payment: income undone, not spending.
        return HistoryKind.SGA
    return HistoryKind.SPENDING


class Ledger(object):
    """
    Every bank line LNL has imported, as flows, loaded once.

    Filed slices come through as filed. Whatever part of a line is not filed
    -- all of a history line, the rest of a line half done in the queue -- is
    read with :func:`reading_for`. ``readings`` keeps each history line's
    reading for the History page.
    """

    def __init__(self):
        self.start = books_start_date()
        self.flows = []
        self.readings = {}
        codes = partition_codes()
        rules = lookup_rules()
        overrides = {override.line_id: override for override in HistoryOverride.objects.all()}

        filed = defaultdict(lambda: ZERO)
        slices = list(ParsedTransaction.objects.filter(parent_transaction__isnull=False)
                      .values_list('parent_transaction_id', 'parent_transaction__accounting_date',
                                   'parent_transaction__worktags_json', 'amount', 'refund_of_id',
                                   'linked_event_id', 'funding_request_id',
                                   'non_event_revenue_type__credits_fund_id',
                                   'lnl_spend_category_id', 'fund_source__behaviour',
                                   'is_projection'))
        for (line, day, worktags, amount, refund_of, event, request, credits_fund, category,
             behaviour, projection) in slices:
            amount = money(amount)
            filed[line] += amount
            kind = _slice_kind(amount, refund_of, event, request, credits_fund)
            self.flows.append(Flow(
                day, amount, kind,
                category=category if kind == HistoryKind.SPENDING else None,
                account=_account_of(worktags, codes)[0], line=line,
                sga_paid=kind == HistoryKind.SPENDING and behaviour in SGA_PAID_BEHAVIOURS,
                is_projection=projection))

        for txn in WorkdayTransaction.objects.all():
            left = money(txn.net_amount) - filed.get(txn.pk, ZERO)
            if not left:
                continue
            history = self.start is not None and txn.accounting_date < self.start
            reading = reading_for(txn, overrides.get(txn.pk) if history else None, rules)
            if history:
                self.readings[txn.pk] = reading
            code, projection = _account_of(txn.worktags_json, codes)
            self.flows.append(Flow(
                txn.accounting_date, left, reading.kind, category=reading.category,
                account=code, line=txn.pk, estimated=True, left_out=reading.left_out,
                sga_paid=bool(reading.reference), is_projection=projection))

    # -- what the years were ----------------------------------------------------
    def for_account(self, code):
        """ The flows on one account. """
        return [flow for flow in self.flows if flow.account == code]

    def months_covered(self, code):
        """ ``{fiscal year: number of calendar months with a line}`` on one account. """
        seen = defaultdict(set)
        for flow in self.for_account(code):
            seen[flow.fiscal_year].add((flow.day.year, flow.day.month))
        return {year: len(months) for year, months in seen.items()}

    def whole_years(self, code, before):
        """
        The fiscal years before ``before`` whose lines cover enough of the year
        to count as one, newest first.
        """
        covered = self.months_covered(code)
        return sorted((year for year, months in covered.items()
                       if year < before and months >= WHOLE_YEAR_MONTHS), reverse=True)


# ---------------------------------------------------------------------------
# How much of past billing the same shows would be charged today
# ---------------------------------------------------------------------------

#: How many shows with a price have to have run since FY27 began before the
#: share they show is trusted.
SHARE_MIN_SHOWS = 25


class BilledShare(object):
    """
    The part of billing before FY27 that the same shows would still be
    charged today, and where that figure came from. ``share`` is a fraction,
    or ``None`` when nobody knows.
    """

    def __init__(self, share, source, detail=''):
        self.share = share
        self.source = source
        self.detail = detail

    @property
    def known(self):
        """ Whether there is a share to scale past billing by. """
        return self.share is not None

    @property
    def percent(self):
        """ The share as a whole percentage, for the page. """
        return None if self.share is None else int((self.share * 100).quantize(Decimal('1')))


def measured_billed_share(today=None):
    """
    What the shows run since FY27 began are charged, as a share of their full
    price, or ``None`` when too few have run to say.

    An SGA-funded show is charged its hired gear and one-off charges, any other
    show its full price (:attr:`finance.activity.Work.charged`). A show marked
    No bill needed is charged nothing; one marked so for any reason but SGA
    funding is left out, since it would not have been billed before FY27
    either. History cannot say which past shows SGA would fund now -- its lines
    name events, not what they were charged for -- so the shows since are the
    measure.

    Returns ``(share, charged, full price, shows)``.
    """
    from finance.activity import load_work
    from finance.models import SGA_FUNDED_FROM, NoBillNeeded

    first = fiscal_year_bounds(SGA_FUNDED_FROM)[0]
    reasons = dict(NoBillNeeded.objects.values_list('event_id', 'reason'))
    charged = full = ZERO
    shows = 0
    for work in load_work(first=first, today=today):
        reason = reasons.get(work.event.pk)
        if reason is not None and reason != NoBillNeeded.SGA_FUNDED:
            continue
        if work.full_price <= 0:
            continue
        shows += 1
        full += work.full_price
        if reason is None:
            charged += work.charged
    if shows < SHARE_MIN_SHOWS:
        return None, charged, full, shows
    return charged / full, charged, full, shows


def billed_share(today=None):
    """
    The share of billing before FY27 the same shows would still be charged
    today: the Treasurer's figure if one is set, else the one the shows run
    since FY27 began show, else unknown.
    """
    from finance.models import finance_settings

    configured = finance_settings().still_billed_share
    if configured is not None:
        return BilledShare(Decimal(configured) / 100, 'set',
                           "%s%%, set in Finance Configuration" % configured)
    share, charged, full, shows = measured_billed_share(today)
    if share is None:
        return BilledShare(
            None, 'unknown',
            "%s show%s with a price %s run since FY27 began, and it is measured once %s have"
            % (shows, '' if shows == 1 else 's', 'has' if shows == 1 else 'have',
               SHARE_MIN_SHOWS))
    return BilledShare(
        share, 'measured',
        "the %s shows run since FY27 began came to %s at full price and were charged %s"
        % (shows, _dollars(full), _dollars(charged)))


def _dollars(amount):
    """ A whole-dollar figure for a sentence. """
    return '${:,.0f}'.format(amount)


# ---------------------------------------------------------------------------
# The years, side by side
# ---------------------------------------------------------------------------

def year_summary(ledger, code):
    """
    Each fiscal year on one account, in the forecast's terms:
    ``[{'year', 'months', 'lines', 'estimated', 'billing', 'sga', 'other',
    'spending': {category pk: amount}, 'spent', 'net', 'left_out'}]``, oldest
    first. Spending is net of refunds and negative, as the bank has it.
    """
    years = {}
    lines = defaultdict(set)
    estimated = defaultdict(set)
    for flow in ledger.for_account(code):
        year = flow.fiscal_year
        row = years.setdefault(year, {
            'year': year, 'billing': ZERO, 'sga': ZERO, 'other': ZERO,
            'spending': defaultdict(lambda: ZERO), 'spent': ZERO, 'net': ZERO,
            'left_out': ZERO})
        lines[year].add(flow.line)
        if flow.estimated:
            estimated[year].add(flow.line)
        if flow.left_out:
            row['left_out'] += flow.amount
            continue
        row['net'] += flow.amount
        if flow.kind == HistoryKind.SPENDING:
            row['spending'][flow.category] += flow.amount
            row['spent'] += flow.amount
        else:
            row[flow.kind] += flow.amount
    covered = ledger.months_covered(code)
    out = []
    for year in sorted(years):
        row = years[year]
        row['months'] = covered.get(year, 0)
        row['lines'] = len(lines[year])
        row['estimated'] = len(estimated[year])
        out.append(row)
    return out


def june_cash(code, years, books=None):
    """
    ``{fiscal year: cash on its last day}`` on one account, worked back from
    the Workday balance entered for it. Empty with no balance entered.

    Only as right as the exports are complete: a missing month shows up as a
    balance that never adds up to the next one Workday reported.
    """
    from finance.balances import Books

    books = books or Books()
    if books.anchor(code) is None:
        return {}
    out = {}
    for year in years:
        last = fiscal_year_bounds(year)[1]
        out[year] = books.cash_on(code, min(last, datetime.date.today()))
    return out


def spending_categories():
    """ ``{pk: SpendCategory}``, every one, retired ones too: history uses them. """
    return {category.pk: category for category in SpendCategory.objects.all()}

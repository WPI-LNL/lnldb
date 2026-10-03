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

from finance.models import (ZERO, ClientType, FundBehaviour, HistoryKind, HistoryOverride,
                            ParsedTransaction, SpendCategory, WorkdayTransaction,
                            books_start_date, client_type_for, fiscal_year_bounds,
                            fiscal_year_for, money, partition_codes)

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
    filed. ``client_type`` is known only for billing filed against an event.
    ``sga_paid`` marks spending SGA pays for: filed to a fund SGA pays, or,
    on a line read rather than filed, one whose memo quotes an SGA request.
    """

    __slots__ = ('day', 'amount', 'kind', 'category', 'account', 'line', 'estimated',
                 'left_out', 'client_type', 'sga_paid', 'is_projection')

    def __init__(self, day, amount, kind, category=None, account=None, line=None,
                 estimated=False, left_out=False, client_type=None, sga_paid=False,
                 is_projection=False):
        self.day = day
        self.amount = amount
        self.kind = kind
        self.category = category
        self.account = account
        self.line = line
        self.estimated = estimated
        self.left_out = left_out
        self.client_type = client_type
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


def _client_types(event_ids):
    """ ``{event pk: ClientType}`` for the events billing was filed against. """
    from events.models import BaseEvent

    out = {}
    for event in (BaseEvent.objects.filter(pk__in=list(event_ids))
                  .select_related('billing_org').prefetch_related('org')):
        out[event.pk] = client_type_for(event)
    return out


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
        types = _client_types({row[5] for row in slices if row[5] is not None})
        for (line, day, worktags, amount, refund_of, event, request, credits_fund, category,
             behaviour, projection) in slices:
            amount = money(amount)
            filed[line] += amount
            kind = _slice_kind(amount, refund_of, event, request, credits_fund)
            self.flows.append(Flow(
                day, amount, kind,
                category=category if kind == HistoryKind.SPENDING else None,
                account=_account_of(worktags, codes)[0], line=line,
                client_type=types.get(event, ClientType.UNKNOWN) if event is not None else None,
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
# How much of past billing came from departments
# ---------------------------------------------------------------------------

#: How much of the billing since the books started has to be filed against
#: events whose client is on file before the split it shows is trusted.
SHARE_COVERAGE = Decimal('0.5')


class DepartmentShare(object):
    """
    The part of billing before FY27 that departments paid, and where that
    figure came from. ``share`` is a fraction, or ``None`` when nobody knows.
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


def measured_department_share(flows, policy_from):
    """
    The departments' share of billing filed against events before
    ``policy_from``, or ``None`` when too little is filed to say.

    Returns ``(share, departments, known, all billing)``.
    """
    known = departments = total = ZERO
    start = books_start_date()
    for flow in flows:
        if flow.kind != HistoryKind.BILLING or flow.day >= policy_from:
            continue
        if start is not None and flow.day < start:
            # History cannot say who paid, and is not the books.
            continue
        total += flow.amount
        if flow.client_type in (ClientType.DEPARTMENT, ClientType.STUDENT_ORG):
            known += flow.amount
            if flow.client_type == ClientType.DEPARTMENT:
                departments += flow.amount
    if total <= 0 or known <= 0 or known < total * SHARE_COVERAGE:
        return None, departments, known, total
    return departments / known, departments, known, total


def department_share(flows):
    """
    The departments' share of billing before FY27: the Treasurer's figure if
    one is set, else the one the filed billing shows, else unknown.
    """
    from finance.models import DEPARTMENTS_ONLY_FROM, finance_settings

    configured = finance_settings().department_billing_share
    if configured is not None:
        return DepartmentShare(Decimal(configured) / 100, 'set',
                               "%s%%, set in Finance Configuration" % configured)
    policy_from = fiscal_year_bounds(DEPARTMENTS_ONLY_FROM)[0]
    share, departments, known, total = measured_department_share(flows, policy_from)
    if share is None:
        return DepartmentShare(
            None, 'unknown',
            "%s of %s billed before FY27 is filed against an event whose client is on file"
            % (_dollars(known), _dollars(total)) if total > 0 else
            "no billing from before FY27 is in the books")
    return DepartmentShare(
        share, 'measured',
        "departments paid %s of the %s billed before FY27 that is filed against an event "
        "whose client is on file" % (_dollars(departments), _dollars(known)))


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

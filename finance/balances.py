"""
What each fund holds, worked out from the ledger rather than stored.

Workday reports one balance per account. This module splits each account's
balance between the funds inside it -- Legacy, the SGA budget, funding-request
money, the Projection mandatory transfer -- and proves the split adds back up
to Workday's figure. The arithmetic, for one account on one day:

* **Cash** is a Workday balance (a :class:`~finance.models.BalanceCheckpoint`)
  plus or minus every imported line between that balance's date and the day
  asked about. The earliest checkpoint is the anchor; every later one is a
  test of the arithmetic, and a difference means lines are missing.

* **A fund's balance** is what was filed to it since the books started --
  money in, less money out -- plus or minus any transfers between funds. The
  account's own fund (the carry-forward fund held in it: Legacy in 226-AG)
  also holds whatever the account had the night before the books started,
  because that is what an account's money is when nobody has said otherwise.

* **Unfiled** is whatever part of the account's lines has not been allocated
  yet. It is a row of its own so the funds plus it always equal the cash: a
  queue left half-done makes the split vague, not wrong.

* **An event's costs wait for its payment.** An expense on LNL's own money (a
  fund that carries forward) that names the event it was for is not counted
  against that fund until the event is paid for: a sub-rental hired for a show
  the client has yet to pay would otherwise make Legacy look short by money
  that is coming back. Until then it sits in a row of its own, *Event costs
  awaiting payment*, so the account still adds up to its cash. On the day the
  event's bill is marked paid it moves into the fund, as a transfer. An event
  marked *No bill needed*, or closed unpaid, will never be paid for, so its
  costs move on that day instead. An encumbrance naming an event waits the
  same way. See :func:`event_paid_days`.

* **What billed events will pay in** is shown beside the funds, not in them:
  no cash has moved. Every payment for an event lands in the Event Production
  account's own fund (Legacy in 226-AG) -- a Projection showing's too -- so
  each bill not yet paid is listed there with what is still owed on it, and
  *free once paid* says what Legacy will have when they all are: the payments
  come in, and the costs waiting for those same events move in with them. See
  :meth:`Books.billed_unpaid`.

Nothing is carried from one year to the next by copying a closing balance into
an opening one. Every figure is a sum from the start of the books, so a line
imported in August for a June purchase corrects last year's closing balance
and this year's opening in the same moment. See
:class:`~finance.models.FiscalYearClose` for how a closed year notices.
"""
import datetime
from collections import defaultdict, namedtuple

from django.db.models import Q
from django.utils import timezone

from finance.models import (ZERO, BalanceCheckpoint, FiscalYearClose, FundBehaviour,
                            FundSource, FundTransfer, ParsedTransaction, PartitionCode,
                            TransactionStatus, WorkdayTransaction, account_own_funds,
                            books_start_date, fiscal_year_bounds, fiscal_year_for, money,
                            org_code_matches, partition_codes, worktag_value)

ONE_DAY = datetime.timedelta(days=1)

#: The key the costs still waiting for their event's payment are held under,
#: in place of a fund's pk.
WAITING = 'waiting'

#: One event with a bill: the bill that stands for it, what it was billed, the
#: day it stopped waiting for its payment (``None`` while it still waits), and
#: ``[(date, amount)]`` of the payments settled against it.
BilledEvent = namedtuple('BilledEvent', 'event bill billed stopped payments')


class UnpaidBill(object):
    """ One bill not yet paid, as a fund row lists it: the event, its bill and what is still owed. """

    def __init__(self, event, bill, owed):
        self.event = event
        self.bill = bill
        self.owed = owed

    @property
    def stage(self):
        """
        Where the bill stands, as the Billing page says it. Worked out only when
        shown: the dashboard reads the same statement and never shows it.
        """
        from finance.billing import STAGES, stage_of
        stage = stage_of(self.event, self.bill)
        return STAGES[stage] if stage else ''

    @property
    def client(self):
        """ Who the bill is to (a multi-bill's *Bill to*, else the event's client), or ``''``. """
        from finance.calculators import payer_of
        org = payer_of(self.event)
        return org.retname if org else ''


def _local_day(value):
    """ The local date of a stored datetime. """
    return timezone.localdate(value) if timezone.is_aware(value) else value.date()


def event_paid_days(event_ids):
    """
    ``{event pk: day}`` the day each of these events stopped waiting for its
    payment, leaving out those still waiting.

    That is the day its bill was marked paid -- the bill that stands for it, its
    own or its multi-bill's -- or, for an event that will never be paid for,
    the day it was marked *No bill needed* or closed, whichever came first. A
    bill is marked paid on the day the last of its money reached Workday, so the
    cost and the payment covering it land in the fund together.
    """
    from events.models import BaseEvent
    from finance.calculators import latest_bill
    from finance.models import no_bill_needed_for

    if not event_ids:
        return {}
    out = {}
    events = (BaseEvent.objects.non_polymorphic().filter(pk__in=list(event_ids))
              .select_related('no_bill_needed').prefetch_related('billings', 'multibillings'))
    for event in events:
        days = []
        bill = latest_bill(event)
        if bill is not None and bill.date_paid:
            days.append(bill.date_paid)
        no_bill = no_bill_needed_for(event)
        if no_bill is not None:
            days.append(_local_day(no_bill.decided_on))
        if event.closed:
            # Closed before the day was recorded: it has stopped waiting, since when is unknown.
            days.append(_local_day(event.closed_on) if event.closed_on else datetime.date.min)
        if days:
            out[event.pk] = min(days)
    return out


def account_code_for(worktags, codes=None):
    """
    Which account a line's worktags put it in, or ``None``.

    The same test as :attr:`WorkdayTransaction.matched_partition_code`, on the
    raw worktags, so a whole ledger can be sorted into accounts without
    building a model instance per line.
    """
    for entry in (partition_codes() if codes is None else codes):
        if org_code_matches(worktag_value(worktags, entry['worktag']), entry['code']):
            return entry['code']
    return None


class Books(object):
    """
    Everything the arithmetic reads, loaded once.

    A handful of queries for the whole ledger, rather than one per figure: a
    statement asks for every fund's balance on two dates in every account, and
    the dashboard asks again. A few thousand small tuples is far cheaper than
    the hundred aggregates that would otherwise be.
    """

    def __init__(self):
        self.start = books_start_date()
        self.accounts = list(PartitionCode.objects.order_by('code'))
        self.funds = {fund.pk: fund for fund in FundSource.objects.select_related('account')}
        own = account_own_funds()
        self.own_fund_ids = {code: fund.pk for code, fund in own.items()}
        #: The account every event's payment lands in: the Event Production
        #: account with money of its own. A Projection showing is paid into it
        #: too.
        self.billing_account = next((account.code for account in self.accounts
                                     if not account.is_projection
                                     and account.code in self.own_fund_ids), None)
        self._billed_events = None

        codes = partition_codes()
        #: ``{line pk: (date, amount, account code)}``. Every line: cash is a
        #: Workday balance plus or minus the lines between it and the day
        #: asked about.
        self.lines = {}
        self.unassigned_lines = 0
        for pk, date, amount, worktags in WorkdayTransaction.objects.values_list(
                'pk', 'accounting_date', 'net_amount', 'worktags_json'):
            code = account_code_for(worktags, codes)
            if code is None:
                self.unassigned_lines += 1
            self.lines[pk] = (date, money(amount), code)

        #: ``(line pk, fund pk, amount, is_refund, event pk)`` for every slice of
        #: a bank line. The event is there only on a cost that waits for it to be
        #: paid for (see :meth:`waits_for_event`), and is ``None`` otherwise.
        self.slices = []
        for line, fund, amount, refund, event in (
                ParsedTransaction.objects.filter(parent_transaction__isnull=False)
                .values_list('parent_transaction_id', 'fund_source_id', 'amount',
                             'refund_of_id', 'linked_event_id')):
            amount, is_refund = money(amount), refund is not None
            is_cost = amount < 0 or is_refund
            self.slices.append((line, fund, amount, is_refund,
                                event if is_cost and self.waits_for_event(fund) else None))

        #: ``(fund pk, amount, date, event pk)`` for every encumbrance still
        #: open, the event as on :attr:`slices`.
        self.encumbrances = [
            (fund, money(amount), date, event if self.waits_for_event(fund) else None)
            for fund, amount, date, event in ParsedTransaction.objects
            .filter(parent_transaction__isnull=True, status=TransactionStatus.PENDING)
            .values_list('fund_source_id', 'amount', 'effective_date', 'linked_event_id')]

        #: ``{event pk: day}`` each event a cost waits for was paid for. See
        #: :func:`event_paid_days`.
        self.paid_on = event_paid_days(
            {entry[4] for entry in self.slices if entry[4] is not None}
            | {entry[3] for entry in self.encumbrances if entry[3] is not None})

        self.transfers = list(FundTransfer.objects.select_related(
            'account', 'from_fund', 'to_fund'))

        self.checkpoints = defaultdict(list)
        for checkpoint in BalanceCheckpoint.objects.select_related('account').order_by('as_of'):
            self.checkpoints[checkpoint.account.code].append(checkpoint)

        self.latest_line_date = max((date for date, _, _ in self.lines.values()), default=None)

    def waits_for_event(self, fund):
        """
        Whether a cost on ``fund`` that names an event waits for the event to
        be paid for: one on LNL's own money does, one SGA pays for does not --
        a funding request already shows what SGA owes for it. A cost naming no
        fund is the account's own money.
        """
        if fund is None:
            return True
        source = self.funds.get(fund)
        return source is not None and source.behaviour == FundBehaviour.CARRIES

    def waiting(self, event, day):
        """ Whether a cost waiting for ``event`` (or ``None``) still waits at the end of ``day``. """
        if event is None:
            return False
        paid = self.paid_on.get(event)
        return paid is None or paid > day

    # -- cash -----------------------------------------------------------------
    def anchor(self, code):
        """ The checkpoint the account's cash is counted from: its earliest. """
        points = self.checkpoints.get(code)
        return points[0] if points else None

    def cash_on(self, code, day):
        """
        What the account held at the end of ``day``, or ``None`` with no anchor.

        Counted forwards from the anchor for a later day and backwards for an
        earlier one, so entering today's Workday balance is enough to work out
        what the account held the night the books started.
        """
        anchor = self.anchor(code)
        if anchor is None:
            return None
        total = money(anchor.balance)
        for date, amount, line_code in self.lines.values():
            if line_code != code:
                continue
            if anchor.as_of < date <= day:
                total += amount
            elif day < date <= anchor.as_of:
                total -= amount
        return total

    # -- funds ----------------------------------------------------------------
    def _transfer_date(self, transfer):
        """
        When a transfer counts. An opening split counts the night before the
        books start, so it shows as the opening balance rather than as a
        movement in the first year.
        """
        if transfer.kind == FundTransfer.OPENING and self.start is not None:
            return self.start - ONE_DAY
        return transfer.date

    def positions(self, code, day):
        """
        Every fund's balance in one account at the end of ``day``.

        Returns ``(balances, unfiled, opening_cash)``: ``balances`` is
        ``{fund pk: amount}``, with ``None`` standing for slices that name no
        fund on an account with no fund of its own, and :data:`WAITING` for
        event costs still waiting for their payment. ``opening_cash`` is what
        the account held the night before the books started, or ``None``.
        """
        balances = defaultdict(lambda: ZERO)
        if self.start is None:
            return balances, ZERO, None
        own = self.own_fund_ids.get(code)
        opening_cash = self.cash_on(code, self.start - ONE_DAY)
        if opening_cash is not None:
            balances[own] += opening_cash

        filed = defaultdict(lambda: ZERO)
        for line, fund, amount, _, event in self.slices:
            date, _, line_code = self.lines[line]
            if line_code != code or not (self.start <= date <= day):
                continue
            if self.waiting(event, day):
                balances[WAITING] += amount
            else:
                balances[fund if fund is not None else own] += amount
            filed[line] += amount

        unfiled = ZERO
        for pk, (date, amount, line_code) in self.lines.items():
            if line_code == code and self.start <= date <= day:
                unfiled += amount - filed.get(pk, ZERO)

        for transfer in self.transfers:
            if transfer.account.code != code or self._transfer_date(transfer) > day:
                continue
            amount = money(transfer.amount)
            balances[transfer.from_fund_id] -= amount
            balances[transfer.to_fund_id] += amount
        return balances, unfiled, opening_cash

    def movements(self, code, first, last):
        """
        What came in, went out and moved between funds over a stretch of days.

        ``{fund pk: {'received', 'spent', 'transferred'}}``. Spending is net of
        refunds, because a credit back on a purchase un-spends it rather than
        earning anything. Opening splits are left out: they are the opening.

        An event cost still waiting on the day it was charged is spent by
        :data:`WAITING`, and moves to its fund as a transfer on the day the
        event is paid for. Counting it as the fund's spending then would count
        it twice in the account's total.
        """
        own = self.own_fund_ids.get(code)
        out = defaultdict(lambda: {'received': ZERO, 'spent': ZERO, 'transferred': ZERO})
        for line, fund, amount, is_refund, event in self.slices:
            date, _, line_code = self.lines[line]
            if line_code != code or date > last:
                continue
            target = fund if fund is not None else own
            waited = self.waiting(event, date)
            if waited and not self.waiting(event, last):
                paid = self.paid_on[event]
                if paid >= first:
                    out[target]['transferred'] += amount
                    out[WAITING]['transferred'] -= amount
            if date < first:
                continue
            row = out[WAITING if waited else target]
            if amount > 0 and not is_refund:
                row['received'] += amount
            else:
                row['spent'] -= amount
        for transfer in self.transfers:
            if (transfer.account.code != code or transfer.kind == FundTransfer.OPENING
                    or not (first <= transfer.date <= last)):
                continue
            amount = money(transfer.amount)
            out[transfer.from_fund_id]['transferred'] -= amount
            out[transfer.to_fund_id]['transferred'] += amount
        return out

    def encumbered(self, code, day):
        """
        ``{fund pk: amount}`` encumbered and not yet charged, for funds held in
        this account. An encumbrance has no bank line, so it belongs to the
        account its fund is held in. One for an event not yet paid for is
        under :data:`WAITING`, as its cost will be once charged.
        """
        out = defaultdict(lambda: ZERO)
        for fund, amount, date, event in self.encumbrances:
            if self._held_in(fund, code) and date <= day:
                out[WAITING if self.waiting(event, day) else fund] -= amount
        return out

    def waiting_events(self, code, day):
        """
        ``{event pk: amount}`` of what still waits for each event at the end of
        ``day`` in this account: its costs and encumbrances together, as a
        positive figure.
        """
        out = defaultdict(lambda: ZERO)
        for line, _, amount, _, event in self.slices:
            date, _, line_code = self.lines[line]
            if line_code == code and self.start <= date <= day and self.waiting(event, day):
                out[event] -= amount
        for fund, amount, date, event in self.encumbrances:
            if self._held_in(fund, code) and date <= day and self.waiting(event, day):
                out[event] -= amount
        return out

    def _held_in(self, fund, code):
        """ Whether ``fund`` is held in the account ``code``. """
        source = self.funds.get(fund)
        return source is not None and source.account is not None and source.account.code == code

    # -- bills ----------------------------------------------------------------
    @property
    def billed_events(self):
        """
        A :data:`BilledEvent` for every event billed since the books started,
        loaded the first time anything asks: most of what reads :class:`Books`
        never does.

        The billed figure is :func:`~finance.calculators.event_billed`'s, a
        multi-bill shared out by price, so it is the bill the Owed to LNL
        report and the event's P&L read. Cancelled and test events are left
        out, and so are events before the books start, whose payments were
        never imported.
        """
        if self._billed_events is None:
            self._billed_events = self._load_billed_events()
        return self._billed_events

    def _load_billed_events(self):
        from events.models import BaseEvent
        from finance.calculators import (_event_queryset, event_billed, latest_bill,
                                         multibill_income)

        if self.start is None:
            return []
        ids = list(BaseEvent.objects
                   .filter(Q(billings__isnull=False) | Q(multibillings__isnull=False),
                           cancelled=False, test_event=False,
                           datetime_start__date__gte=self.start)
                   .values_list('pk', flat=True).distinct())
        if not ids:
            return []
        stopped = event_paid_days(ids)
        payments = defaultdict(list)
        settled = ParsedTransaction.objects.revenue().filter(parent_transaction__isnull=False)
        for event, date, amount in (settled.filter(linked_event_id__in=ids)
                                    .values_list('linked_event_id', 'effective_date', 'amount')):
            payments[event].append((date, money(amount)))
        # A multi-bill's payment counts towards each event by its share.
        for entry, event, share in multibill_income(
                settled.filter(linked_multibill__events__in=ids).distinct()):
            payments[event.pk].append((entry.effective_date, share))
        cache, out = {}, []
        for event in _event_queryset().filter(pk__in=ids):
            billed, _ = event_billed(event, cache)
            out.append(BilledEvent(event, latest_bill(event), billed, stopped.get(event.pk),
                                   payments.get(event.pk, [])))
        return out

    def billed_unpaid(self, code, day):
        """
        An :class:`UnpaidBill` for every bill still waiting for its payment
        at the end of ``day``, longest-owed first, if ``code`` is the account
        event payments land in (:attr:`billing_account`), and ``[]`` for any
        other.

        A bill counts from the day it is dated, until the day its event stops
        waiting for its payment -- marked paid, marked *No bill needed* or
        closed (:func:`event_paid_days`), the same day the event's costs move
        into Legacy. What is owed is the bill less the payments settled
        against it by then. A bill not emailed yet still counts: what it will
        bring in is known.
        """
        if code != self.billing_account:
            return []
        out = []
        for item in self.billed_events:
            if item.bill is None or item.billed is None or item.bill.date_billed > day:
                continue
            if item.stopped is not None and item.stopped <= day:
                continue
            received = sum((amount for date, amount in item.payments if date <= day), ZERO)
            owed = item.billed - received
            if owed > 0:
                out.append(UnpaidBill(item.event, item.bill, owed))
        out.sort(key=lambda unpaid: (unpaid.bill.date_billed, unpaid.event.pk))
        return out


# ---------------------------------------------------------------------------
# One year, laid out
# ---------------------------------------------------------------------------

class FundRow(object):
    """ One fund's line on an account's statement. """

    #: Whether this is the row of event costs waiting for their payment, and
    #: the events it waits for. See :class:`WaitingRow`.
    is_waiting = False
    events = ()

    #: The bills not yet paid whose money will land in this fund, each an
    #: :class:`UnpaidBill`, and what still waits for those same events (see
    #: :meth:`Books.waiting_events`). Only the own fund of the account event
    #: payments land in has any: see :meth:`Books.billed_unpaid`.
    unpaid_bills = ()
    waiting_for_billed = ZERO

    def __init__(self, fund, opening, received, spent, transferred, closing, encumbered,
                 is_own, year_over):
        self.fund = fund
        self.opening = opening
        self.received = received
        self.spent = spent
        self.transferred = transferred
        self.closing = closing
        self.encumbered = encumbered
        self.is_own = is_own
        self.year_over = year_over

    @property
    def name(self):
        """ The fund's name, or what an unnamed balance is. """
        return str(self.fund) if self.fund is not None else "No fund named"

    @property
    def behaviour(self):
        """ The fund's :class:`FundBehaviour`, carrying forward if unknown. """
        return self.fund.behaviour if self.fund is not None else FundBehaviour.CARRIES

    @property
    def behaviour_label(self):
        """ What happens to the fund at year end, in words, or nothing for an unnamed one. """
        return self.fund.get_behaviour_display() if self.fund is not None else ''

    @property
    def available(self):
        """
        What can still be spent: the balance less what is encumbered. ``None``
        for a fund SGA reimburses, which never holds money to spend -- see
        :attr:`to_reimburse` for what its figure means instead.
        """
        if self.closing is None or self.behaviour == FundBehaviour.REIMBURSED:
            return None
        return self.closing - self.encumbered

    @property
    def billed(self):
        """ What the bills not yet paid will bring into this fund. """
        return sum((unpaid.owed for unpaid in self.unpaid_bills), ZERO)

    @property
    def free_once_paid(self):
        """
        What will be free once every bill not yet paid is: the payments come
        in, and the costs and encumbrances waiting for those same events move
        in with them. Events with costs waiting and no bill yet are left out of
        both sides, as what they will bring in is not known. ``None`` with no
        bill unpaid, or no free figure to start from.
        """
        if not self.unpaid_bills or self.available is None:
            return None
        return self.available + self.billed - self.waiting_for_billed

    @property
    def to_reimburse(self):
        """
        For a fund SGA reimburses: what SGA will owe once the encumbered
        purchases are charged, as a positive figure. ``None`` for any other
        kind of fund.
        """
        if self.closing is None or self.behaviour != FundBehaviour.REIMBURSED:
            return None
        return self.encumbered - self.closing

    @property
    def status(self):
        """
        What the closing figure means, in words, for this kind of fund.

        The same number says opposite things depending on how SGA pays the
        money: a negative funding-request balance is money SGA owes LNL, and a
        positive budget balance at year end is money LNL owes SGA.
        """
        closing = self.closing
        if closing is None:
            return "Enter a Workday balance to see this"
        if not any((closing, self.opening, self.received, self.spent, self.transferred)):
            # "Fully spent" would claim money arrived; nothing has.
            return "Nothing in or out yet"
        behaviour = self.behaviour
        if behaviour == FundBehaviour.RETURNS:
            if closing > 0:
                return "Goes back to SGA" if self.year_over else "Left to spend this year"
            if closing < 0:
                return "Overspent -- cover it from money that carries forward"
            return "Fully spent"
        if behaviour == FundBehaviour.REIMBURSED:
            if closing < 0:
                return "Awaiting reimbursement from SGA"
            if closing > 0:
                return "More reimbursed than spent -- check the reimbursements"
            return "Fully reimbursed"
        if closing < 0:
            return "Overdrawn"
        return "Carries forward" if self.year_over else "Carries forward at year end"


class WaitingRow(FundRow):
    """
    The costs of events not yet paid for, kept out of the fund they were
    charged to until the client pays. See :data:`WAITING`.

    ``events`` is ``[(event, amount)]``: each event still waited on at the end,
    with what its costs and encumbrances come to.
    """

    is_waiting = True

    def __init__(self, opening, received, spent, transferred, closing, encumbered, year_over,
                 events):
        super(WaitingRow, self).__init__(None, opening, received, spent, transferred, closing,
                                         encumbered, is_own=False, year_over=year_over)
        self.events = events

    @property
    def name(self):
        return "Event costs awaiting payment"

    @property
    def behaviour(self):
        """ None: the row is no fund, and nothing happens to it at year end. """
        return None

    @property
    def behaviour_label(self):
        return "Waits for each event's payment"

    @property
    def available(self):
        return None

    @property
    def to_reimburse(self):
        return None

    @property
    def status(self):
        if self.closing or self.encumbered:
            return "Moves into the fund it was charged to when the event is paid for"
        return "Every event paid for"

    @property
    def is_empty(self):
        """ Nothing waiting, and nothing waited during the period. """
        return not any((self.opening, self.received, self.spent, self.transferred,
                        self.closing, self.encumbered))


class CheckpointRow(object):
    """ A Workday balance beside what the ledger says that day. """

    def __init__(self, checkpoint, computed, is_anchor):
        self.checkpoint = checkpoint
        self.computed = computed
        self.is_anchor = is_anchor

    @property
    def difference(self):
        """ Workday's figure less the ledger's. Non-zero means lines are missing. """
        return money(self.checkpoint.balance) - self.computed


class AccountStatement(object):
    """ One account's year: cash at each end, and the funds that make it up. """

    def __init__(self, account, first, last, rows, unfiled_opening, unfiled_closing,
                 opening_cash, closing_cash, checkpoints, own_fund):
        self.account = account
        self.first = first
        self.last = last
        self.rows = rows
        self.unfiled_opening = unfiled_opening
        self.unfiled_closing = unfiled_closing
        self.opening_cash = opening_cash
        self.closing_cash = closing_cash
        self.checkpoints = checkpoints
        self.own_fund = own_fund

    @property
    def code(self):
        """ The account's code, e.g. 226-AG. """
        return self.account.code

    @property
    def cash_known(self):
        """ Whether a Workday balance has been entered for this account. """
        return self.closing_cash is not None

    def _sum(self, attribute):
        """ One column of the fund rows, added up. """
        return sum((getattr(row, attribute) for row in self.rows), ZERO)

    @property
    def received(self):
        """ What came into the account's funds over the period. """
        return self._sum('received')

    @property
    def spent(self):
        """ What the account's funds spent over the period, net of refunds. """
        return self._sum('spent')

    @property
    def transferred(self):
        """ Transfers between funds, added up: zero, since none leaves the account. """
        return self._sum('transferred')

    @property
    def encumbered(self):
        """ What is encumbered against the account's funds. """
        return self._sum('encumbered')

    @property
    def billed(self):
        """ What bills not yet paid will bring into the account. """
        return self._sum('billed')

    @property
    def unpaid_bills(self):
        """ Every :class:`UnpaidBill` on the account's funds, longest-owed first. """
        return [unpaid for row in self.rows for unpaid in row.unpaid_bills]

    @property
    def funds_total(self):
        """ Every fund's closing balance, plus what is unfiled. """
        if not self.cash_known:
            return None
        return sum((row.closing for row in self.rows), ZERO) + self.unfiled_closing

    @property
    def out_of_balance(self):
        """
        How far the funds miss the cash by. Zero by construction; anything else
        is a bug worth seeing rather than hiding.
        """
        if not self.cash_known:
            return ZERO
        return self.closing_cash - self.funds_total

    @property
    def is_empty(self):
        """ Nothing to show: no money, no activity, no Workday balance. """
        return (not self.rows and not self.checkpoints and not self.unfiled_closing
                and not self.closing_cash)


class Statement(object):
    """ Every account's statement for one fiscal year, or the part of it booked. """

    def __init__(self, fiscal_year, first, last, accounts, books, year_over, before_books):
        self.fiscal_year = fiscal_year
        self.first = first
        self.last = last
        self.accounts = accounts
        self.books = books
        self.year_over = year_over
        self.before_books = before_books

    @property
    def books_start(self):
        """ The first day the books count from. """
        return self.books.start

    @property
    def latest_line_date(self):
        """ The newest line imported, which is as current as any figure here is. """
        return self.books.latest_line_date

    @property
    def unassigned_lines(self):
        """ Lines on no known account, left out of every figure. """
        return self.books.unassigned_lines

    def account(self, code):
        """ One account's statement by its code, or ``None``. """
        for statement in self.accounts:
            if statement.code == code:
                return statement
        return None


def _row_order(row):
    """
    The account's own money first, then what waits to join it, then the funds
    in their admin order.
    """
    fund = row.fund
    return (0 if row.is_own else 1 if row.is_waiting else 2,
            fund.sort_order if fund else 999, row.name)


def _waiting_row(waits, opening, moved, closing, reserved, year_over):
    """
    The account's row of event costs awaiting payment, or ``None`` when nothing
    waits or waited. Takes its figures out of the funds' dicts as it goes.
    ``waits`` is :meth:`Books.waiting_events` at the end of the period.
    """
    from events.models import BaseEvent

    movement = moved.pop(WAITING, None) or {'received': ZERO, 'spent': ZERO,
                                            'transferred': ZERO}
    waiting = {pk: amount for pk, amount in waits.items() if amount}
    names = BaseEvent.objects.non_polymorphic().in_bulk(list(waiting))
    events = sorted(((names[pk], amount) for pk, amount in waiting.items() if pk in names),
                    key=lambda pair: (pair[0].datetime_start, pair[0].pk))
    row = WaitingRow(opening.pop(WAITING, ZERO), movement['received'], movement['spent'],
                     movement['transferred'], closing.pop(WAITING, ZERO),
                     reserved.pop(WAITING, ZERO), year_over, events)
    return None if row.is_empty else row


def statement(fiscal_year, books=None, today=None):
    """
    Every account's funds over one fiscal year: opening, movements, closing.

    A year still running stops at ``today``, and says so. A year that began
    before the books did starts on the day they did, because nothing before
    that was filed.
    """
    books = books or Books()
    today = today or timezone.localdate()
    year_start, year_end = fiscal_year_bounds(fiscal_year)
    year_over = year_end < today

    if books.start is None or year_end < books.start:
        return Statement(fiscal_year, year_start, year_end, [], books, year_over,
                         before_books=books.start is not None)

    first = max(year_start, books.start)
    last = min(year_end, today)
    accounts = []
    for account in books.accounts:
        code = account.code
        own_id = books.own_fund_ids.get(code)
        opening, unfiled_opening, opening_cash = books.positions(code, first - ONE_DAY)
        closing, unfiled_closing, _ = books.positions(code, last)
        moved = books.movements(code, first, last)
        reserved = books.encumbered(code, last)
        cash_known = opening_cash is not None
        waits = books.waiting_events(code, last)
        waiting = _waiting_row(waits, opening, moved, closing, reserved, year_over)

        held_here = {pk for pk, fund in books.funds.items()
                     if fund.account_id == account.pk and fund.is_active}
        fund_ids = set(opening) | set(closing) | set(moved) | set(reserved) | held_here
        rows = [waiting] if waiting is not None else []
        for fund_id in fund_ids:
            fund = books.funds.get(fund_id)
            is_own = fund_id == own_id
            row_opening = opening.get(fund_id, ZERO)
            row_closing = closing.get(fund_id, ZERO)
            movement = moved.get(fund_id) or {'received': ZERO, 'spent': ZERO,
                                              'transferred': ZERO}
            if is_own and not cash_known:
                # Without an anchor the own fund's opening is unknown, and so is
                # everything that rests on it. Its movements are still real.
                row_opening = row_closing = None
            if fund_id is None and not any((row_closing, movement['received'],
                                            movement['spent'], movement['transferred'])):
                continue
            rows.append(FundRow(fund, row_opening, movement['received'], movement['spent'],
                                movement['transferred'], row_closing,
                                reserved.get(fund_id, ZERO), is_own, year_over))
        rows.sort(key=_row_order)

        unpaid = books.billed_unpaid(code, last)
        own_row = next((row for row in rows if row.is_own), None)
        if unpaid and own_row is not None:
            own_row.unpaid_bills = unpaid
            own_row.waiting_for_billed = sum((waits.get(bill.event.pk, ZERO) for bill in unpaid),
                                             ZERO)

        checkpoints = []
        anchor = books.anchor(code)
        for checkpoint in books.checkpoints.get(code, []):
            if first - ONE_DAY <= checkpoint.as_of <= year_end:
                checkpoints.append(CheckpointRow(
                    checkpoint, books.cash_on(code, checkpoint.as_of),
                    is_anchor=checkpoint is anchor))

        statement_ = AccountStatement(
            account, first, last, rows, unfiled_opening, unfiled_closing,
            books.cash_on(code, first - ONE_DAY), books.cash_on(code, last), checkpoints,
            books.funds.get(own_id))
        # An account no fund is held in and nothing has touched is a partition
        # code and nothing more; listing it would be a table of zeroes.
        if not statement_.is_empty or held_here:
            accounts.append(statement_)
    return Statement(fiscal_year, first, last, accounts, books, year_over, before_books=False)


# ---------------------------------------------------------------------------
# Closing a year
# ---------------------------------------------------------------------------

def _text(value):
    """ A figure as snapshot text, keeping "unknown" distinct from zero. """
    return None if value is None else str(value)


def snapshot(year):
    """
    A statement reduced to the figures a close records, as JSON-safe text.

    Both ends of the year, not only the closing. Cash is counted from the
    account's earliest Workday balance (see :meth:`Books.cash_on`), so which
    end a late line moves depends on where that anchor is. Counted forwards
    from an earlier balance, a June line imported after the close changes the
    closing figures. Counted backwards from the June 30 balance itself, it
    changes the year's *opening* instead -- which a snapshot of the closing
    alone would never notice.
    """
    out = {'first': year.first.isoformat(), 'last': year.last.isoformat(), 'accounts': {}}
    for account in year.accounts:
        out['accounts'][account.code] = {
            'opening_cash': _text(account.opening_cash),
            'cash': _text(account.closing_cash),
            'unfiled': str(account.unfiled_closing),
            'funds': {row.name: _text(row.closing) for row in account.rows},
            'opening_funds': {row.name: _text(row.opening) for row in account.rows},
        }
    return out


def drift(close, year):
    """
    What has changed in a closed year since it was closed.

    A list of ``(account code, what, closed at, now)``, empty when nothing has.
    Late imports and re-filed lines are the usual causes, and neither is wrong
    -- but a balance that moved after the year was signed off is something the
    Treasurer has to know about.
    """
    then = (close.snapshot or {}).get('accounts', {})
    now = snapshot(year)['accounts']
    changes = []
    for code in sorted(set(then) | set(now)):
        before, after = then.get(code, {}), now.get(code, {})
        pairs = [('Opening cash', before.get('opening_cash'), after.get('opening_cash')),
                 ('Cash', before.get('cash'), after.get('cash')),
                 ('Unsettled', before.get('unfiled'), after.get('unfiled'))]
        for key, suffix in (('opening_funds', ' at the start'), ('funds', '')):
            old_funds, new_funds = before.get(key, {}), after.get(key, {})
            pairs += [(name + suffix, old_funds.get(name), new_funds.get(name))
                      for name in sorted(set(old_funds) | set(new_funds))]
        for what, old, new in pairs:
            if _as_money(old) != _as_money(new):
                changes.append((code, what, _as_money(old), _as_money(new)))
    return changes


def _as_money(value):
    """ A snapshot figure back as money; a missing one is zero. """
    return money(value) if value not in (None, '') else ZERO


def year_end_proposals(year):
    """
    What closing this year would do, account by account.

    Two kinds of balance need an answer at June 30, and nothing else does:

    * a **budget overspend** -- spending beyond what SGA deposited has to come
      out of money that carries forward, so the default is to cover it from
      the account's own fund;
    * a **funding request still awaiting SGA** -- normally carried forward
      until SGA pays, but a reimbursement SGA has refused is a loss the
      account's own money absorbs, so the Treasurer may write some of it off.

    A budget balance left unspent needs no transfer: SGA takes it back with a
    Workday line of its own, and filing that line to the budget fund brings it
    to zero. Until then it shows as owed back.

    Returns ``[{'account', 'row', 'kind', 'amount'}]``.
    """
    proposals = []
    for account in year.accounts:
        if account.own_fund is None:
            continue
        for row in account.rows:
            if row.fund is None or row.is_own or row.closing is None:
                continue
            if row.behaviour == FundBehaviour.RETURNS and row.closing < 0:
                proposals.append({'account': account, 'row': row, 'kind': 'cover',
                                  'amount': -row.closing})
            elif row.behaviour == FundBehaviour.REIMBURSED and row.closing < 0:
                proposals.append({'account': account, 'row': row, 'kind': 'write_off',
                                  'amount': -row.closing})
    return proposals


def closed_years():
    """ ``{fiscal year: FiscalYearClose}`` for every year closed so far. """
    return {close.fiscal_year: close
            for close in FiscalYearClose.objects.select_related('closed_by')}


def fiscal_year_of_books_start():
    """ The fiscal year the books start in, or ``None`` with nothing imported. """
    start = books_start_date()
    return fiscal_year_for(start) if start else None

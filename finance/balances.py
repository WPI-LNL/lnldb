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

Nothing is carried from one year to the next by copying a closing balance into
an opening one. Every figure is a sum from the start of the books, so a line
imported in August for a June purchase corrects last year's closing balance
and this year's opening in the same moment. See
:class:`~finance.models.FiscalYearClose` for how a closed year notices.
"""
import datetime
from collections import defaultdict

from django.utils import timezone

from finance.models import (ZERO, BalanceCheckpoint, FiscalYearClose, FundBehaviour,
                            FundSource, FundTransfer, ParsedTransaction, PartitionCode,
                            TransactionStatus, WorkdayTransaction, account_own_funds,
                            books_start_date, fiscal_year_bounds, fiscal_year_for, money,
                            org_code_matches, partition_codes, worktag_value)

ONE_DAY = datetime.timedelta(days=1)


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

        codes = partition_codes()
        #: ``{line pk: (date, amount, account code)}``
        self.lines = {}
        self.unassigned_lines = 0
        for pk, date, amount, worktags in WorkdayTransaction.objects.values_list(
                'pk', 'accounting_date', 'net_amount', 'worktags_json'):
            code = account_code_for(worktags, codes)
            if code is None:
                self.unassigned_lines += 1
            self.lines[pk] = (date, money(amount), code)

        #: ``(line pk, fund pk, amount, is_refund)`` for every slice of a bank line.
        self.slices = [
            (line, fund, money(amount), refund is not None)
            for line, fund, amount, refund in ParsedTransaction.objects
            .filter(parent_transaction__isnull=False)
            .values_list('parent_transaction_id', 'fund_source_id', 'amount', 'refund_of_id')]

        #: ``(fund pk, amount, date)`` for every reservation still waiting.
        self.encumbrances = [
            (fund, money(amount), date)
            for fund, amount, date in ParsedTransaction.objects
            .filter(parent_transaction__isnull=True, status=TransactionStatus.PENDING)
            .values_list('fund_source_id', 'amount', 'effective_date')]

        self.transfers = list(FundTransfer.objects.select_related(
            'account', 'from_fund', 'to_fund'))

        self.checkpoints = defaultdict(list)
        for checkpoint in BalanceCheckpoint.objects.select_related('account').order_by('as_of'):
            self.checkpoints[checkpoint.account.code].append(checkpoint)

        self.latest_line_date = max((date for date, _, _ in self.lines.values()), default=None)

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
        fund on an account with no fund of its own. ``opening_cash`` is what
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
        for line, fund, amount, _ in self.slices:
            date, _, line_code = self.lines[line]
            if line_code != code or not (self.start <= date <= day):
                continue
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
        """
        own = self.own_fund_ids.get(code)
        out = defaultdict(lambda: {'received': ZERO, 'spent': ZERO, 'transferred': ZERO})
        for line, fund, amount, is_refund in self.slices:
            date, _, line_code = self.lines[line]
            if line_code != code or not (first <= date <= last):
                continue
            row = out[fund if fund is not None else own]
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
        ``{fund pk: amount}`` reserved and not yet charged, for funds held in
        this account. An encumbrance has no bank line, so it belongs to the
        account its fund is held in.
        """
        out = defaultdict(lambda: ZERO)
        for fund, amount, date in self.encumbrances:
            source = self.funds.get(fund)
            if source is None or source.account is None or source.account.code != code:
                continue
            if date <= day:
                out[fund] -= amount
        return out


# ---------------------------------------------------------------------------
# One year, laid out
# ---------------------------------------------------------------------------

class FundRow(object):
    """ One fund's line on an account's statement. """

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
    def available(self):
        """ What can still be spent: the balance less what is reserved. """
        return self.closing - self.encumbered if self.closing is not None else None

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
    """ The account's own money first, then the funds in their admin order. """
    fund = row.fund
    return (not row.is_own, fund.sort_order if fund else 999, row.name)


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

        held_here = {pk for pk, fund in books.funds.items()
                     if fund.account_id == account.pk and fund.is_active}
        fund_ids = set(opening) | set(closing) | set(moved) | set(reserved) | held_here
        rows = []
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
                                            movement['spent'])):
                continue
            rows.append(FundRow(fund, row_opening, movement['received'], movement['spent'],
                                movement['transferred'], row_closing,
                                reserved.get(fund_id, ZERO), is_own, year_over))
        rows.sort(key=_row_order)

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

    Both ends of the year, not only the closing. With Workday's June 30 balance
    entered, the closing figures are pinned to it, and a June line imported
    after the close shows up as the year having *opened* differently -- which
    a snapshot of the closing alone would never notice.
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
                 ('Unfiled', before.get('unfiled'), after.get('unfiled'))]
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

"""
Fund balances: what each fund holds, the Workday figures that prove it, and the
year-end close.

Every figure on these pages is worked out by :mod:`finance.balances`; the views
here only collect the three things a person has to supply -- what Workday says
an account holds, money moved between funds, and the answers a year-end close
needs -- and write them down.
"""
import reversion
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from finance import balances
from finance.filters import filter_context, get_filter_state
from finance.forms import (BalanceCheckpointForm, FundTransferForm, OpeningBalancesForm,
                           YearCloseForm)
from finance.models import (ZERO, BalanceCheckpoint, FiscalYearClose, FundSource,
                            FundTransfer, books_start_date, current_fiscal_year,
                            fiscal_year_bounds, fiscal_year_for, money, own_fund_for_account)

ONE_DAY = balances.ONE_DAY


def _balances_url(fiscal_year):
    """ The balance page for one year. """
    return '%s?fy=%s' % (reverse('finance:balances'), fiscal_year)


def _year_transfers(books, year):
    """
    The transfers that belong on this year's page, newest first.

    Ordinary and year-end transfers by their date; the opening split on the
    year the books start in, since that is the year it is the opening of.
    """
    first, last = fiscal_year_bounds(year.fiscal_year)
    out = []
    for transfer in books.transfers:
        if transfer.kind == FundTransfer.OPENING:
            if books.start is not None and fiscal_year_for(books.start) == year.fiscal_year:
                out.append(transfer)
        elif first <= transfer.date <= last:
            out.append(transfer)
    return sorted(out, key=lambda t: (t.date, t.pk), reverse=True)


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def balance_sheet(request):
    """
    Every account's funds for the selected year, and what Workday says.

    The year is the filter bar's; "All years" shows the current one, because a
    balance is always a balance *on* some day. The partition switch does not
    apply: a fund's money is the account's whatever it was spent on.
    """
    state = get_filter_state(request)
    fiscal_year = state.fiscal_year or current_fiscal_year()
    books = balances.Books()
    year = balances.statement(fiscal_year, books=books)
    close = (FiscalYearClose.objects.filter(fiscal_year=fiscal_year)
             .select_related('closed_by').first())

    context = {
        'h2': "Fund Balances",
        'fin_page': 'balances',
        'year': year,
        'close': close,
        'changes': balances.drift(close, year) if close else [],
        'transfers': _year_transfers(books, year),
        'can_close': (year.year_over and close is None and year.accounts
                      and request.user.has_perm('finance.close_fiscalyear')),
        'books_start_year': (fiscal_year_for(books.start) if books.start else None),
    }
    context.update(filter_context(request))
    return render(request, 'finance/balances.html', context)


# ---------------------------------------------------------------------------
# What a person supplies
# ---------------------------------------------------------------------------

def _render_form(request, form, title, intro, cancel_year):
    """ The one small form page every balance input shares. """
    context = {
        'h2': title,
        'fin_page': 'balances',
        'form': form,
        'intro': intro,
        'cancel_url': _balances_url(cancel_year),
    }
    context.update(filter_context(request))
    return render(request, 'finance/balance_form.html', context)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
def checkpoint_new(request):
    """ Write down what Workday says an account holds. """
    initial = {}
    account = request.GET.get('account')
    if account and account.isdigit():
        initial['account'] = account
    as_of = request.GET.get('as_of')
    if as_of:
        initial['as_of'] = as_of

    form = BalanceCheckpointForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        with reversion.create_revision():
            reversion.set_user(request.user)
            checkpoint = form.save(commit=False)
            checkpoint.entered_by = request.user
            checkpoint.save()
        messages.success(request, "Recorded %s." % checkpoint)
        return HttpResponseRedirect(_balances_url(fiscal_year_for(checkpoint.as_of)))
    return _render_form(
        request, form, "Record a Workday balance",
        "Copy an account's balance out of Workday, with the day it is for. The first one "
        "entered for an account is where its cash is counted from; every later one checks "
        "that no line is missing from the ledger.",
        current_fiscal_year())


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def checkpoint_delete(request, pk):
    """ Remove a Workday balance that was copied down wrong. """
    checkpoint = get_object_or_404(BalanceCheckpoint, pk=pk)
    year = fiscal_year_for(checkpoint.as_of)
    label = str(checkpoint)
    checkpoint.delete()
    messages.success(request, "Removed %s." % label)
    return HttpResponseRedirect(_balances_url(year))


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
def transfer_new(request):
    """ Move money from one fund to another inside one account. """
    books_start = books_start_date()
    form = FundTransferForm(request.POST or None, books_start=books_start)
    if request.method == 'POST' and form.is_valid():
        with reversion.create_revision():
            reversion.set_user(request.user)
            transfer = form.save(commit=False)
            transfer.kind = FundTransfer.TRANSFER
            transfer.created_by = request.user
            transfer.full_clean()
            transfer.save()
        messages.success(request, "Moved $%s from %s to %s." % (
            money(transfer.amount), transfer.from_fund, transfer.to_fund))
        return HttpResponseRedirect(_balances_url(transfer.fiscal_year))
    return _render_form(
        request, form, "Move money between funds",
        "For money changing funds without leaving the account, which Workday never sees "
        "-- paying for something out of Legacy that was charged to the budget, say. The "
        "account's total does not change; one fund goes down by exactly what the other "
        "goes up.",
        current_fiscal_year())


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def transfer_delete(request, pk):
    """
    Take back a transfer recorded by hand.

    Opening splits and year-end transfers are refused here: they belong to the
    page that wrote them, which replaces or reopens them as a set.
    """
    transfer = get_object_or_404(FundTransfer, pk=pk)
    year = transfer.fiscal_year
    if transfer.kind != FundTransfer.TRANSFER:
        messages.error(request, "That transfer was made by %s. Change it there." % (
            "the opening balances page" if transfer.kind == FundTransfer.OPENING
            else "closing FY%s -- reopen the year to take it back" % str(year)[-2:]))
        return HttpResponseRedirect(_balances_url(year))
    with reversion.create_revision():
        reversion.set_user(request.user)
        transfer.delete()
    messages.success(request, "Transfer removed.")
    return HttpResponseRedirect(_balances_url(year))


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
def opening_balances(request):
    """
    What each account held when the books started, and which fund held it.

    Saving replaces the opening split outright rather than adding to it, so the
    page always shows exactly what the opening is.
    """
    start = books_start_date()
    if start is None:
        messages.warning(request, "Import a Workday export first: the books start with the "
                                  "first line imported.")
        return HttpResponseRedirect(reverse('finance:balances'))
    night_before = start - ONE_DAY

    books = balances.Books()
    accounts = []
    skipped = []
    for account in books.accounts:
        own = own_fund_for_account(account.code)
        if own is None:
            skipped.append(account)
            continue
        funds = [fund for fund in FundSource.objects.active().filter(account=account)
                 .order_by('sort_order', 'name') if fund.pk != own.pk]
        existing = {}
        for transfer in books.transfers:
            if transfer.kind != FundTransfer.OPENING or transfer.account_id != account.pk:
                continue
            amount = money(transfer.amount)
            if transfer.to_fund_id != own.pk:
                existing[transfer.to_fund_id] = existing.get(transfer.to_fund_id, ZERO) + amount
            if transfer.from_fund_id != own.pk:
                existing[transfer.from_fund_id] = (existing.get(transfer.from_fund_id, ZERO)
                                                   - amount)
        cash = next((c.balance for c in books.checkpoints.get(account.code, [])
                     if c.as_of == night_before), None)
        accounts.append((account, own, funds, cash, existing))

    form = OpeningBalancesForm(request.POST or None, books_start=start, accounts=accounts)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic(), reversion.create_revision():
            reversion.set_user(request.user)
            for account, own, cash, amounts in form.section_values():
                if cash is not None:
                    BalanceCheckpoint.objects.update_or_create(
                        account=account, as_of=night_before,
                        defaults={'balance': cash, 'entered_by': request.user,
                                  'note': 'Opening balance'})
                FundTransfer.objects.filter(account=account,
                                            kind=FundTransfer.OPENING).delete()
                for fund, amount in amounts.items():
                    if not amount:
                        continue
                    source, target = (own, fund) if amount > 0 else (fund, own)
                    FundTransfer.objects.create(
                        account=account, date=start, amount=abs(amount), from_fund=source,
                        to_fund=target, kind=FundTransfer.OPENING, created_by=request.user,
                        description="Opening balance: %s held $%s when the books started"
                                    % (fund, amount))
        messages.success(request, "Opening balances saved.")
        return HttpResponseRedirect(_balances_url(fiscal_year_for(start)))

    context = {
        'h2': "Opening balances",
        'fin_page': 'balances',
        'form': form,
        'books_start': start,
        'night_before': night_before,
        'skipped': skipped,
        'cancel_url': _balances_url(fiscal_year_for(start)),
    }
    context.update(filter_context(request))
    return render(request, 'finance/balance_opening.html', context)


# ---------------------------------------------------------------------------
# The year-end close
# ---------------------------------------------------------------------------

def _year_checklist(year):
    """
    What is still open in a year, as ``[(ok, text, link)]``.

    None of it blocks the close -- Workday posts into a year for weeks after it
    ends, and the Treasurer may close knowing that -- but each is something a
    closing balance would be wrong about.
    """
    from finance.models import ParsedTransaction, TransactionStatus, WorkdayTransaction

    first, last = fiscal_year_bounds(year.fiscal_year)
    lines = WorkdayTransaction.objects.filter(accounting_date__range=(first, last))
    unreconciled = lines.unreconciled().count()
    pending_encumbrances = ParsedTransaction.objects.filter(
        parent_transaction__isnull=True, status=TransactionStatus.PENDING,
        effective_date__range=(first, last)).count()
    queue = '%s?fy=%s' % (reverse('finance:queue'), year.fiscal_year)
    ledger = '%s?fy=%s' % (reverse('finance:ledger'), year.fiscal_year)

    out = [
        (unreconciled == 0,
         "Every line in FY%s is filed and settled" % str(year.fiscal_year)[-2:]
         if not unreconciled else
         "%s line%s still in the queue. Unfiled money shows as its own row and belongs to "
         "no fund." % (unreconciled, '' if unreconciled == 1 else 's'),
         None if not unreconciled else queue),
        (pending_encumbrances == 0,
         "No encumbrances left open" if not pending_encumbrances else
         "%s encumbrance%s from this year still open. They carry into next year as "
         "reserved money." % (pending_encumbrances, '' if pending_encumbrances == 1 else 's'),
         None if not pending_encumbrances else ledger),
    ]
    for account in year.accounts:
        at_end = [row for row in account.checkpoints if row.checkpoint.as_of == last]
        if not account.cash_known:
            out.append((False, "No Workday balance for %s yet, so its own money cannot be "
                               "worked out. Enter its June 30 balance below." % account.code,
                        None))
        elif not at_end:
            out.append((False, "No Workday balance for %s on %s to check the ledger against. "
                               "Enter it below." % (account.code, date_format(last, 'M j, Y')),
                        None))
        elif at_end[0].difference:
            out.append((False, "%s: Workday and the ledger differ by $%s on %s -- lines are "
                               "missing or a balance was copied wrong."
                        % (account.code, at_end[0].difference, date_format(last, 'M j, Y')),
                        None))
        else:
            out.append((True, "%s agrees with Workday on %s" % (
                account.code, date_format(last, 'M j, Y')), None))
    return out


@login_required
@permission_required('finance.close_fiscalyear', raise_exception=True)
def close_year(request, fiscal_year):
    """
    Close one finished year: check it, square it, and record what it looked like.

    Squaring means the two balances that cannot simply carry forward: a budget
    overspend is covered from the account's own money, and a reimbursement SGA
    will not pay is written off to it. Everything else carries by arithmetic.
    """
    fiscal_year = int(fiscal_year)
    first, last = fiscal_year_bounds(fiscal_year)
    if last >= timezone.localdate():
        messages.error(request, "FY%s has not ended yet." % str(fiscal_year)[-2:])
        return HttpResponseRedirect(_balances_url(fiscal_year))
    if FiscalYearClose.objects.filter(fiscal_year=fiscal_year).exists():
        messages.info(request, "FY%s is already closed." % str(fiscal_year)[-2:])
        return HttpResponseRedirect(_balances_url(fiscal_year))

    books = balances.Books()
    year = balances.statement(fiscal_year, books=books)
    if not year.accounts:
        messages.error(request, "There is nothing to close in FY%s." % str(fiscal_year)[-2:])
        return HttpResponseRedirect(_balances_url(fiscal_year))

    proposals = balances.year_end_proposals(year)
    form = YearCloseForm(request.POST or None, year=year, proposals=proposals)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic(), reversion.create_revision():
            reversion.set_user(request.user)
            close = FiscalYearClose.objects.create(
                fiscal_year=fiscal_year, closed_by=request.user,
                notes=form.cleaned_data.get('notes') or '')
            for account, balance in form.workday_balances():
                BalanceCheckpoint.objects.update_or_create(
                    account=account.account, as_of=last,
                    defaults={'balance': balance, 'entered_by': request.user,
                              'note': 'Entered when closing FY%s' % str(fiscal_year)[-2:]})
            for account, fund, amount, description in form.transfers():
                FundTransfer.objects.create(
                    account=account.account, date=last, amount=amount,
                    from_fund=account.own_fund, to_fund=fund, kind=FundTransfer.YEAR_END,
                    description=description, fiscal_year_close=close,
                    created_by=request.user)
            # Recorded after the transfers, so the snapshot is the year as closed.
            close.snapshot = balances.snapshot(balances.statement(fiscal_year))
            close.save()
        messages.success(request, "FY%s closed." % str(fiscal_year)[-2:])
        return HttpResponseRedirect(_balances_url(fiscal_year))

    context = {
        'h2': "Close FY%s" % str(fiscal_year)[-2:],
        'fin_page': 'balances',
        'year': year,
        'form': form,
        'proposals': proposals,
        'checklist': _year_checklist(year),
        'cancel_url': _balances_url(fiscal_year),
    }
    context.update(filter_context(request))
    return render(request, 'finance/close_year.html', context)


@login_required
@permission_required('finance.close_fiscalyear', raise_exception=True)
@require_POST
def reopen_year(request, fiscal_year):
    """
    Undo a close: forget its snapshot and take back its year-end transfers.

    The Workday balances entered while closing stay. They are what Workday
    said, and that does not stop being true because the year was reopened.
    """
    close = get_object_or_404(FiscalYearClose, fiscal_year=int(fiscal_year))
    with transaction.atomic(), reversion.create_revision():
        reversion.set_user(request.user)
        count = close.transfers.count()
        close.delete()
    messages.success(request, "FY%s reopened%s." % (
        str(close.fiscal_year)[-2:],
        "; its %s year-end transfer%s were taken back" % (count, '' if count == 1 else 's')
        if count else ''))
    return HttpResponseRedirect(_balances_url(close.fiscal_year))

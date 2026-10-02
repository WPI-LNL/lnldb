"""
The Forecast tab: where LNL's money is heading, whether it can afford
something, and the past the forecast learns from.

The figures are :mod:`finance.forecast` and :mod:`finance.history`, laid out.
The only things saved here are what only a person can supply: planned
purchases, and corrections to how a line from before the books start is read.
"""
from collections import OrderedDict

import reversion
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from finance import forecast, history
from finance.balances import Books
from finance.filters import filter_context
from finance.forms import HistoryOverrideForm, PlannedPurchaseForm, WhatIfForm
from finance.models import (ZERO, HistoryKind, HistoryOverride, PartitionCode, PlannedPurchase,
                            WorkdayTransaction, books_start_date, fiscal_year_bounds,
                            fiscal_year_for)


def _account(request):
    """ ``(account asked for, every account)``: the event account unless another is named. """
    accounts = list(PartitionCode.objects.order_by('code'))
    code = (request.GET.get('account') or '').strip()
    chosen = next((a for a in accounts if a.code == code), None)
    if chosen is None:
        chosen = next((a for a in accounts if not a.is_projection), accounts[0] if accounts
                      else None)
    return chosen, accounts


def _context(request, page, **extra):
    """ What every page on the tab needs. """
    context = {'fin_page': 'forecast', 'forecast_page': page,
               'forecast_pages': [(key, label, name) for key, (label, name) in PAGES.items()]}
    context.update(extra)
    context.update(filter_context(request))
    return context


def _next_url(request, default):
    """ Where to go after a save: the page that asked, if it is one of ours. """
    target = request.POST.get('next') or request.GET.get('next')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return default


# ---------------------------------------------------------------------------
# The forecast
# ---------------------------------------------------------------------------

@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def forecast_page(request):
    """
    The forecast for one account, to the end of next fiscal year.

    ``?without=<part>`` (repeatable) leaves a part out, to see what it
    contributes; ``?account=<code>`` forecasts another account.
    """
    account, accounts = _account(request)
    without = [key for key in request.GET.getlist('without') if key in forecast.COMPONENTS]
    ledger, books = history.Ledger(), Books()
    result = forecast.project(account, without=without, ledger=ledger, books=books)
    tests = (forecast.back_test(ledger, account.code, share=result.share)
             if result.available else [])
    totals = result.totals_by_component() if result.available else {}

    # Each part is a link that switches it, keeping the others as they are.
    switches = []
    for key, label, included in result.components:
        params = request.GET.copy()
        others = [k for k in without if k != key]
        params.setlist('without', others + ([key] if included else []))
        switches.append({'key': key, 'label': label, 'included': included,
                         'url': '?' + params.urlencode(), 'total': totals.get(key)})
    params = request.GET.copy()
    context = _context(
        request, 'forecast',
        h2="Forecast",
        forecast=result,
        accounts=accounts,
        back_test=tests,
        back_test_summary=forecast.back_test_summary(tests),
        switches=switches,
        components=forecast.COMPONENTS,
        chart_data=result.chart() if result.available else None,
        querystring=params.urlencode(),
        can_edit=request.user.has_perm('finance.edit_subledger'),
        plans_count=PlannedPurchase.objects.filter(status__in=PlannedPurchase.COUNTED).count(),
    )
    return render(request, 'finance/forecast.html', context)


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def afford(request):
    """
    "Can we afford it?" -- the forecast run twice, without the purchase and
    with it, and the answer read against the minimum reserve.

    Asked by GET, so the answer is a link that can be sent to someone. Saving
    it to the planned purchases list is a separate POST to
    :func:`plan_edit`.
    """
    form = WhatIfForm(request.GET or None)
    answer = None
    if request.GET and form.is_valid():
        purchase = form.save(commit=False)
        account = getattr(purchase.fund_source, 'account', None)
        ledger, books = history.Ledger(), Books()
        before = forecast.project(account, ledger=ledger, books=books)
        after = forecast.project(account, extra=[purchase], ledger=ledger, books=books)
        answer = {'purchase': purchase, 'before': before, 'after': after,
                  'saves': [(field, request.GET.get(field, '')) for field in form.fields]}
    context = _context(request, 'afford', h2="Can we afford it?", form=form, answer=answer,
                       can_edit=request.user.has_perm('finance.edit_subledger'))
    return render(request, 'finance/forecast_afford.html', context)


# ---------------------------------------------------------------------------
# Planned purchases
# ---------------------------------------------------------------------------

@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def plans(request):
    """ Everything LNL means to buy, the ones the forecast counts first. """
    purchases = list(PlannedPurchase.objects.select_related('fund_source', 'spend_category'))
    counted = [p for p in purchases if p.is_counted]
    context = _context(
        request, 'plans', h2="Planned purchases",
        counted=counted,
        others=[p for p in purchases if not p.is_counted],
        counted_total=sum((p.amount for p in counted), ZERO),
        can_edit=request.user.has_perm('finance.edit_subledger'))
    return render(request, 'finance/forecast_plans.html', context)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
def plan_edit(request, pk=None):
    """ Add a planned purchase, or change one. """
    purchase = get_object_or_404(PlannedPurchase, pk=pk) if pk else None
    form = PlannedPurchaseForm(request.POST or None, instance=purchase)
    if request.method == 'POST' and form.is_valid():
        with reversion.create_revision():
            reversion.set_user(request.user)
            saved = form.save(commit=False)
            if saved.created_by_id is None:
                saved.created_by = request.user
            saved.save()
        messages.success(request, "%s %s." % ("Saved" if pk else "Added", saved.name))
        return HttpResponseRedirect(_next_url(request, reverse('finance:plans')))
    context = _context(
        request, 'plans', h2="Change a planned purchase" if pk else "Plan a purchase",
        form=form, purchase=purchase, cancel_url=reverse('finance:plans'))
    return render(request, 'finance/forecast_plan_form.html', context)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def plan_delete(request, pk):
    """ Take a purchase off the list altogether. Marking it dropped keeps it on record. """
    purchase = get_object_or_404(PlannedPurchase, pk=pk)
    name = purchase.name
    with reversion.create_revision():
        reversion.set_user(request.user)
        purchase.delete()
    messages.success(request, "Removed %s." % name)
    return HttpResponseRedirect(reverse('finance:plans'))


# ---------------------------------------------------------------------------
# History: what the forecast learns from
# ---------------------------------------------------------------------------

def _matrix(rows, years, categories):
    """
    The year-by-year summary as table rows: ``[{'label', 'values', 'kind',
    'key'}]``, where ``values`` lines up with ``years``.
    """
    by_year = {row['year']: row for row in rows}

    def line(label, pick, kind='', key=''):
        return {'label': label, 'kind': kind, 'key': key,
                'values': [pick(by_year[year]) for year in years]}

    out = [line("Client billing", lambda r: r['billing'], 'in', 'billing'),
           line("SGA funding", lambda r: r['sga'], 'in', 'sga'),
           line("Other: transfers and gifts", lambda r: r['other'], 'in', 'other')]
    used = set()
    for row in rows:
        used.update(pk for pk, amount in row['spending'].items() if amount)
    ordered = sorted(used, key=lambda pk: (pk is None, getattr(categories.get(pk), 'sort_order', 0),
                                           str(categories.get(pk, ''))))
    for pk in ordered:
        category = categories.get(pk)
        out.append(line(category.name if category else "Not worked out",
                        lambda r, pk=pk: r['spending'].get(pk, ZERO), 'out',
                        'category-%s' % (pk or 'none')))
    out.append(line("Spending, all categories", lambda r: r['spent'], 'total', 'spent'))
    out.append(line("Net", lambda r: r['net'], 'total', 'net'))
    return out


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def history_page(request):
    """
    Every year on file, side by side, the way the forecast reads it -- history
    and the books alike -- with what Workday's balance works back to.
    """
    from finance.suggestions import unmapped_spend_categories

    account, accounts = _account(request)
    ledger = history.Ledger()
    categories = history.spending_categories()
    rows = history.year_summary(ledger, account.code) if account else []
    years = [row['year'] for row in rows]
    cash = history.june_cash(account.code, years) if account else {}
    start = books_start_date()
    old_lines = list(WorkdayTransaction.objects.before_books())
    corrected = HistoryOverride.objects.count()
    context = _context(
        request, 'history', h2="History",
        account=account, accounts=accounts,
        years=rows,
        matrix=_matrix(rows, years, categories),
        cash=[cash.get(year) for year in years],
        books_start=start,
        history_lines=len(old_lines),
        corrected=corrected,
        whole_years=set(ledger.whole_years(account.code, before=9999)) if account else set(),
        share=history.department_share(ledger.flows),
        unmapped=unmapped_spend_categories([t for t in old_lines if t.net_amount < 0]),
    )
    return render(request, 'finance/history.html', context)


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def history_year(request, fiscal_year):
    """
    One year's lines from before the books start, each with how it is read.
    ``?kind=`` and ``?category=`` narrow it to one row of the summary.
    """
    fiscal_year = int(fiscal_year)
    start = books_start_date()
    first, last = fiscal_year_bounds(fiscal_year)
    if start is None or first >= start:
        # A year in the books is filed, not read: the ledger shows it.
        return HttpResponseRedirect('%s?fy=%s' % (reverse('finance:ledger'), fiscal_year))
    ledger = history.Ledger()
    categories = history.spending_categories()
    kind = request.GET.get('kind') or ''
    category = request.GET.get('category') or ''
    lines = (WorkdayTransaction.objects.before_books()
             .filter(accounting_date__range=(first, last)).order_by('accounting_date', 'pk'))
    rows = []
    for txn in lines:
        reading = ledger.readings.get(txn.pk)
        if reading is None:
            continue
        if kind and reading.kind != kind:
            continue
        if category:
            wanted = None if category == 'none' else int(category) if category.isdigit() else -1
            if reading.kind != HistoryKind.SPENDING or reading.category != wanted:
                continue
        rows.append({'txn': txn, 'reading': reading,
                     'category': categories.get(reading.category)})
    narrowed = ''
    if kind:
        narrowed = HistoryKind(kind).label if kind in HistoryKind.values else kind
    elif category:
        found = categories.get(int(category)) if category.isdigit() else None
        narrowed = found.name if found else "Spending not worked out"
    context = _context(
        request, 'history', h2="FY%s history" % str(fiscal_year)[-2:],
        fiscal_year=fiscal_year, rows=rows, narrowed=narrowed,
        total=sum((row['txn'].net_amount for row in rows), ZERO),
        can_edit=request.user.has_perm('finance.edit_subledger'))
    return render(request, 'finance/history_year.html', context)


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def history_line(request, pk):
    """
    One line from before the books start: how it is read, and the
    Treasurer's correction to it. Saving an empty correction removes it.
    """
    txn = get_object_or_404(WorkdayTransaction, pk=pk)
    if not txn.is_history:
        raise Http404("That line is in the books: file it in the queue.")
    override = HistoryOverride.objects.filter(line=txn).first()
    can_edit = request.user.has_perm('finance.edit_subledger')
    form = HistoryOverrideForm(request.POST or None, instance=override)
    back = _next_url(request, reverse('finance:history-year',
                                      args=[fiscal_year_for(txn.accounting_date)]))
    if request.method == 'POST':
        if not can_edit:
            raise Http404
        if request.POST.get('clear') or (form.is_valid() and not _says_anything(form)):
            if override is not None:
                override.delete()
            messages.success(request, "%s is read from the line again." % txn.reference)
            return HttpResponseRedirect(back)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.line = txn
            saved.updated_by = request.user
            saved.save()
            messages.success(request, "Correction to %s saved." % txn.reference)
            return HttpResponseRedirect(back)
    reading = history.reading_for(txn, override)
    context = _context(
        request, 'history', h2="How %s is read" % txn.reference,
        txn=txn, reading=reading, estimate=reading.estimate or reading,
        override=override, form=form, can_edit=can_edit, back=back,
        categories=history.spending_categories())
    return render(request, 'finance/history_line.html', context)


def _says_anything(form):
    """ Whether a correction form changes anything at all. """
    data = form.cleaned_data
    return bool(data.get('kind') or data.get('spend_category') or data.get('leave_out')
                or (data.get('note') or '').strip())


#: The tab's own pages, for its second row of links.
PAGES = OrderedDict((
    ('forecast', ("Forecast", 'finance:forecast')),
    ('afford', ("Can we afford it?", 'finance:afford')),
    ('plans', ("Planned purchases", 'finance:plans')),
    ('history', ("History", 'finance:history')),
))

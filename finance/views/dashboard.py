"""
Page 1 -- the executive dashboard.

This module is deliberately thin. Every number on the page is produced by
:mod:`finance.calculators`; the view's whole job is to run the active filter
state through those calculators and reshape the results into the JSON blobs
Chart.js expects. If a figure looks wrong, the bug is almost certainly in the
calculator, not here.
"""
from decimal import Decimal

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Sum
from django.shortcuts import render

from finance.calculators import (cash_flow_by_month, client_type_breakdown, project_composition,
                                 revenue_by_client, revenue_rows, service_mix, spend_by_category)
from finance.filters import filter_context, get_filter_state
from finance.models import (FundingRequest, ParsedTransaction, TransactionStatus,
                            WorkdayTransaction, money)


def _doughnut(rows, label_key='label'):
    """
    Shape a calculator result for Chart.js.

    Decimals become floats here rather than in the template: ``json_script``
    serialises Decimal as a *string*, which Chart.js would silently plot as
    zero.
    """
    return {
        'labels': [str(row[label_key]) for row in rows],
        'data': [float(row['amount']) for row in rows],
        'colors': [row['color'] for row in rows],
    }


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def dashboard(request):
    """ Page 1: the executive dashboard. """
    state = get_filter_state(request)
    projection_flag = state.projection_flag

    # -- action banner: what still needs a human -----------------------------
    # Reconciliation state is resolved in SQL rather than by asking each row.
    unreconciled = list(state.apply_to_workday(WorkdayTransaction.objects.unreconciled()))
    pending_encumbrances = state.apply(
        ParsedTransaction.objects.filter(parent_transaction__isnull=True,
                                         status=TransactionStatus.PENDING)).count()

    # -- headline numbers ----------------------------------------------------
    entries = state.apply(ParsedTransaction.objects.all())
    revenue = money(entries.revenue().aggregate(t=Sum('amount'))['t'])
    expense = -money(entries.expenses().aggregate(t=Sum('amount'))['t'])

    # -- charts --------------------------------------------------------------
    fy, proj = state.fiscal_year, projection_flag

    categories = spend_by_category(fiscal_year=fy, is_projection=proj)
    cash_flow = cash_flow_by_month(fiscal_year=fy, is_projection=proj)

    # One enriched revenue pass feeds all three revenue widgets rather than
    # re-resolving the polymorphic events three times.
    rev_rows = revenue_rows(fiscal_year=fy, is_projection=proj)
    clients = revenue_by_client(rows=rev_rows)
    client_types = client_type_breakdown(rows=rev_rows)
    services = service_mix(rows=rev_rows)

    projects = project_composition(fiscal_year=fy, is_projection=proj)

    # -- funding request burndowns ------------------------------------------
    # with_totals() puts the request's own figures in SQL; with_lines() does
    # the same for each line's spend. Both are aggregating properties, so a
    # plain prefetch of the allocations would not have been read by either.
    fr_qs = FundingRequest.objects.filter(closed=False).with_totals().with_lines()
    if projection_flag is not None:
        fr_qs = fr_qs.filter(is_projection=projection_flag)
    if state.fiscal_year:
        fr_qs = fr_qs.filter(fiscal_year=state.fiscal_year)

    funding_requests = []
    for fr in fr_qs:
        lines = list(fr.line_items.all())
        funding_requests.append({
            'obj': fr,
            'lines': lines,
            'awarded': fr.total_awarded,
            'spent': fr.total_spent,
            'remaining': fr.total_remaining,
            'percent': fr.percent_spent,
            'overspent': fr.is_overspent,
        })

    context = {
        'h2': "Financial Dashboard",
        'fin_page': 'dashboard',
        'unreconciled_count': len(unreconciled),
        # Gross, not net: a $350 deposit and a $475 invoice are two pieces of
        # work, not $125 of it. Netting them would understate the queue.
        'unreconciled_total': sum((abs(t.unallocated_amount) for t in unreconciled),
                                  Decimal('0.00')),
        'pending_encumbrances': pending_encumbrances,
        'total_revenue': revenue,
        'total_expense': expense,
        'net_position': revenue - expense,
        'categories': categories,
        'category_total': sum((c['amount'] for c in categories), Decimal('0.00')),

        'cash_flow': cash_flow,
        'cash_flow_peak': max([r['revenue'] for r in cash_flow] +
                              [r['expense'] for r in cash_flow] + [Decimal('0.00')]),
        'clients': clients,
        'client_total': sum((c['amount'] for c in clients), Decimal('0.00')),
        # Bars are drawn relative to the biggest value so the leader fills the
        # track; the true share of total is shown as the percentage label.
        'client_max': max([c['amount'] for c in clients] + [Decimal('0.00')]),
        'client_types': client_types,
        'client_type_total': sum((c['amount'] for c in client_types), Decimal('0.00')),
        'client_type_shows': sum(c['shows'] for c in client_types),
        'services': services,
        'service_total': sum((s['amount'] for s in services), Decimal('0.00')),
        'projects': projects,
        'project_grand_total': sum((p['total'] for p in projects), Decimal('0.00')),
        'project_max': max([p['total'] for p in projects] + [Decimal('0.00')]),

        'chart_data': {
            'categories': _doughnut(categories),
            'client_types': _doughnut(client_types),
            'services': _doughnut(services),
            'cash_flow': {
                'labels': [r['label'] for r in cash_flow],
                'revenue': [float(r['revenue']) for r in cash_flow],
                'expense': [float(r['expense']) for r in cash_flow],
            },
        },

        'funding_requests': funding_requests,
        'can_edit': request.user.has_perm('finance.edit_subledger'),
        'can_import': request.user.has_perm('finance.import_workdaytransaction'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/dashboard.html', context)

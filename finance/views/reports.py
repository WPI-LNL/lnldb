"""
The Reports tab: the subledger's figures laid out to print and to download.

The reports are pure functions in :mod:`finance.reports`. This module only
works out what a request asks for -- the period, the side of the partition, a
fund -- and answers with the page, or with the same figures as CSV.
"""
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from finance import forecast, reports
from finance.filters import filter_context, get_filter_state
from finance.models import FundSource, PartitionCode, current_fiscal_year

#: The partition as a report's printed header says it.
PARTITION_WORDS = {True: 'Projection only', False: 'Event Production only'}


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def report_list(request):
    """ Every report, with what it answers and what period it takes. """
    context = {
        'h2': "Reports",
        'fin_page': 'reports',
        'reports': [{'slug': slug, 'title': title, 'summary': summary, 'takes': takes}
                    for slug, (title, summary, takes) in reports.REPORTS.items()],
    }
    context.update(filter_context(request))
    return render(request, 'finance/reports.html', context)


def csv_response(text, filename):
    """ ``text`` as a CSV download called ``filename``. """
    response = HttpResponse(text, content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="%s"' % filename
    return response


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def report(request, slug):
    """
    One report, for the filter bar's fiscal year and partition.

    ``?from=&to=`` reports on any dates instead of the year, for the reports
    that can; ``?fund=<slug>`` narrows income and spending to one fund;
    ``?by=term|year`` and ``?measure=events|value`` cut and count event
    activity; ``?account=`` and ``?without=`` choose the forecast's account
    and leave parts of it out; and ``?format=csv`` downloads it.
    """
    if slug not in reports.REPORTS:
        raise Http404
    title, summary, takes = reports.REPORTS[slug]
    state = get_filter_state(request)
    today = timezone.localdate()
    projection = state.projection_flag
    period_error = ''
    fund = None
    by = request.GET.get('by') if request.GET.get('by') in reports.TREND_GROUPINGS else 'term'
    measure = (request.GET.get('measure') if request.GET.get('measure') in reports.TREND_MEASURES
               else 'events')

    if takes == 'range':
        period, period_error = reports.parse_period(
            state.fiscal_year, request.GET.get('from'), request.GET.get('to'), today)
    if slug == 'income-and-spending':
        fund_slug = (request.GET.get('fund') or '').strip()
        fund = FundSource.objects.filter(slug=fund_slug).first() if fund_slug else None
        built = reports.income_and_spending(period, projection, fund)
    elif slug == 'fund-balances':
        # A balance is always a balance on some day, so "All years" means now.
        projection = None
        built = reports.fund_balances(state.fiscal_year or current_fiscal_year(), today)
    elif slug == 'events':
        built = reports.event_report(period, projection, today)
    elif slug == 'work-split':
        # The events app's work, not the ledger's entries: no side applies.
        projection = None
        built = reports.work_split(period, today)
    elif slug == 'activity':
        projection = None
        built = reports.activity_trends(state.fiscal_year or current_fiscal_year(), by, measure,
                                        today)
    elif slug == 'forecast':
        # The whole forecast from today -- the event account's, unless
        # ``?account=`` names another -- so neither the year nor the side
        # applies. ``?without=`` and ``?account=`` work as on the Forecast tab.
        projection = None
        account = PartitionCode.objects.filter(code=request.GET.get('account', '')).first()
        built = reports.forecast_report(forecast.project(
            account, today=today,
            without=[k for k in request.GET.getlist('without') if k in forecast.COMPONENTS]))
    elif slug == 'budget-draft':
        projection = None
        built = reports.budget_draft(today)
    else:
        built = reports.owed_to_lnl(projection, today)

    if request.GET.get('format') == 'csv':
        return csv_response(reports.as_csv(built), built.filename)

    params = request.GET.copy()
    params['format'] = 'csv'
    context = {
        'h2': title,
        'fin_page': 'reports',
        'report': built,
        'summary': summary,
        'takes': takes,
        'period_error': period_error,
        'range_from': (request.GET.get('from') or '').strip(),
        'range_to': (request.GET.get('to') or '').strip(),
        'fund': fund,
        'fund_choices': (FundSource.objects.active() if slug == 'income-and-spending'
                         else None),
        'partition_words': PARTITION_WORDS.get(projection, ''),
        'trend_by': by,
        'trend_measure': measure,
        'trend_groupings': reports.TREND_GROUPINGS.items(),
        'trend_measures': reports.TREND_MEASURES.items(),
        'csv_url': '?' + params.urlencode(),
        'printed_on': timezone.localtime(),
    }
    context.update(filter_context(request))
    return render(request, 'finance/report.html', context)

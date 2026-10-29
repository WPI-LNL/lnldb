"""
The Reports tab: the subledger's figures laid out to print and to download.

The reports are pure functions in :mod:`finance.reports`. This module only
works out what a request asks for -- the period, the side of the partition, a
fund, a funding request -- and answers with the page, or with the same figures
as CSV. The Funding Request Report Form also answers as the PDF SGA asks for,
made by :mod:`finance.frrf`.
"""
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from finance import frrf, reports
from finance.filters import filter_context, get_filter_state
from finance.models import FundingRequest, FundSource, current_fiscal_year

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


def report_form_request(request, fiscal_year):
    """
    ``(requests to offer, the one chosen)`` for the report form.

    The picker offers the filter bar's year's requests, and the one asked for
    by ``?request=`` whatever its year -- a request's own page links here, and
    SGA can still owe on last year's. With none asked for, it is the first SGA
    still owes on, as that is the one waiting for its form, or else the first.
    """
    requests = FundingRequest.objects.with_totals()
    offered = list(requests.filter(fiscal_year=fiscal_year) if fiscal_year else requests)
    raw = (request.GET.get('request') or '').strip()
    if raw:
        if not raw.isdigit():
            raise Http404
        chosen = get_object_or_404(requests, pk=raw)
        if chosen not in offered:
            offered.insert(0, chosen)
        return offered, chosen
    owed = [fr for fr in offered if fr.awaiting_sga > 0]
    return offered, (owed or offered or [None])[0]


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
    activity; ``?request=<pk>`` picks the funding request for its report
    form; and ``?format=csv`` downloads it. ``?format=pdf`` is the report
    form's PDF, receipts and all, which takes permission to view receipts.
    """
    if slug not in reports.REPORTS:
        raise Http404
    title, summary, takes = reports.REPORTS[slug]
    state = get_filter_state(request)
    today = timezone.localdate()
    projection = state.projection_flag
    period_error = ''
    fund = None
    fr_choices, fr = None, None
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
    elif slug == 'fr-report-form':
        # One request, whenever its spending was, so neither the year nor the
        # side narrows it; the year only decides which requests are offered.
        projection = None
        fr_choices, fr = report_form_request(request, state.fiscal_year)
        if fr is None:
            built = reports.Report(slug, title, 'No funding request', '', 'none', [], [],
                                   warnings=["There are no funding requests for %s."
                                             % ('FY%02d' % (state.fiscal_year % 100)
                                                if state.fiscal_year else 'any year')])
        elif request.GET.get('format') == 'pdf':
            if not request.user.has_perm('finance.view_subledger_receipts'):
                raise PermissionDenied
            form = frrf.gather(fr)
            response = HttpResponse(frrf.report_form_pdf(form, request),
                                    content_type='application/pdf')
            response['Content-Disposition'] = 'inline; filename="%s"' % form.filename
            return response
        else:
            built = reports.fr_report_form(fr)
    else:
        built = reports.owed_to_lnl(projection, today)

    if request.GET.get('format') == 'csv':
        return csv_response(reports.as_csv(built), built.filename)

    params = request.GET.copy()
    params['format'] = 'csv'
    pdf_url = ''
    if fr is not None:
        pdf_params = request.GET.copy()
        pdf_params['request'] = fr.pk
        pdf_params['format'] = 'pdf'
        pdf_url = '?' + pdf_params.urlencode()
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
        'fr': fr,
        'fr_choices': fr_choices,
        'pdf_url': pdf_url,
        'can_view_receipts': request.user.has_perm('finance.view_subledger_receipts'),
        'printed_on': timezone.localtime(),
    }
    context.update(filter_context(request))
    return render(request, 'finance/report.html', context)

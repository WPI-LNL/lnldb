"""
What each event made or lost.

The question a Treasurer gets asked after a big show -- "we hired a video wall
for that, did we come out ahead?" -- used to need the ledger, the events app and
a calculator. This page answers it for every event in the selected year at
once, from the entries linked to each event and the bill the events app holds.
The arithmetic, and the three decisions inside it, live in
:func:`finance.calculators.event_pnl_rows`.
"""
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render

from finance.calculators import EVENT_FLAGS, event_pnl_rows, event_pnl_totals
from finance.filters import filter_context, get_filter_state


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def event_pnl(request):
    """
    Every event in the selected year with its billed, received, cost and margin.

    ``?show=all`` adds events that were billed but have nothing linked yet. Off
    by default: until the queue's revenue is filed that is most of the year, and
    the events that cost money are what this page is for.
    """
    state = get_filter_state(request)
    show_all = request.GET.get('show') == 'all'
    flag = request.GET.get('flag')
    if flag not in EVENT_FLAGS:
        flag = None

    rows = event_pnl_rows(state.fiscal_year, state.projection_flag,
                          include_unlinked=show_all)
    # Totals describe the year, not whichever flag happens to be selected, so
    # they are taken before the rows are narrowed.
    totals = event_pnl_totals(rows)
    flag_counts = {key: sum(1 for r in rows if key in r['flag_keys']) for key in EVENT_FLAGS}
    if flag:
        rows = [r for r in rows if flag in r['flag_keys']]

    context = {
        'h2': "Event P&L",
        'fin_page': 'events',
        'rows': rows,
        'totals': totals,
        'show_all': show_all,
        'active_flag': flag,
        'flag_options': [(key, label, flag_counts[key]) for key, label in EVENT_FLAGS.items()],
    }
    context.update(filter_context(request))
    return render(request, 'finance/event_pnl.html', context)

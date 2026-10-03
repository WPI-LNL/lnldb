"""
What each event made or lost.

The question a Treasurer gets asked after a big show -- "we hired a video wall
for that, did we come out ahead?" -- used to need the ledger, the events app and
a calculator. This page answers it for every event in the selected year at
once, from the entries linked to each event and the bill the events app holds.
The arithmetic, and the three decisions inside it, live in
:func:`finance.calculators.event_pnl_rows`.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Max, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from finance.calculators import (EVENT_FLAGS, event_financials, event_pnl_rows,
                                 event_pnl_totals)
from finance.filters import filter_context, get_filter_state
from finance.models import ParsedTransaction, money


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def event_pnl(request):
    """
    Every event in the selected year with its billed, received, cost and margin.

    ``?show=all`` adds events that were billed but have nothing linked yet. Off
    by default: until the queue's revenue is filed that is most of the year, and
    the events that cost money are what this page is for. ``?flag=<key>`` shows
    only the events carrying one of :data:`~finance.calculators.EVENT_FLAGS`.
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
        # The events app's own permission is checked per event on the way in.
        'can_mark_paid': request.user.has_perm('finance.edit_subledger'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/event_pnl.html', context)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def mark_bill_paid(request, pk):
    """
    Mark an event's bill paid in lnldb, dated the day its payment arrived.

    The events app keeps its own "paid" date, set by hand when somebody
    noticed the money. The ledger knows when it actually arrived, so this
    offers to copy that across -- only when the payment filed against the
    event covers the bill, and only when a person presses the button. For a
    multi-bill, every show on the bill counts towards it, because one payment
    settles all of them.

    Needs the events app's own permission to mark a bill paid as well as the
    finance one: it is that app's record being changed.
    """
    from events.models import BaseEvent, MultiBilling

    event = get_object_or_404(BaseEvent, pk=pk)
    redirect_to = request.POST.get('next') or reverse('finance:events')
    if not url_has_allowed_host_and_scheme(redirect_to, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        redirect_to = reverse('finance:events')
    if not request.user.has_perm('events.bill_event', event):
        raise PermissionDenied
    if getattr(event, 'closed', False):
        messages.error(request, "%s is closed, so its bill cannot be changed." % event.event_name)
        return HttpResponseRedirect(redirect_to)

    figures = event_financials(event)
    bill = figures['bill']
    if bill is None:
        messages.error(request, "%s has no bill in lnldb to mark paid." % event.event_name)
        return HttpResponseRedirect(redirect_to)
    if bill.date_paid:
        messages.info(request, "The bill for %s was already marked paid on %s."
                      % (event.event_name, date_format(bill.date_paid, 'M j, Y')))
        return HttpResponseRedirect(redirect_to)

    shows = [event.pk]
    owed = figures['billed']
    if isinstance(bill, MultiBilling):
        shows = list(bill.events.values_list('pk', flat=True))
        owed = money(bill.amount)
    payments = ParsedTransaction.objects.revenue().filter(
        linked_event_id__in=shows, parent_transaction__isnull=False)
    received = money(payments.aggregate(t=Sum('amount'))['t'])
    if owed is None or received < owed:
        messages.error(request, "Only %s of the %s billed has been filed against %s, so the bill "
                                "is not marked paid. File the rest of the payment first."
                       % (money(received), money(owed or 0),
                          'the events on its multi-bill' if len(shows) > 1 else event.event_name))
        return HttpResponseRedirect(redirect_to)

    paid_on = payments.aggregate(last=Max('effective_date'))['last']
    bill.date_paid = paid_on
    bill.save(update_fields=['date_paid'])
    messages.success(request, "Marked the bill for %s paid on %s, the day the last of its "
                              "payment reached Workday."
                     % (event.event_name, date_format(paid_on, 'M j, Y')))
    return HttpResponseRedirect(redirect_to)

"""
Page 2 -- the spreadsheet ledger.

:data:`LEDGER_COLUMNS` lists every column the page can show and whether it is
shown by default; the column picker is built from it. The header and the
cells are written out in ``site_tmpl/finance/ledger.html``, keyed by the same
names (``data-col``), and ``SORTABLE`` says which columns sort. So adding
a column means an entry here, a ``<th>`` and a ``<td>`` in the template, an
entry in ``SORTABLE`` if it sorts, and a line in
:data:`LEDGER_CSV_COLUMNS` for the download. The bulk-action endpoint lives
here too, since it operates on exactly the rows the ledger's checkboxes select.

``?format=csv`` downloads every row the filters select rather than the page of
them on screen, with :data:`LEDGER_CSV_COLUMNS` -- every column, since a
spreadsheet is where hidden columns get used.
"""
import csv
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls.base import reverse
from django.views.decorators.http import require_POST

import reversion
from finance.filters import FilterState, filter_context, get_filter_state
from finance.forms import BulkActionForm
from finance.models import (FundSource, ParsedTransaction, ProjectTag, SpendCategory,
                            TransactionStatus, money)
from finance.reports import Period
from finance.views.reports import csv_response

# Every column the spreadsheet can show: ``(key, label, shown by default)``.
# The key matches ``data-col`` in the template. ledger.js remembers each
# viewer's own choice of columns in localStorage.
LEDGER_COLUMNS = (
    ('date', 'Date', True),
    ('description', 'Description', True),
    ('payee', 'Payee', True),
    ('amount', 'Amount', True),
    ('type', 'Type', True),
    ('status', 'Status', True),
    ('partition', 'Partition', False),
    ('event', 'Event', True),
    ('client_type', 'Client Type', False),
    ('services', 'Services', False),
    ('fund_source', 'Fund', True),
    ('spend_category', 'Spend Category', True),
    ('fr_line', 'FR Line', False),
    ('project', 'Project', True),
    ('workday_ref', 'Workday Ref', False),
    ('ledger_account', 'Ledger Acct', False),
    ('receipt', 'Receipt', False),
)


def _request_label(entry):
    """ The funding request an entry names, by line or as SGA's payment. """
    line = entry.fr_line_target
    request = line.funding_request if line is not None else entry.funding_request
    if request is None:
        return ''
    return ('%s %s' % (request.reference, request.name)).strip()


def _workday(entry, attribute):
    """ An attribute of the bank line behind an entry; blank for an encumbrance. """
    parent = entry.parent_transaction
    return getattr(parent, attribute, '') if parent is not None else ''


#: The download's columns: ``(heading, how to read it off an entry)``.
LEDGER_CSV_COLUMNS = (
    ('Date', lambda e: e.effective_date.isoformat() if e.effective_date else ''),
    ('Description', lambda e: e.description),
    ('Payee', lambda e: e.payee_label),
    ('Amount', lambda e: '%.2f' % money(e.amount)),
    ('Type', lambda e: e.get_entry_type_display()),
    ('Status', lambda e: e.get_status_display()),
    ('Partition', lambda e: 'Projection' if e.is_projection else 'Event Production'),
    ('Event', lambda e: e.linked_event.event_name if e.linked_event_id else ''),
    ('Client type', lambda e: e.client_type_display if e.linked_event_id else ''),
    ('Fund', lambda e: e.fund_source.name if e.fund_source_id else ''),
    ('Spend category', lambda e: e.lnl_spend_category.name if e.lnl_spend_category_id else ''),
    ('Revenue source',
     lambda e: e.non_event_revenue_type.name if e.non_event_revenue_type_id else ''),
    ('Funding request', _request_label),
    ('FR line', lambda e: e.fr_line_target.name if e.fr_line_target_id else ''),
    ('Project', lambda e: str(e.project_tag) if e.project_tag_id else ''),
    ('Workday reference', lambda e: _workday(e, 'reference')),
    ('Ledger account', lambda e: _workday(e, 'ledger_account')),
    ('Memo', lambda e: _workday(e, 'memo')),
    ('Note', lambda e: e.audit_explanation),
)


def _ledger_csv(entries, filename):
    """ ``entries`` as a CSV download, every column, in the order given. """
    out = io.StringIO()
    out.write('\ufeff')  # so Excel reads it as UTF-8; see finance.reports.as_csv
    writer = csv.writer(out)
    writer.writerow([heading for heading, _ in LEDGER_CSV_COLUMNS])
    for entry in entries.select_related('fund_source', 'lnl_spend_category',
                                        'non_event_revenue_type'):
        writer.writerow([read(entry) or '' for _, read in LEDGER_CSV_COLUMNS])
    return csv_response(out.getvalue(), filename)


SORTABLE = {
    'date': 'effective_date',
    'amount': 'amount',
    'status': 'status',
    'spend_category': 'lnl_spend_category__sort_order',
    'fund_source': 'fund_source__sort_order',
    'project': 'project_tag__name',
    'description': 'description',
}


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def ledger(request):
    """ Page 2: the high-density spreadsheet ledger. """
    state = get_filter_state(request)

    base = (ParsedTransaction.objects.select_related(
                'parent_transaction', 'project_tag', 'fr_line_target__funding_request',
                'funding_request', 'linked_event')
            .prefetch_related('linked_event__serviceinstance_set__service__category'))

    # One event's entries, from the event P&L or the event's own page. Every
    # year of them: a late-June show is billed in July, so its revenue and its
    # rental sit in different fiscal years, and a year filter would show half
    # an event. The partition still applies -- that is a question about the
    # entries, not about when they landed.
    event = _event_filter(request.GET.get('event'))
    if event is not None:
        qs = FilterState(None, state.partition).apply(base).filter(linked_event=event)
    else:
        qs = state.apply(base)

    # -- text search --------------------------------------------------------
    query = (request.GET.get('q') or '').strip()
    if query:
        qs = qs.filter(
            Q(description__icontains=query) |
            Q(audit_explanation__icontains=query) |
            Q(parent_transaction__supplier__icontains=query) |
            Q(parent_transaction__employee__icontains=query) |
            Q(parent_transaction__memo__icontains=query) |
            Q(parent_transaction__operational_transaction__icontains=query) |
            Q(linked_event__event_name__icontains=query) |
            Q(project_tag__name__icontains=query) |
            Q(project_tag__code__icontains=query))

    # -- facet filters ------------------------------------------------------
    status = request.GET.get('status')
    if status in dict(TransactionStatus.choices):
        qs = qs.filter(status=status)

    # Filtered by slug rather than primary key so links stay readable and
    # survive the rows being reordered or renamed in the admin.
    category = request.GET.get('category')
    if category:
        qs = qs.filter(lnl_spend_category__slug=category)

    fund = request.GET.get('fund')
    if fund:
        qs = qs.filter(fund_source__slug=fund)

    project = request.GET.get('project')
    if project and project.isdigit():
        qs = qs.filter(project_tag_id=int(project))

    kind = request.GET.get('kind')
    if kind == 'revenue':
        qs = qs.revenue()
    elif kind == 'expense':
        qs = qs.expenses()

    # -- sorting ------------------------------------------------------------
    sort = request.GET.get('sort', 'date')
    direction = request.GET.get('dir', 'desc')
    field = SORTABLE.get(sort.lstrip('-'), 'effective_date')
    order = ('-' if direction == 'desc' else '') + field
    qs = qs.order_by(order, '-pk')

    if request.GET.get('format') == 'csv':
        if event is not None:
            part = 'event-%s' % event.pk
        elif state.fiscal_year:
            part = Period(fiscal_year=state.fiscal_year).file_part
        else:
            part = 'all-years'
        return _ledger_csv(qs, 'lnl-ledger-%s.csv' % part)

    net_total = money(qs.aggregate(net=Sum('amount'))['net'])
    revenue_total = money(qs.revenue().aggregate(t=Sum('amount'))['t'])
    expense_total = -money(qs.expenses().aggregate(t=Sum('amount'))['t'])

    paginator = Paginator(qs, 100)
    page = paginator.get_page(request.GET.get('page'))

    # Preserve every filter except page when building pagination links.
    params = request.GET.copy()
    params.pop('page', None)

    context = {
        'h2': "Subledger",
        'fin_page': 'ledger',
        'page_obj': page,
        'columns': LEDGER_COLUMNS,
        'result_count': paginator.count,
        'net_total': net_total,
        'revenue_total': revenue_total,
        'expense_total': expense_total,
        'query': query,
        'sort': sort,
        'dir': direction,
        'querystring': params.urlencode(),
        'status_choices': TransactionStatus.choices,
        'category_choices': [(c.slug, c.name) for c in SpendCategory.objects.active()],
        'fund_choices': [(f.slug, f.name) for f in FundSource.objects.active()],
        'projects': ProjectTag.objects.filter(archived=False),
        'active_filters': {
            'status': status, 'category': category, 'fund': fund,
            'project': project, 'kind': kind,
        },
        'event_filter': event,
        'event_clear_querystring': _without(params, 'event'),
        'bulk_form': BulkActionForm(),
        'can_edit': request.user.has_perm('finance.edit_subledger'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/ledger.html', context)


def _event_filter(raw):
    """ The event an ``?event=<pk>`` names, or ``None`` for anything else. """
    from events.models import BaseEvent

    raw = (raw or '').strip()
    if not raw.isdigit():
        return None
    return BaseEvent.objects.filter(pk=int(raw)).first()


def _without(params, key):
    """ ``params`` as a querystring with ``key`` taken out. """
    params = params.copy()
    params.pop(key, None)
    return params.urlencode()


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def bulk_action(request):
    """ Backs the slide-up bulk action bar. """
    form = BulkActionForm(request.POST)
    redirect_to = request.POST.get('next') or reverse('finance:ledger')

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return HttpResponseRedirect(redirect_to)

    ids = form.selected_ids
    if not ids:
        messages.warning(request, "Nothing was selected.")
        return HttpResponseRedirect(redirect_to)

    action = form.cleaned_data['action']
    value = form.cleaned_data[action]
    entries = list(ParsedTransaction.objects.filter(pk__in=ids))

    # Expense routing on a revenue row is refused by a database constraint, so
    # without this a mixed selection takes the whole action down with a 500.
    # The fund is not expense routing: money coming in names one too.
    if action == 'lnl_spend_category':
        wrong_direction = [e for e in entries if e.is_revenue]
        if wrong_direction:
            messages.warning(
                request,
                "%s revenue entr%s skipped — a spend category is expense routing and cannot "
                "be filed against money coming in."
                % (len(wrong_direction), 'y was' if len(wrong_direction) == 1 else 'ies were'))
            entries = [e for e in entries if not e.is_revenue]

    if action == 'fund_source':
        # Changing the fund out from under an entry that names an FR line would
        # break the pairing the model insists on.
        # The same goes for SGA's payment for a request.
        pinned = [e for e in entries if e.fr_line_target_id or e.funding_request_id]
        if pinned:
            messages.warning(
                request,
                "%s entr%s skipped — they are charged to a funding request, or are SGA's "
                "payment for one, so the fund has to stay as it is."
                % (len(pinned), 'y was' if len(pinned) == 1 else 'ies were'))
            entries = [e for e in entries
                       if not (e.fr_line_target_id or e.funding_request_id)]

    if action == 'status' and value == TransactionStatus.SETTLED:
        # Settling in bulk still has to respect the balance rule, so anything
        # that doesn't add up is reported rather than silently skipped.
        blocked = []
        allowed = []
        for entry in entries:
            parent = entry.parent_transaction
            if parent is None or not parent.is_fully_allocated:
                blocked.append(entry)
            else:
                allowed.append(entry)
        if blocked:
            messages.warning(
                request,
                "%s entr%s left Pending — their bank lines are not fully allocated yet."
                % (len(blocked), 'y was' if len(blocked) == 1 else 'ies were'))
        entries = allowed

    if not entries:
        return HttpResponseRedirect(redirect_to)

    with reversion.create_revision():
        reversion.set_user(request.user)
        reversion.set_comment("Bulk %s via ledger" % action.replace('_', ' '))
        updated, refused = 0, []
        for entry in entries:
            setattr(entry, action, value)
            try:
                # Validate each row rather than trusting the selection: a bulk
                # action must never be the thing that writes an entry the rest
                # of the app would have rejected.
                entry.full_clean()
            except ValidationError as exc:
                refused.append((entry, exc))
                continue
            entry.save()
            updated += 1

    if updated:
        messages.success(request, "Updated %s entr%s." % (updated, 'y' if updated == 1 else 'ies'))
    for entry, exc in refused[:5]:
        messages.warning(request, "Entry #%s unchanged: %s"
                         % (entry.pk, '; '.join(m for msgs in exc.message_dict.values()
                                                for m in msgs)))
    if len(refused) > 5:
        messages.warning(request, "...and %s more the change would have invalidated."
                         % (len(refused) - 5))
    return HttpResponseRedirect(redirect_to)

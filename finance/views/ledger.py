"""
Page 2 -- the spreadsheet ledger.

Everything on this page is driven by :data:`LEDGER_COLUMNS`: the header row,
the sort links, the column picker and the CSV-ish copy behaviour all read from
that one tuple, so adding a column means editing it in a single place. The
bulk-action endpoint lives here too, since it operates on exactly the rows the
ledger's checkboxes select.
"""
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
from finance.filters import filter_context, get_filter_state
from finance.forms import BulkActionForm
from finance.models import (FundSource, ParsedTransaction, ProjectTag, SpendCategory,
                            TransactionStatus, money)

# Every column the spreadsheet can show. ``default`` drives the initial
# column-visibility state; the picker stores the rest in localStorage.
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

    qs = state.apply(
        ParsedTransaction.objects.select_related(
            'parent_transaction', 'project_tag', 'fr_line_target__funding_request', 'linked_event')
        .prefetch_related('linked_event__serviceinstance_set__service__category'))

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
        'bulk_form': BulkActionForm(),
        'can_edit': request.user.has_perm('finance.edit_subledger'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/ledger.html', context)


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
    if action in ('fund_source', 'lnl_spend_category'):
        wrong_direction = [e for e in entries if e.is_revenue]
        if wrong_direction:
            messages.warning(
                request,
                "%s revenue entr%s skipped — %s is expense routing and cannot be filed "
                "against money coming in."
                % (len(wrong_direction), 'y was' if len(wrong_direction) == 1 else 'ies were',
                   action.replace('_', ' ')))
            entries = [e for e in entries if not e.is_revenue]

    if action == 'fund_source':
        # Changing the fund out from under an entry that names an FR line would
        # break the pairing the model insists on.
        pinned = [e for e in entries if e.fr_line_target_id]
        if pinned:
            messages.warning(
                request,
                "%s entr%s skipped — they are charged to a funding request line, so the "
                "fund has to stay as it is."
                % (len(pinned), 'y was' if len(pinned) == 1 else 'ies were'))
            entries = [e for e in entries if not e.fr_line_target_id]

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

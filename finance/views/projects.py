"""
Page 5 -- the project tag explorer, plus the SGA Funding screens.

Project tags are an MPTT forest, so the sidebar here shows the whole tree with
rollup totals while the main pane shows one branch. Funding requests and
budgets share the module because they are the other half of the same question
-- a tag says what money was spent on, SGA's funding says what money was
promised for it.
"""
from decimal import Decimal

import reversion
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import F, Prefetch, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from finance.calculators import sga_receivables
from finance.filters import filter_context, get_filter_state
from finance.forms import (BudgetCategoryFormSet, FRLineItemFormSet, FundingRequestForm,
                           ProjectTagForm, kind_for)
from finance.models import (FRLineItem, FundingKind, FundingRequest, LineTotals,
                            ParsedTransaction, ProjectTag, budget_name, current_fiscal_year,
                            money, project_tag_costs)


def _tree_context(state, selected=None, rollup=None):
    """
    The left sidebar: the whole project forest with live rollup totals.

    Tree figures are deliberately *lifetime* rather than fiscal-year scoped --
    a project like NEL26 spans years by definition, and scoping the browser to
    one FY would hide most of what the explorer exists to show.

    Costs come from :func:`finance.models.project_tag_costs` in one pass rather
    than from ``node.total_cost()`` per row: this sidebar renders every tag
    there is, and asking each one separately made the page cost a pair of
    queries per project. The caller passes the map in when it has already
    built one, since it needs the same figures for the pane on the right.
    """
    nodes = ProjectTag.objects.filter(archived=False)
    if state.projection_flag is not None:
        nodes = nodes.filter(is_projection=state.projection_flag)

    if rollup is None:
        rollup = project_tag_costs()[1]

    # Resolved once rather than per row -- it was a query inside the loop.
    ancestors = set()
    if selected is not None:
        ancestors = set(selected.get_ancestors().values_list('pk', flat=True))

    tree = []
    for node in nodes:
        tree.append({
            'node': node,
            'depth': node.level,
            'cost': rollup.get(node.pk, Decimal('0.00')),
            'is_selected': selected is not None and node.pk == selected.pk,
            'is_ancestor': node.pk in ancestors,
        })
    return tree


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def project_explorer(request, pk=None):
    """
    Page 5: two-pane project explorer. Folder tree on the left, the filtered
    ledger for the selected node on the right.
    """
    state = get_filter_state(request)
    selected = get_object_or_404(ProjectTag, pk=pk) if pk is not None else None

    include_children = request.GET.get('children', '1') != '0'
    entries, total, children = [], Decimal('0.00'), []
    lifetime = Decimal('0.00')

    # One pass for the sidebar, the lifetime figure and the child list, all of
    # which ask the same question of overlapping sets of nodes.
    direct_costs, rollup_costs = project_tag_costs()

    if selected is not None:
        costs = rollup_costs if include_children else direct_costs
        lifetime = costs.get(selected.pk, Decimal('0.00'))

        qs = selected.rollup_transactions(include_descendants=include_children)
        qs = state.apply(qs).select_related(
            'parent_transaction', 'project_tag', 'linked_event',
            'fr_line_target__funding_request').order_by('-effective_date', '-pk')
        entries = list(qs)
        total = -money(qs.aggregate(t=Sum('amount'))['t'])

        for child in selected.get_children():
            children.append({'node': child,
                             'cost': rollup_costs.get(child.pk, Decimal('0.00'))})

    context = {
        'h2': "Project Explorer",
        'fin_page': 'projects',
        'tree': _tree_context(state, selected, rollup_costs),
        'selected': selected,
        'entries': entries,
        'total_cost': total,
        'lifetime_cost': lifetime,
        'children': children,
        'include_children': include_children,
        'print_mode': request.GET.get('print') == '1',
        'can_edit': request.user.has_perm('finance.manage_projecttag'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/projects.html', context)


@login_required
@permission_required('finance.manage_projecttag', raise_exception=True)
def project_edit(request, pk=None):
    """
    Create or rename a project tag.

    ``pk`` is ``None`` on the "new tag" route and set on the edit route; the
    two share a template because the only difference is the heading.
    """
    instance = get_object_or_404(ProjectTag, pk=pk) if pk is not None else None

    if request.method == 'POST':
        form = ProjectTagForm(request.POST, instance=instance)
        if form.is_valid():
            with reversion.create_revision():
                reversion.set_user(request.user)
                reversion.set_comment("Project tag saved")
                tag = form.save()
            messages.success(request, "Saved %s." % tag)
            return HttpResponseRedirect(reverse('finance:projects-detail', args=[tag.pk]))
    else:
        form = ProjectTagForm(instance=instance)

    context = {
        'h2': "New Project Tag" if instance is None else "Edit %s" % instance,
        'form': form,
        'instance': instance,
    }
    context.update(filter_context(request))
    return render(request, 'finance/project_form.html', context)


# ---------------------------------------------------------------------------
# SGA funding: funding requests and budgets
# ---------------------------------------------------------------------------

def budget_rows(state):
    """
    The Budget box: each budget in the filter, with its figures.

    The filter bar's side narrows the figures to that side's lines -- a
    budget's lines are each Event Production or Projection -- and leaves out a
    budget with no lines on it. What SGA deposited is the whole budget's
    whatever the side, since SGA deposits one sum.
    """
    budgets = FundingRequest.objects.budgets().with_totals().prefetch_related(
        Prefetch('line_items', queryset=FRLineItem.objects.with_spend()))
    if state.fiscal_year:
        budgets = budgets.filter(fiscal_year=state.fiscal_year)
    rows = []
    for budget in budgets:
        lines = list(budget.line_items.all())
        if state.projection_flag is not None:
            side = [line for line in lines if line.is_projection == state.projection_flag]
            if lines and not side:
                continue
            lines = side
        rows.append({'budget': budget, 'totals': LineTotals(lines)})
    return rows


def budget_groups(budget, lines):
    """
    A budget's lines nested under their categories, in the categories' order,
    each with its subtotals. A category with no lines yet is listed too: the
    Treasurer made it. Lines with no category come last.

    Returns ``[{'category', 'lines', 'totals'}]``; ``category`` is ``None``
    for the uncategorised group.
    """
    by_category = {}
    for line in lines:
        by_category.setdefault(line.category_id, []).append(line)
    groups = []
    for category in budget.budget_categories.all():
        members = by_category.pop(category.pk, [])
        groups.append({'category': category, 'lines': members, 'totals': LineTotals(members)})
    leftover = [line for members in by_category.values() for line in members]
    if leftover:
        leftover.sort(key=lambda line: (line.sort_order, line.pk))
        groups.append({'category': None, 'lines': leftover, 'totals': LineTotals(leftover)})
    return groups


@login_required
@permission_required('finance.view_fundingrequest', raise_exception=True)
def funding_list(request):
    """
    The SGA Funding tab: what SGA owes, every funding request for the
    selected year, and the year's budget, each with spend rolled up.

    ``with_totals()`` is what keeps this to a constant number of queries. The
    template asks every row for its approved, spent and remaining figures,
    and all three are aggregating properties -- so a plain
    ``prefetch_related('line_items__allocations')`` bought nothing here, since
    an aggregate never reads a prefetch cache. The totals are computed in SQL
    alongside the rows instead.
    """
    state = get_filter_state(request)
    qs = FundingRequest.objects.requests().with_totals()
    if state.fiscal_year:
        qs = qs.filter(fiscal_year=state.fiscal_year)
    if state.projection_flag is not None:
        qs = qs.filter(is_projection=state.projection_flag)

    context = {
        'h2': "SGA Funding",
        'fin_page': 'funding',
        'requests': qs,
        'budgets': budget_rows(state),
        # Across every year, whatever the filter says: SGA can owe on an FY26
        # request well into FY27, and that is exactly what this is for.
        'receivables': sga_receivables(),
        'can_edit': request.user.has_perm('finance.manage_fundingrequest'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/funding_list.html', context)


@login_required
@permission_required('finance.view_fundingrequest', raise_exception=True)
def funding_detail(request, pk):
    """
    One funding request or budget, line by line, with the entries charged to
    each line.

    The per-line dictionary is built here rather than in the template so that
    each property (``spent``, ``remaining``, ``percent_spent``) is evaluated
    exactly once -- they are computed, not stored, and several of them hit the
    database.

    ``with_lines()`` annotates each line's spend in SQL, which is what makes
    "evaluated exactly once" cheap rather than merely tidy: without it every
    one of those three properties aggregates, because an aggregate does not
    read a prefetch cache.
    """
    fr = get_object_or_404(FundingRequest.objects.with_totals().with_lines(), pk=pk)
    if fr.is_budget:
        return budget_detail(request, fr)

    lines = []
    for line in fr.line_items.all():
        lines.append({
            'obj': line,
            'spent': line.spent,
            'remaining': line.remaining,
            'percent': line.percent_spent,
            'overspent': line.is_overspent,
            'allocations': line.allocations.select_related(
                'parent_transaction', 'project_tag').order_by('-effective_date'),
        })

    context = {
        'h2': fr.name,
        'fin_page': 'funding',
        'fr': fr,
        'lines': lines,
        # SGA's own payments for the request: reimbursements, and anything it
        # took back.
        'payments': fr.sga_payments.select_related('parent_transaction')
                                   .order_by('-effective_date', '-pk'),
        'unreimbursed_since': fr.unreimbursed_since(),
        'can_edit': request.user.has_perm('finance.manage_fundingrequest'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/funding_detail.html', context)


def budget_detail(request, budget):
    """
    One budget: its figures, what SGA has deposited, and its lines grouped by
    category.

    A budget can run to a hundred lines, so the entries charged to them are
    fetched in one query and handed to each line, rather than asked of each
    line in turn as a funding request's page does.
    """
    lines = list(budget.line_items.all())
    entries = {}
    for entry in (ParsedTransaction.objects.filter(fr_line_target__funding_request=budget)
                  .select_related('parent_transaction', 'project_tag')
                  .order_by('-effective_date', '-pk')):
        entries.setdefault(entry.fr_line_target_id, []).append(entry)
    for line in lines:
        line.entries = entries.get(line.pk, [])

    context = {
        'h2': budget.name,
        'fin_page': 'funding',
        'fr': budget,
        'totals': LineTotals(lines),
        'sides': [('Event Production',
                   LineTotals([line for line in lines if not line.is_projection])),
                  ('Projection', LineTotals([line for line in lines if line.is_projection]))],
        'groups': budget_groups(budget, lines),
        'unnumbered': [line for line in lines if not line.number],
        # SGA's own payments for the budget: the deposit, and money returned.
        'payments': budget.sga_payments.select_related('parent_transaction')
                                       .order_by('-effective_date', '-pk'),
        'can_edit': request.user.has_perm('finance.manage_fundingrequest'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/budget_detail.html', context)


def _lines_in_order(instance):
    """
    The lines the edit form lists, in the order the request's page shows
    them: a budget's under its categories, in the categories' order.
    """
    lines = FRLineItem.objects.select_related('category')
    if instance is not None and instance.is_budget:
        return lines.order_by(F('category__sort_order').asc(nulls_last=True), 'category__name',
                              'sort_order', 'pk')
    return lines.order_by('sort_order', 'pk')


def _order_of(form):
    """ Where a line's row sits within its category, as the form says. """
    value = form['sort_order'].value()
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def category_blocks(formset, categories):
    """
    The line rows, nested under the category each belongs to, for the form.

    Each block is ``{'form', 'key', 'lines'}``: a category's form and the key
    its lines name it by, or ``None`` and ``''`` for the lines with no
    category, which always come last. A line names its category by key
    (:class:`finance.forms.FRLineItemForm`), so this works on a form sent
    back with errors as on a fresh one -- including for categories added on
    the page and not saved yet. A line naming a category that is not there
    any more joins the lines with none.
    """
    blocks = []
    if categories is not None:
        ordered = sorted(enumerate(categories.forms),
                         key=lambda pair: (_order_of(pair[1]), pair[0]))
        for _, form in ordered:
            if form['DELETE'].value():
                continue
            key = form['key'].value() or ''
            if not key and form.instance.pk is not None:
                key = str(form.instance.pk)
            blocks.append({'form': form, 'key': str(key), 'lines': []})
    by_key = {block['key']: block for block in blocks if block['key']}
    loose = {'form': None, 'key': '', 'lines': []}
    for index, form in enumerate(formset.forms):
        key = str(form['category_key'].value() or '')
        # Saved lines in their order, then new ones in the order they came:
        # the page only ever adds a line at the end of its category.
        place = (form.instance.pk is None, _order_of(form), index)
        by_key.get(key, loose)['lines'].append((place, form))
    blocks.append(loose)
    for block in blocks:
        block['lines'] = [form for _, form in sorted(block['lines'], key=lambda pair: pair[0])]
    return blocks


@login_required
@permission_required('finance.manage_fundingrequest', raise_exception=True)
def funding_edit(request, pk=None):
    """
    Edit a funding request or a budget: the header and its lines together.

    The formset is the interesting half: a request is meaningless without the
    lines that break it down, so both are validated before either is written.
    Formset errors are surfaced as messages because the line rows are rendered
    as a compact table with no room for per-field error text.

    A budget has one more formset, for its categories: added, renamed,
    reordered and removed on the same page, with each line nested under one.
    A line names its category by a key the page gives it (see
    :func:`category_blocks`), since a category added on the page has no pk
    until it is saved, so the categories are saved first and the lines are
    then nested under what each key turned out to be.
    """
    instance = get_object_or_404(FundingRequest, pk=pk) if pk is not None else None
    # The queue links here to add a request a memo quoted, and wants the row
    # back afterwards. Only ever a page on this site.
    next_url = request.GET.get('next') or ''
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()},
                                           require_https=request.is_secure()):
        next_url = ''
    lines = _lines_in_order(instance)
    existing_budget = None

    if request.method == 'POST':
        kind = kind_for(request.POST, instance)
        form = FundingRequestForm(request.POST, instance=instance)
        formset = FRLineItemFormSet(request.POST, instance=instance, kind=kind, queryset=lines)
        categories = None
        if kind == FundingKind.BUDGET and 'budget_categories-TOTAL_FORMS' in request.POST:
            categories = BudgetCategoryFormSet(request.POST, instance=instance,
                                               prefix='budget_categories')
        # Every part is validated before any is written, so a bad line cannot
        # leave the header saved and the lines rejected. Each is checked even
        # when an earlier one failed, so every error shows at once.
        valid = [form.is_valid(), formset.is_valid(),
                 categories is None or categories.is_valid()]
        if all(valid):
            with reversion.create_revision():
                reversion.set_user(request.user)
                reversion.set_comment("%s saved" % FundingKind(kind).label)
                fr = form.save()
                by_key = {'': None}
                if categories is not None:
                    categories.instance = fr
                    categories.save()
                    by_key = categories.by_key()
                formset.instance = fr
                formset.assign_categories(by_key)
                formset.save()
                if not fr.is_budget:
                    fr.line_items.update(number='', is_projection=False, category=None)
                    fr.budget_categories.all().delete()
            messages.success(request, "Saved %s." % fr.name)
            return HttpResponseRedirect(next_url or reverse('finance:fr-detail', args=[fr.pk]))
        for errors in formset.errors:
            for error in errors.values():
                messages.error(request, error)
        for error in formset.non_form_errors():
            messages.error(request, error)
        if categories is not None:
            for errors in categories.errors:
                for error in errors.values():
                    messages.error(request, error)
            for error in categories.non_form_errors():
                messages.error(request, error)
        if kind == FundingKind.BUDGET and 'fiscal_year' in form.errors:
            existing_budget = (FundingRequest.objects.budgets()
                               .filter(fiscal_year=form.data.get('fiscal_year') or 0)
                               .exclude(pk=instance.pk if instance is not None else None)
                               .first())
    else:
        if instance is None:
            wanted = request.GET.get('kind')
            kind = wanted if wanted in FundingKind.values else FundingKind.REQUEST
        else:
            kind = instance.kind
        # A new request can arrive pre-filled from the memo that quoted it:
        # the number, the name written after it, and the year the number says.
        # A new budget starts named for its year.
        initial = {}
        if instance is None:
            initial = {key: request.GET[key] for key in ('reference', 'name', 'fiscal_year')
                       if request.GET.get(key)}
            initial['kind'] = kind
            if kind == FundingKind.BUDGET:
                year = initial.get('fiscal_year') or current_fiscal_year()
                initial.setdefault('name', budget_name(year))
        form = FundingRequestForm(instance=instance, initial=initial)
        formset = FRLineItemFormSet(instance=instance, kind=kind, queryset=lines)
        categories = None

    # The categories are on the page whichever type it opens as, so switching
    # a new form to a budget has them to hand; a request's form simply hides
    # them.
    if categories is None:
        categories = BudgetCategoryFormSet(instance=instance, prefix='budget_categories')

    if instance is not None:
        h2 = "Edit %s" % instance.name
    else:
        h2 = "New Budget" if kind == FundingKind.BUDGET else "New Funding Request"
    context = {
        'h2': h2,
        'form': form,
        'formset': formset,
        'categories': categories,
        'blocks': category_blocks(formset, categories),
        'kind': kind,
        'is_budget': kind == FundingKind.BUDGET,
        'existing_budget': existing_budget,
        'instance': instance,
    }
    context.update(filter_context(request))
    return render(request, 'finance/funding_form.html', context)

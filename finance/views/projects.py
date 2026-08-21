"""
Page 5 -- the project tag explorer, plus the funding request screens.

Project tags are an MPTT forest, so the sidebar here shows the whole tree with
rollup totals while the main pane shows one branch. Funding requests share the
module because they are the other half of the same question -- a tag says what
money was spent on, a funding request says what money was promised for it.
"""
from decimal import Decimal

import reversion
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse

from finance.filters import filter_context, get_filter_state
from finance.forms import FRLineItemFormSet, FundingRequestForm, ProjectTagForm
from finance.models import FundingRequest, ProjectTag, money


def _tree_context(state, selected=None):
    """
    The left sidebar: the whole project forest with live rollup totals.

    Tree figures are deliberately *lifetime* rather than fiscal-year scoped --
    a project like NEL26 spans years by definition, and scoping the browser to
    one FY would hide most of what the explorer exists to show.
    """
    nodes = ProjectTag.objects.filter(archived=False)
    if state.projection_flag is not None:
        nodes = nodes.filter(is_projection=state.projection_flag)

    tree = []
    for node in nodes:
        tree.append({
            'node': node,
            'depth': node.level,
            'cost': node.total_cost(),
            'is_selected': selected is not None and node.pk == selected.pk,
            'is_ancestor': (selected is not None and selected.pk != node.pk
                            and node.pk in selected.get_ancestors().values_list('pk', flat=True)),
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

    if selected is not None:
        lifetime = selected.total_cost(include_descendants=include_children)

        qs = selected.rollup_transactions(include_descendants=include_children)
        qs = state.apply(qs).select_related(
            'parent_transaction', 'project_tag', 'linked_event',
            'fr_line_target__funding_request').order_by('-effective_date', '-pk')
        entries = list(qs)
        total = -money(qs.aggregate(t=Sum('amount'))['t'])

        for child in selected.get_children():
            children.append({'node': child, 'cost': child.total_cost()})

    context = {
        'h2': "Project Explorer",
        'fin_page': 'projects',
        'tree': _tree_context(state, selected),
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
# Funding requests
# ---------------------------------------------------------------------------

@login_required
@permission_required('finance.view_fundingrequest', raise_exception=True)
def funding_list(request):
    """
    Every funding request for the selected year, with spend rolled up.

    The prefetch matters: the template asks each request for its awarded and
    spent totals, which walk ``line_items`` and then the allocations under
    each line. Without it the page issues two queries per line item.
    """
    state = get_filter_state(request)
    qs = FundingRequest.objects.prefetch_related('line_items__allocations')
    if state.fiscal_year:
        qs = qs.filter(fiscal_year=state.fiscal_year)
    if state.projection_flag is not None:
        qs = qs.filter(is_projection=state.projection_flag)

    context = {
        'h2': "Funding Requests",
        'fin_page': 'funding',
        'requests': qs,
        'can_edit': request.user.has_perm('finance.manage_fundingrequest'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/funding_list.html', context)


@login_required
@permission_required('finance.view_fundingrequest', raise_exception=True)
def funding_detail(request, pk):
    """
    One funding request, line by line, with the entries charged to each line.

    The per-line dictionary is built here rather than in the template so that
    each property (``spent``, ``remaining``, ``percent_spent``) is evaluated
    exactly once -- they are computed, not stored, and several of them hit the
    database.
    """
    fr = get_object_or_404(FundingRequest.objects.prefetch_related('line_items__allocations'), pk=pk)

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
        'can_edit': request.user.has_perm('finance.manage_fundingrequest'),
    }
    context.update(filter_context(request))
    return render(request, 'finance/funding_detail.html', context)


@login_required
@permission_required('finance.manage_fundingrequest', raise_exception=True)
def funding_edit(request, pk=None):
    """
    Edit a funding request header and its line items together.

    The formset is the interesting half: a request is meaningless without the
    lines that break it down, so both are validated before either is written.
    Formset errors are surfaced as messages because the line rows are rendered
    as a compact table with no room for per-field error text.
    """
    instance = get_object_or_404(FundingRequest, pk=pk) if pk is not None else None

    if request.method == 'POST':
        form = FundingRequestForm(request.POST, instance=instance)
        formset = FRLineItemFormSet(request.POST, instance=instance)
        # Both halves are validated before either is written, so a bad line
        # cannot leave the request header saved and the lines rejected.
        if form.is_valid() and formset.is_valid():
            with reversion.create_revision():
                reversion.set_user(request.user)
                reversion.set_comment("Funding request saved")
                fr = form.save()
                formset.instance = fr
                formset.save()
            messages.success(request, "Saved %s." % fr.name)
            return HttpResponseRedirect(reverse('finance:fr-detail', args=[fr.pk]))
        for errors in formset.errors:
            for error in errors.values():
                messages.error(request, error)
    else:
        form = FundingRequestForm(instance=instance)
        formset = FRLineItemFormSet(instance=instance)

    context = {
        'h2': "New Funding Request" if instance is None else "Edit %s" % instance.name,
        'form': form,
        'formset': formset,
        'instance': instance,
    }
    context.update(filter_context(request))
    return render(request, 'finance/funding_form.html', context)

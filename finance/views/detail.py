"""
Page 4 -- one bank line, and the entries posted against it.

Two things make this page more than a template. The first is the audit trail:
django-reversion stores each save as an opaque field snapshot, so the helpers
here diff consecutive versions and translate database column names back into
the labels a Treasurer actually recognises. The second is splitting -- a single
Workday line frequently pays for several different things, and the formset
below is what carves it up.
"""
import reversion
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.serializers.base import DeserializationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from reversion.errors import RevertError
from reversion.models import Version

from finance.filters import filter_context
from finance.forms import AllocationForm, SplitFormSet
from finance.models import ParsedTransaction, WorkdayTransaction
from finance.suggestions import suggest_all


def _snapshot(version):
    """
    A version's field snapshot, or ``None`` if it can no longer be read.

    Reversion serialises each revision against the schema of the day, so a
    field that later changed shape leaves older snapshots undeserialisable --
    a routing column that became a foreign key stored 'sga_fr' where an id is
    now expected. Those revisions are history and cannot be re-recorded, so the
    trail degrades to "saved this entry" rather than taking the page down.
    """
    try:
        return version.field_dict
    except (RevertError, DeserializationError):
        return None


def _audit_trail(instance, limit=50):
    """
    Human-readable change history from django-reversion.

    Reversion stores a full field snapshot per revision, so the trail is built
    by diffing consecutive versions and reporting only what actually moved.
    """
    versions = list(Version.objects.get_for_object(instance)[:limit])
    entries = []
    # Keyed by *attname* as well as name: reversion snapshots a foreign key as
    # ``lnl_spend_category_id``, so a map keyed only by ``lnl_spend_category``
    # missed every relation and the trail read "Lnl Spend Category Id" -- the
    # column name, shown to someone who has only ever seen the field's label.
    field_labels = {}
    for field in instance._meta.get_fields():
        label = getattr(field, 'verbose_name', None)
        if not label:
            continue
        field_labels[field.name] = label.title()
        field_labels[getattr(field, 'attname', field.name)] = label.title()

    for index, version in enumerate(versions):
        previous = versions[index + 1] if index + 1 < len(versions) else None
        changes = []
        current_data = _snapshot(version)
        previous_data = _snapshot(previous) if previous is not None else None
        if previous_data is not None and current_data is not None:
            for key, new_value in current_data.items():
                if key in ('id', 'updated_on', 'created_on'):
                    continue
                old_value = previous_data.get(key)
                if old_value != new_value:
                    changes.append({
                        'field': field_labels.get(key, key.replace('_', ' ').title()),
                        'old': old_value,
                        'new': new_value,
                    })
        entries.append({
            'version': version,
            'user': version.revision.user,
            'date': version.revision.date_created,
            'comment': version.revision.get_comment(),
            'changes': changes,
            'is_creation': previous is None,
            'unreadable': current_data is None,
        })
    return entries


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def transaction_detail(request, pk):
    """
    Page 4: immutable Workday data locked on the left, editable subledger
    metadata and the split interface on the right.
    """
    txn = get_object_or_404(
        WorkdayTransaction.objects.prefetch_related('slices__project_tag'), pk=pk)
    can_edit = request.user.has_perm('finance.edit_subledger')

    if request.method == 'POST' and can_edit:
        formset = SplitFormSet(request.POST, request.FILES, instance=txn,
                               parent_transaction=txn)
        if formset.is_valid():
            with reversion.create_revision():
                reversion.set_user(request.user)
                reversion.set_comment("Split purchase across %s allocations"
                                      % len([f for f in formset.forms
                                             if f.cleaned_data and not f.cleaned_data.get('DELETE')]))
                entries = formset.save(commit=False)
                for entry in entries:
                    entry.parent_transaction = txn
                    if entry.created_by_id is None:
                        entry.created_by = request.user
                    if not entry.effective_date:
                        entry.effective_date = txn.accounting_date
                    entry.full_clean()
                    entry.save()
                for obj in formset.deleted_objects:
                    obj.delete()
            messages.success(request, "Split saved — the allocation balances to $0.00.")
            return HttpResponseRedirect(txn.get_absolute_url())
        else:
            for error in formset.non_form_errors():
                messages.error(request, error)
    else:
        formset = SplitFormSet(instance=txn, parent_transaction=txn)

    slices = list(txn.slices.select_related(
        'project_tag', 'fr_line_target__funding_request', 'linked_event').all())

    context = {
        'h2': "Transaction %s" % txn.reference,
        'txn': txn,
        'slices': slices,
        'formset': formset,
        'suggestions': suggest_all(txn),
        'unallocated': txn.unallocated_amount,
        'is_balanced': txn.is_fully_allocated,
        'can_edit': can_edit,
        'can_settle': request.user.has_perm('finance.settle_subledger'),
        'worktags': sorted((k.replace('_', ' ').title(), v)
                           for k, v in (txn.worktags_json or {}).items()),
    }
    context.update(filter_context(request))
    return render(request, 'finance/transaction_detail.html', context)


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def entry_detail(request, pk):
    """ Focused edit of a single allocation slice, with its audit trail. """
    entry = get_object_or_404(
        ParsedTransaction.objects.select_related(
            'parent_transaction', 'linked_event', 'project_tag',
            'fr_line_target__funding_request'), pk=pk)
    can_edit = request.user.has_perm('finance.edit_subledger')

    if request.method == 'POST' and can_edit:
        form = AllocationForm(request.POST, request.FILES, instance=entry,
                              parent_transaction=entry.parent_transaction)
        if form.is_valid():
            with reversion.create_revision():
                reversion.set_user(request.user)
                reversion.set_comment("Edited from the line item detail page")
                obj = form.save(commit=False)
                obj.full_clean()
                obj.save()
            messages.success(request, "Saved.")
            return HttpResponseRedirect(entry.get_absolute_url())
    else:
        form = AllocationForm(instance=entry, parent_transaction=entry.parent_transaction)

    context = {
        'h2': "Subledger Entry #%s" % entry.pk,
        'entry': entry,
        'txn': entry.parent_transaction,
        'form': form,
        'audit_trail': _audit_trail(entry),
        'can_edit': can_edit,
        'can_view_receipts': request.user.has_perm('finance.view_subledger_receipts'),
        'worktags': sorted((k.replace('_', ' ').title(), v) for k, v in
                           ((entry.parent_transaction.worktags_json or {}).items()
                            if entry.parent_transaction else [])),
    }
    context.update(filter_context(request))
    return render(request, 'finance/entry_detail.html', context)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
def entry_delete(request, pk):
    """
    Remove an allocation slice. The parent bank line is never touched.

    Only what LNL decided *about* the money is withdrawn. The Workday row is
    immutable bank truth and keeps its own value, which is why removing a slice
    returns that amount to the unallocated remainder rather than making it
    disappear.

    .. note::

       The deletion itself leaves no new version. ``_save_revision`` in
       django-reversion drops any version whose row no longer exists -- by
       design, since a version is a snapshot of something that is there -- so
       ``add_to_revision`` inside this block is silently discarded. What does
       survive is everything recorded *before* the deletion: the entry's
       history stays queryable through
       ``Version.objects.get_for_object_reference(ParsedTransaction, pk)``,
       which is how a removed allocation can still be accounted for.
    """
    entry = get_object_or_404(ParsedTransaction, pk=pk)
    parent = entry.parent_transaction

    if request.method == 'POST':
        with reversion.create_revision():
            reversion.set_user(request.user)
            reversion.set_comment("Allocation slice removed")
            entry.delete()
        messages.success(request, "Allocation removed. The Workday line itself is untouched.")
        return HttpResponseRedirect(
            parent.get_absolute_url() if parent else reverse('finance:ledger'))

    context = {
        'h2': "Remove allocation?",
        'entry': entry,
        'txn': parent,
    }
    context.update(filter_context(request))
    return render(request, 'finance/entry_confirm_delete.html', context)

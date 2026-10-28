"""
Page 4 -- one bank line and the entries posted against it, and one entry on
a page of its own.

Two things make these more than templates. The first is splitting, on the
bank line's page -- a single Workday line frequently pays for several
different things, and the formset below is what carves it up. A payment for
a multi-bill is split across its events here, and the page offers to mark
the bill paid when the split covers it. The second is the audit trail, on the
entry's page: django-reversion stores each save as an opaque field snapshot,
so the helpers here diff consecutive versions and translate database column
names back into the labels a Treasurer actually recognises.
"""
import reversion
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.serializers.base import DeserializationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils.formats import date_format
from reversion.errors import RevertError
from reversion.models import Version

from finance.billing import bill_closed, mark_paid_from_payments, payment_offer
from finance.calculators import bill_payments
from finance.filters import filter_context
from finance.forms import AllocationForm, SplitFormSet
from finance.models import MultiBilling, ParsedTransaction, WorkdayTransaction, money, own_fund_for_account
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
    bill_offer = None

    if request.method == 'POST' and can_edit:
        formset = SplitFormSet(request.POST, request.FILES, instance=txn,
                               parent_transaction=txn)
        if formset.is_valid():
            with reversion.create_revision():
                reversion.set_user(request.user)
                reversion.set_comment("Split purchase across %s entries"
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
            # It cannot be saved unless it balances, so it is finished: settled
            # now, as the queue settles a line it files whole. Left Pending for
            # someone without the permission, which keeps it in the queue.
            if request.user.has_perm('finance.settle_subledger'):
                # Fetched with its slices prefetched, so it still believes it
                # has the ones it had before this save.
                txn.refresh_from_db()
                txn.settle()
                messages.success(request, "Split saved and settled — the entries add up to the "
                                          "line, so it has left the queue.")
            else:
                messages.success(request, "Split saved — the entries add up to the line. It "
                                          "stays in the queue as Pending until someone who can "
                                          "settle it clicks Mark settled.")
            paid = _mark_paid_on_split(request, txn)
            if paid:
                messages.info(request, paid)
            return HttpResponseRedirect(txn.get_absolute_url())
        else:
            for error in formset.non_form_errors():
                messages.error(request, error)
            offered = request.POST.get('bill_offered', '')
            if offered.isdigit():
                bill_offer = _split_bill_offer(request, txn, MultiBilling.objects.filter(pk=offered).first())
    else:
        formset = SplitFormSet(instance=txn, parent_transaction=txn)
        multibill = _multibill_to_split(request, txn)
        if multibill is not None:
            shares = _multibill_rows(txn, multibill)
            # Laid out as unsaved rows to check, one per show. The POST builds
            # its formset without them, so what is saved is what was submitted.
            formset = SplitFormSet(instance=txn, parent_transaction=txn, initial=shares)
            formset.extra = len(shares)
            on_bill = len(multibill.events.all())
            across = ("the %s events" % on_bill if len(shares) == on_bill
                      else "%s of the %s events (the others come to $0)" % (len(shares), on_bill))
            messages.info(request, "Laid out across %s on %s, the multi-bill sent %s, "
                                   "each by its share. Check the amounts, then save."
                          % (across, multibill.display_name, date_format(multibill.date_billed, 'M j, Y')))
            bill_offer = _split_bill_offer(request, txn, multibill)

    slices = list(txn.slices.select_related(
        'project_tag', 'fr_line_target__funding_request', 'linked_event',
        'funding_request').all())

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
        'bill_offer': bill_offer,
        'worktags': sorted((k.replace('_', ' ').title(), v)
                           for k, v in (txn.worktags_json or {}).items()),
    }
    context.update(filter_context(request))
    return render(request, 'finance/transaction_detail.html', context)


def _split_bill_offer(request, txn, multibill):
    """
    The pre-ticked *Mark paid* box for a multi-bill whose payment this line
    is being split as, when filing it would cover the bill, or ``None``. Only
    for someone who can bill.
    """
    if multibill is None or not request.user.has_perm('events.bill_event'):
        return None
    return payment_offer(multibill, txn.net_amount, txn.accounting_date)


def _mark_paid_on_split(request, txn):
    """
    Mark the multi-bill paid when the split page's box was ticked, and say
    what happened, as a sentence or ``''``.

    Only when the split filed money against the bill's events and what has
    been filed against them now covers it, dated the day the last of the
    money arrived -- the rules the *Mark paid* form and the queue follow.
    """
    ticked = request.POST.get('mark_bill_paid', '')
    if not ticked.isdigit() or not request.user.has_perm('events.bill_event'):
        return ''
    bill = MultiBilling.objects.filter(pk=ticked).prefetch_related('events').first()
    if bill is None or bill.date_paid or bill_closed(bill):
        return ''
    shows = [event.pk for event in bill.events.all()]
    if not txn.slices.filter(linked_event_id__in=shows).exists():
        return ("%s was not marked paid, because none of this line was linked to its events."
                % bill.display_name)
    paid_on = mark_paid_from_payments(bill)
    if paid_on is None:
        received, _ = bill_payments(bill)
        return ("%s was not marked paid: $%s of its $%s has been received."
                % (bill.display_name, money(received), money(bill.amount)))
    return "Marked %s paid on %s." % (bill.display_name, date_format(paid_on, 'M j, Y'))


def _multibill_to_split(request, txn):
    """
    The multi-bill ``?multibill=`` asks to split this line across, or ``None``.

    Only for a deposit with nothing filed against it yet: laying the shares out
    over existing slices would ask the Treasurer to save a split that silently
    replaces what was already there.
    """
    raw = request.GET.get('multibill')
    if not raw or not raw.isdigit() or txn.net_amount <= 0:
        return None
    if txn.slices.exists():
        messages.warning(request, "This line already has entries. Undo them first to "
                                  "split it across a multi-bill.")
        return None
    return MultiBilling.objects.filter(pk=raw).prefetch_related('events').first()


def _multibill_rows(txn, multibill):
    """
    One unsaved split row per event on the bill, each with its share.

    Shares come from :func:`finance.calculators.multibill_shares`, the same
    split the event P&L uses, so each show is credited with what the P&L says
    it was billed. When the payment differs from the bill, the last show takes
    the difference, so the rows still add up to the bank line. A show whose
    share is $0 -- one SGA pays for, with nothing to charge -- gets no row: a
    slice cannot be $0, so its row could only be refused.
    """
    from finance.calculators import multibill_shares

    shares = multibill_shares(multibill)
    events = sorted(multibill.events.all(), key=lambda e: e.pk)
    fund = own_fund_for_account(txn.partition_code_label)
    rows, allotted = [], 0
    for index, event in enumerate(events):
        amount = shares.get(event.pk, 0)
        if index == len(events) - 1:
            amount = txn.net_amount - allotted
        allotted += amount
        rows.append({'amount': amount, 'description': event.event_name,
                     'linked_event': event.pk,
                     'fund_source': fund.pk if fund is not None else None})
    return [row for row in rows if row['amount']]


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
       adding the entry to the revision opened below would be silently
       discarded, which is why it is not tried. What does
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
            reversion.set_comment("Entry removed")
            entry.delete()
        messages.success(request, "Entry removed. The Workday line itself is untouched.")
        return HttpResponseRedirect(
            parent.get_absolute_url() if parent else reverse('finance:ledger'))

    context = {
        'h2': "Remove entry?",
        'entry': entry,
        'txn': parent,
    }
    context.update(filter_context(request))
    return render(request, 'finance/entry_confirm_delete.html', context)

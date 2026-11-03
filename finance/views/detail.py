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
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils.formats import date_format
from reversion.errors import RevertError
from reversion.models import Version

from finance.billing import bill_closed, bills_paid_from, mark_paid_from_payments, payment_offer, unpay_uncovered
from finance.calculators import bill_payments
from finance.filters import filter_context
from finance.forms import AllocationForm, SplitFormSet
from finance.models import (ZERO, MultiBilling, ParsedTransaction, TransactionStatus, WorkdayTransaction,
                            dollars, money, own_fund_for_account)
from finance.suggestions import suggest_all
from finance.views.ingest import _name_a_few, _put_back_on_encumbrance


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
        can_settle = request.user.has_perm('finance.settle_subledger')
        formset = SplitFormSet(request.POST, request.FILES, instance=txn,
                               parent_transaction=txn, can_settle=can_settle)
        if formset.is_valid():
            # Read from the database: SplitLineForm.clean() has set every row
            # to Pending, so that they are weighed together.
            before = list(txn.slices.all())
            was_settled = {entry.pk for entry in before if entry.status == TransactionStatus.SETTLED}
            paid = bills_paid_from(before)
            restored = {}
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
                    # Changing a settled entry doesn't unsettle it for someone
                    # who can't settle, as on its own page. Checked above as
                    # Pending, against the other rows' new amounts; the formset
                    # has made the whole line add up, which is all Settled asks.
                    if not can_settle and entry.pk in was_settled:
                        entry.status = TransactionStatus.SETTLED
                    entry.save()
                for obj in formset.deleted_objects:
                    if obj.encumbrance_id is None:
                        obj.delete()
                        continue
                    # As Undo does: the money goes back on the encumbrance it
                    # came from, rather than the encumbrance going with it.
                    # Fetched again, without what the deleted row had typed in.
                    entry = ParsedTransaction.objects.select_related('encumbrance').get(pk=obj.pk)
                    header = entry.encumbrance
                    restored[header] = restored.get(header, ZERO) + _put_back_on_encumbrance(entry)
                unpaid = unpay_uncovered(paid, request.user)
            # It cannot be saved unless it balances, so it is finished: settled
            # now, as the queue settles a line it files whole. Left Pending for
            # someone without the permission, which keeps it in the queue.
            if can_settle:
                # Fetched with its slices prefetched, so it still believes it
                # has the ones it had before this save.
                txn.refresh_from_db()
                txn.settle()
                messages.success(request, "Split saved and settled — the entries add up to the "
                                          "line, so it has left the queue.")
            elif not txn.slices.filter(status=TransactionStatus.PENDING).exists():
                messages.success(request, "Split saved — the entries add up to the line, and it "
                                          "stays settled.")
            elif was_settled:
                messages.success(request, "Split saved — the entries add up to the line. The "
                                          "entries that were settled stay settled; the rest stay "
                                          "in the queue as Pending until someone who can settle "
                                          "the line clicks Mark settled.")
            else:
                messages.success(request, "Split saved — the entries add up to the line. It "
                                          "stays in the queue as Pending until someone who can "
                                          "settle it clicks Mark settled.")
            if restored:
                messages.warning(request, "%s encumbered again on %s: the entries removed came from "
                                          "%s, so their money was put back rather than deleted."
                                 % (dollars(abs(sum(restored.values(), ZERO))),
                                    _name_a_few("“%s”" % header.description for header in restored),
                                    "it" if len(restored) == 1 else "them"))
            for note in unpaid:
                messages.warning(request, note)
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
        'linked_multibill__org', 'funding_request').prefetch_related('linked_multibill__events'))

    context = {
        'h2': "Transaction %s" % txn.reference,
        'txn': txn,
        'slices': slices,
        # Undo settling puts these back on their encumbrance rather than
        # deleting them, and the page says so before it is clicked.
        'from_encumbrance': any(entry.encumbrance_id for entry in slices),
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
    if not txn.slices.filter(Q(linked_event_id__in=shows) | Q(linked_multibill=bill)).exists():
        return ("%s was not marked paid, because none of this line was linked to it or its events."
                % bill.display_name)
    paid_on = mark_paid_from_payments(bill)
    if paid_on is None:
        received, _ = bill_payments(bill)
        return ("%s was not marked paid: %s of its %s has been received."
                % (bill.display_name, dollars(received), dollars(bill.amount)))
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

    The payment is shared by price (:func:`finance.calculators.split_by_price`),
    as a payment linked to the bill is (:func:`~finance.calculators.multibill_income`),
    so the rows add up to the bank line to the cent and each show's figures are
    the same either way. The whole bill paid gives each show what the P&L says
    it was billed; part of it gives each show its part, not the first shows
    their whole share and the last whatever is left, or less than nothing. A
    show whose share is $0 -- one SGA pays for, with nothing to charge -- gets
    no row: a slice cannot be $0, so its row could only be refused.
    """
    from finance.calculators import split_by_price

    shares = split_by_price(multibill, txn.net_amount)
    fund = own_fund_for_account(txn.partition_code_label)
    rows = []
    for event in sorted(multibill.events.all(), key=lambda e: e.pk):
        rows.append({'amount': shares.get(event.pk, 0), 'description': event.event_name,
                     'linked_event': event.pk,
                     'fund_source': fund.pk if fund is not None else None})
    return [row for row in rows if row['amount']]


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def entry_detail(request, pk):
    """ Focused edit of a single allocation slice, with its audit trail. """
    entry = get_object_or_404(
        ParsedTransaction.objects.select_related(
            'parent_transaction', 'linked_event', 'linked_multibill', 'project_tag',
            'fr_line_target__funding_request', 'refund_of'), pk=pk)
    can_edit = request.user.has_perm('finance.edit_subledger')

    if request.method == 'POST' and can_edit:
        # Before the form writes what was typed onto the entry.
        paid = bills_paid_from([entry])
        form = AllocationForm(request.POST, request.FILES, instance=entry,
                              parent_transaction=entry.parent_transaction)
        if form.is_valid():
            with reversion.create_revision():
                reversion.set_user(request.user)
                reversion.set_comment("Edited from the line item detail page")
                obj = form.save(commit=False)
                obj.full_clean()
                obj.save()
                unpaid = unpay_uncovered(paid, request.user)
            messages.success(request, "Saved.")
            for note in unpaid:
                messages.warning(request, note)
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
        'multibill_shares': _multibill_shares_of(entry),
    }
    context.update(filter_context(request))
    return render(request, 'finance/entry_detail.html', context)


def _multibill_shares_of(entry):
    """
    ``[(event, share)]`` of a multi-bill's payment, each event with what it is
    credited, as :func:`finance.calculators.multibill_income` shares it out.
    Empty for any other entry.
    """
    from finance.calculators import multibill_income

    if not entry.linked_multibill_id:
        return []
    shares = multibill_income(ParsedTransaction.objects.filter(pk=entry.pk))
    return sorted(((event, share) for _, event, share in shares),
                  key=lambda pair: (pair[0].datetime_start, pair[0].pk))


def _why_not_removable(request, entry):
    """ Why ``entry`` can't be removed by this person, or ``None`` if it can. """
    # The database won't orphan a refund, so its purchase stays until the
    # refund goes.
    if entry.refunds.exists():
        return "This purchase has a refund recorded against it. Remove the refund first."
    if (entry.status == TransactionStatus.SETTLED
            and not request.user.has_perm('finance.settle_subledger')):
        return "This entry is settled, and you don't have permission to unsettle it."
    return None


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

    Two things happen besides. An entry matched from an encumbrance goes
    back on it, as Undo puts it back, rather than taking the encumbered money
    with it. And a bill marked paid from this payment is marked unpaid again
    when what is left filed no longer covers it.

    A line of an encumbrance still waiting for its Workday charge has no bank
    line to go back to: removing it cancels that much of the encumbrance, so a
    purchase that fell through never has to be matched to get rid of it. When
    it was the encumbrance's last line, the encumbrance goes too, as its own
    *Delete* would have done.
    """
    entry = get_object_or_404(ParsedTransaction.objects.select_related('encumbrance'), pk=pk)
    parent = entry.parent_transaction
    blocked = _why_not_removable(request, entry)
    header = entry.encumbrance
    open_line = header is not None and parent is None

    if request.method == 'POST':
        if blocked:
            messages.error(request, blocked)
            return HttpResponseRedirect(reverse('finance:entry-delete', args=[entry.pk]))
        paid = bills_paid_from([entry])
        with transaction.atomic(), reversion.create_revision():
            reversion.set_user(request.user)
            reversion.set_comment("Encumbrance line removed" if open_line else "Entry removed")
            if open_line:
                entry.delete()
                header_gone = not header.lines.exists()
                if header_gone:
                    header.delete()
            elif header is None:
                entry.delete()
            else:
                restored = _put_back_on_encumbrance(entry)
            unpaid = unpay_uncovered(paid, request.user)
        if open_line:
            if header_gone:
                messages.success(request, "Deleted the encumbrance “%s”: %s is no longer encumbered."
                                 % (header.description, dollars(abs(money(entry.amount)))))
            else:
                messages.success(request, "Removed a line of %s from the encumbrance “%s”: it is no "
                                          "longer encumbered. The rest of the encumbrance stays."
                                 % (dollars(abs(money(entry.amount))), header.description))
        elif header is None:
            messages.success(request, "Entry removed. The Workday line itself is untouched.")
        else:
            messages.warning(request, "Entry removed, and its money put back on the encumbrance "
                                      "“%s”: %s is encumbered again. The Workday line itself is "
                                      "untouched." % (header.description, dollars(abs(restored))))
        for note in unpaid:
            messages.warning(request, note)
        return HttpResponseRedirect(
            parent.get_absolute_url() if parent else reverse('finance:ledger'))

    context = {
        'h2': "Remove entry?",
        'entry': entry,
        'txn': parent,
        'blocked': blocked,
        # An open encumbrance line: the other lines of its encumbrance that
        # removing this one leaves behind, matched or not.
        'open_line': open_line,
        'other_lines': header.lines.exclude(pk=entry.pk).count() if open_line else 0,
        'encumbered': dollars(abs(money(entry.amount))),
    }
    context.update(filter_context(request))
    return render(request, 'finance/entry_confirm_delete.html', context)

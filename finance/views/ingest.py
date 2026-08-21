"""
Page 3 -- the ingestion queue, where bank lines become ledger entries.

This is the busiest module in the app because it owns the whole intake path:
uploading a Workday export, confirming it, reconciling a line (singly or in
bulk), undoing that reconciliation, settling an encumbrance, and serving the
suggestion JSON the queue page fetches as you scroll. Uploads are two-step by
design -- the file is parsed and staged first so the confirmation page can
report an exact row count before anything is written.
"""
from decimal import Decimal

import reversion
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.views.decorators.http import require_POST

from finance.filters import filter_context, get_filter_state
from finance.forms import (BulkReconcileForm, EncumbranceForm, ReconcileForm,
                           WorkdayCSVUploadForm)
from finance.importers import (ImportError_, discard_staged, import_workday_export,
                               purge_stale_staged, read_staged, stage_upload)
from finance.models import ParsedTransaction, TransactionStatus, WorkdayTransaction  # NOQA
from finance.suggestions import (active_project_tags, active_suggestion_rules,
                                 suggest_all, suggest_refund_targets)

#: Where a staged upload's details live between the two halves of an import.
#: The session, not a hidden form field, so a token cannot be replayed by
#: anyone but the person who uploaded the file.
STAGED_SESSION_KEY = 'finance_staged_import'


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def queue(request):
    """
    Page 3: the ingestion queue.

    Upload zone on top, then a vertical list of imported-but-unreconciled bank
    lines, each with a routing form whose fields are chosen by the sign of the
    transaction.
    """
    state = get_filter_state(request)
    upload_form = WorkdayCSVUploadForm()
    can_edit = request.user.has_perm('finance.edit_subledger')

    unreconciled = list(
        state.apply_to_workday(WorkdayTransaction.objects.unreconciled())
        .order_by('-accounting_date', '-pk'))

    paginator = Paginator(unreconciled, 25)
    page = paginator.get_page(request.GET.get('page'))

    # Both loaded once for the whole page rather than per row.
    tags = active_project_tags()
    rules = active_suggestion_rules()

    rows = []
    filled = 0
    for txn in page.object_list:
        # Worked out once and handed to the form, which fills in the answers
        # that came straight out of the export and leaves the guesses as chips.
        suggestions = suggest_all(txn, tags=tags, rules=rules)
        form = ReconcileForm(parent_transaction=txn, prefix='txn%s' % txn.pk,
                             suggestions=suggestions)
        filled += len(form.autofilled)
        rows.append({
            'txn': txn,
            'form': form,
            'suggestions': suggestions,
            'is_revenue': txn.net_amount > 0,
            'partially_allocated': txn.slice_count > 0,
            # The seldom-used fields are folded away so a row reads as two
            # boxes and a button. Unfolded again for the lines that actually
            # have something in there: a project we found, a partition that is
            # not the ordinary one, or a crossing that has to be explained.
            'expanded': bool(txn.crossing_requires_reason
                             or txn.defaults_to_projection
                             or form.autofilled.get('project_tag')
                             or suggestions.get('project_tag')),
        })

    context = {
        'h2': "Ingestion Queue",
        'fin_page': 'queue',
        'upload_form': upload_form,
        'rows': rows,
        'page_obj': page,
        'queue_count': paginator.count,
        # Gross magnitude of outstanding work; see the note in views/dashboard.py.
        'queue_total': sum((abs(t.unallocated_amount) for t in unreconciled), Decimal('0.00')),
        'autofilled_count': filled,
        'can_import': request.user.has_perm('finance.import_workdaytransaction'),
        'can_edit': can_edit,
        'bulk_reconcile_form': BulkReconcileForm() if can_edit else None,
    }
    context.update(filter_context(request))
    return render(request, 'finance/queue.html', context)


def _report_import(request, result, dry_run=False):
    """ Turn an :class:`ImportResult` into the banner messages for the queue. """
    if dry_run:
        messages.info(request, "Preview only — nothing was saved. %s" % result.summary())
    elif result.created_count:
        messages.success(request, result.summary())
    else:
        messages.info(request, result.summary())

    if result.duplicate_count and not result.created_count:
        messages.info(request, "Every line in that file had already been imported.")

    for row in result.errors[:10]:
        messages.warning(request, "Line %s: %s" % (row.line_number, row.message))
    if result.error_count > 10:
        messages.warning(request, "...and %s more problem rows." % (result.error_count - 10))

    # A Workday spend category nothing maps is a category the Treasurer will
    # pick by hand on every line that carries it. One admin row ends that.
    unmapped = result.unmapped_spend_categories()
    if unmapped:
        messages.warning(
            request,
            "No spend category rule covers %s. Add one under Finance → Spend Category "
            "Suggestion Rules and those lines will fill themselves in: %s"
            % ("these Workday categories" if len(unmapped) > 1 else "this Workday category",
               ", ".join("%s (%s line%s)" % (name, count, '' if count == 1 else 's')
                         for name, count in unmapped[:8])))

    if result.unmapped_headers:
        messages.info(
            request, "Unrecognised columns were stored as worktags: %s"
            % ", ".join(h.replace('_', ' ').title() for h in result.unmapped_headers))


def _clear_staged(request):
    """ Drop whatever upload was waiting for confirmation, file and all. """
    staged = request.session.pop(STAGED_SESSION_KEY, None)
    if staged:
        discard_staged(staged.get('token'))
    return staged


@login_required
@permission_required('finance.import_workdaytransaction', raise_exception=True)
@require_POST
def upload(request):
    """
    First half of an import: parse the file and ask before writing anything.

    An import is the one action on this page that is awkward to walk back --
    every line it creates lands in the queue as work somebody now has to do,
    and undoing it means finding and deleting them by hand. It also happens
    once a month, from a file exported by a system nobody here controls, and
    the two ways it goes wrong are picking last month's export and picking a
    file that is not an export at all. Both are obvious the moment you see a
    count of new lines, and invisible before it.

    So nothing is written here. The file is parsed with ``dry_run``, staged in
    the file store, and its counts are put in front of the Treasurer;
    :func:`upload_confirm` runs the real import against the same bytes.
    """
    form = WorkdayCSVUploadForm(request.POST, request.FILES)
    redirect_to = reverse('finance:queue')

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return HttpResponseRedirect(redirect_to)

    upload_file = form.cleaned_data['csv_file']
    dry_run = form.cleaned_data.get('dry_run')

    # A second upload replaces the first rather than leaving it on disk.
    _clear_staged(request)
    purge_stale_staged()

    try:
        result = import_workday_export(upload_file, user=request.user,
                                       filename=upload_file.name, dry_run=True)
    except ImportError_ as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(redirect_to)

    # "Preview only" is already an explicit request to look and not touch, so
    # asking "are you sure?" about it would be asking the same question twice.
    if dry_run:
        _report_import(request, result, dry_run=True)
        return HttpResponseRedirect(redirect_to)

    # Nothing to confirm: with no new lines the button does nothing either way,
    # and a confirmation screen offering to add zero rows is just a detour.
    if not result.created_count:
        _report_import(request, result)
        return HttpResponseRedirect(redirect_to)

    token = stage_upload(upload_file)
    request.session[STAGED_SESSION_KEY] = {
        'token': token,
        'filename': upload_file.name,
    }

    context = {
        'h2': "Confirm import",
        'fin_page': 'queue',
        'filename': upload_file.name,
        'created_count': result.created_count,
        'duplicate_count': result.duplicate_count,
        'error_count': result.error_count,
        'errors': result.errors[:5],
        'more_errors': max(0, result.error_count - 5),
        # Enough of the file to recognise it as the right one, without
        # reprinting a 253-line export on a confirmation screen.
        'preview_rows': [r.preview for r in result.created[:8]],
        'preview_more': max(0, result.created_count - 8),
        'net_total': sum((r.preview.get('net_amount') or Decimal('0.00')
                          for r in result.created), Decimal('0.00')),
    }
    context.update(filter_context(request))
    return render(request, 'finance/import_confirm.html', context)


@login_required
@permission_required('finance.import_workdaytransaction', raise_exception=True)
@require_POST
def upload_confirm(request):
    """ Second half of an import: the Treasurer said yes, so write the rows. """
    redirect_to = reverse('finance:queue')
    staged = request.session.get(STAGED_SESSION_KEY) or {}

    if request.POST.get('cancel'):
        _clear_staged(request)
        messages.info(request, "Import cancelled — nothing was added.")
        return HttpResponseRedirect(redirect_to)

    handle = read_staged(staged.get('token'))
    if handle is None:
        # Staged files expire, and a confirmation left open overnight is
        # exactly the one that should not quietly import itself in the morning.
        _clear_staged(request)
        messages.error(request, "That upload is no longer waiting to be imported. "
                                "Upload the file again.")
        return HttpResponseRedirect(redirect_to)

    try:
        result = import_workday_export(handle, user=request.user,
                                       filename=staged.get('filename', ''))
    except ImportError_ as exc:
        _clear_staged(request)
        messages.error(request, str(exc))
        return HttpResponseRedirect(redirect_to)

    _clear_staged(request)
    _report_import(request, result)
    return HttpResponseRedirect(redirect_to)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def reconcile(request, pk):
    """
    Save the inline routing form for one bank line in the queue.

    Answers XHR with JSON so the queue page can settle one row without
    reloading. Reloading is what it used to do, and it threw away whatever the
    Treasurer had already typed into the other rows on screen -- the queue is
    designed to be worked down a screenful at a time, so that was expensive.

    The plain-POST path is kept intact underneath: without JavaScript the form
    still submits, redirects and reports through the messages framework.
    """
    txn = get_object_or_404(WorkdayTransaction, pk=pk)
    form = ReconcileForm(request.POST, parent_transaction=txn, prefix='txn%s' % txn.pk)
    redirect_to = request.POST.get('next') or reverse('finance:queue')
    wants_json = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if not form.is_valid():
        if wants_json:
            return JsonResponse({
                'ok': False,
                'reference': txn.reference,
                # Keyed by field so the page can put each message beside the
                # input that caused it rather than in a banner up the top.
                'errors': {name: [str(e) for e in errors]
                           for name, errors in form.errors.items()},
            }, status=400)
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, "%s: %s" % (txn.reference, error))
        return HttpResponseRedirect(redirect_to)

    with reversion.create_revision():
        reversion.set_user(request.user)
        reversion.set_comment("Reconciled from the ingestion queue")
        entry = form.save(commit=False)
        entry.created_by = request.user
        entry.full_clean()
        entry.save()

    # A single full-value slice is complete by definition, so settle it now and
    # save the Treasurer a second click.
    settled = txn.is_fully_allocated and request.user.has_perm('finance.settle_subledger')
    if settled:
        txn.settle()
        message = "%s reconciled and settled." % txn.reference
    else:
        message = "%s allocated." % txn.reference

    if wants_json:
        txn.refresh_from_db()
        return JsonResponse({
            'ok': True,
            'reference': txn.reference,
            'message': message,
            'settled': settled,
            # False when a partial split leaves work behind, so the row stays.
            'done': txn.is_fully_allocated,
            'unallocated': str(txn.unallocated_amount),
        })

    messages.success(request, message)
    return HttpResponseRedirect(redirect_to)


@login_required
@permission_required('finance.view_subledger', raise_exception=True)
def suggestions_json(request, pk):
    """ Auto-suggest payload for the badge UI, fetched lazily by the queue page. """
    txn = get_object_or_404(WorkdayTransaction, pk=pk)
    data = suggest_all(txn)
    payload = {'kind': data['kind'],
               'default_partition': txn.default_partition,
               'crossing_requires_reason': txn.crossing_requires_reason}

    payload['warning'] = data.get('warning', '')

    for key in ('spend_category', 'fund_source', 'project_tag', 'fr_line_target',
                'linked_event'):
        suggestion = data.get(key)
        payload[key] = None if suggestion is None else {
            'value': str(suggestion.value),
            'label': suggestion.label,
            'confidence': suggestion.confidence,
            'reason': suggestion.reason,
            # True when the export said so and the form has already filled it
            # in; False when this is ours to offer and theirs to accept.
            'is_lookup': suggestion.is_lookup,
        }

    if txn.net_amount > 0:
        payload['refund_targets'] = [{
            'value': str(entry.pk),
            'label': "%s — %s" % (entry.description or entry.parent_transaction.payee, entry.amount),
        } for entry in suggest_refund_targets(txn)]

    return JsonResponse(payload)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
def encumbrance(request, pk=None):
    """ Log (or edit) a pending purchase that hasn't hit the bank feed yet. """
    instance = None
    if pk is not None:
        instance = get_object_or_404(ParsedTransaction, pk=pk, parent_transaction__isnull=True)

    if request.method == 'POST':
        form = EncumbranceForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            with reversion.create_revision():
                reversion.set_user(request.user)
                reversion.set_comment("Encumbrance logged" if instance is None
                                      else "Encumbrance updated")
                entry = form.save(commit=False)
                if instance is None:
                    entry.created_by = request.user
                entry.full_clean()
                entry.save()
            messages.success(request, "Encumbered $%s. It will stay Pending until the matching "
                                      "Workday line is imported." % abs(entry.amount))
            return HttpResponseRedirect(reverse('finance:ledger'))
    else:
        form = EncumbranceForm(instance=instance)

    context = {
        'h2': "Log a Pending Purchase" if instance is None else "Edit Encumbrance",
        'form': form,
        'instance': instance,
        'msg': "Reserve funds now so the budget reflects this spend before it clears Workday.",
    }
    context.update(filter_context(request))
    return render(request, 'finance/encumbrance.html', context)


@login_required
@permission_required('finance.settle_subledger', raise_exception=True)
@require_POST
def settle(request, pk):
    """ Mark every slice of a fully-allocated bank line as Settled. """
    txn = get_object_or_404(WorkdayTransaction, pk=pk)
    redirect_to = request.POST.get('next') or reverse('finance:queue')
    try:
        txn.settle()
    except Exception as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(redirect_to)
    messages.success(request, "%s settled." % txn.reference)
    return HttpResponseRedirect(redirect_to)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def unreconcile(request, pk):
    """
    Put a bank line back in the queue: delete its allocations, settled or not.

    Reconciling is a judgement call made twenty-five times in a sitting, and
    the moment you notice you filed one wrong is the moment right after you
    filed it. Until now the way back was to leave the queue, find the line in
    the ledger, open each slice and delete it one at a time through a
    confirmation page -- five navigations to undo one click, which in practice
    meant the wrong answer stayed.

    The Workday line itself is never touched. It is immutable bank truth: only
    what LNL decided *about* it is being withdrawn, which is why this is a
    deletion of slices and not an edit of anything.
    """
    txn = get_object_or_404(WorkdayTransaction, pk=pk)
    redirect_to = request.POST.get('next') or reverse('finance:queue')
    wants_json = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    slices = list(txn.slices.all())
    if not slices:
        message = "%s had nothing allocated to it." % txn.reference
        if wants_json:
            return JsonResponse({'ok': True, 'reference': txn.reference, 'message': message})
        messages.info(request, message)
        return HttpResponseRedirect(redirect_to)

    # A slice someone has since credited a refund against is load-bearing: the
    # refund exists to reverse *that* purchase, and the database refuses to
    # orphan it. Saying so beats a 500 from ProtectedError.
    refunded = [s for s in slices if s.refunds.exists()]
    if refunded:
        message = ("%s cannot be undone: %s of its allocations %s a refund filed against "
                   "%s. Remove the refund first."
                   % (txn.reference, len(refunded),
                      'has' if len(refunded) == 1 else 'have',
                      'it' if len(refunded) == 1 else 'them'))
        if wants_json:
            return JsonResponse({'ok': False, 'reference': txn.reference,
                                 'message': message}, status=409)
        messages.error(request, message)
        return HttpResponseRedirect(redirect_to)

    with reversion.create_revision():
        reversion.set_user(request.user)
        reversion.set_comment("Reconciliation undone — allocations removed")
        for entry in slices:
            entry.delete()

    txn.refresh_from_db()
    message = ("Undone. %s is back in the queue with $%s to allocate."
               % (txn.reference, abs(txn.unallocated_amount)))
    if wants_json:
        return JsonResponse({
            'ok': True,
            'reference': txn.reference,
            'message': message,
            'removed': len(slices),
        })
    messages.success(request, message)
    return HttpResponseRedirect(redirect_to)


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def bulk_reconcile(request):
    """
    Reconcile every selected queue row with one set of answers.

    The per-row form is the right tool when the rows differ. When they do not
    -- a dozen supply orders on one export, all Consumables out of the standing
    budget -- it asks the same two questions a dozen times, and the Treasurer
    answers them a dozen times identically. This is the ledger's bulk bar
    pointed at the queue.

    Each selected line gets one slice for whatever is still unallocated on it,
    which is exactly what :class:`ReconcileForm` does for a single row, so a
    part-allocated line is finished off rather than double-counted.

    Every row is validated on its own and the failures are named. A bulk action
    must never be the thing that writes a row the rest of the app would have
    rejected -- the same rule the ledger's bulk action follows.
    """
    form = BulkReconcileForm(request.POST)
    redirect_to = request.POST.get('next') or reverse('finance:queue')

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return HttpResponseRedirect(redirect_to)

    ids = form.selected_ids
    if not ids:
        messages.warning(request, "Nothing was selected.")
        return HttpResponseRedirect(redirect_to)

    lines = list(WorkdayTransaction.objects.filter(pk__in=ids))

    # Revenue routes to an event, not to a fund; the database refuses expense
    # routing on it outright. Said plainly rather than silently dropped.
    revenue = [t for t in lines if t.net_amount > 0]
    if revenue:
        messages.warning(
            request,
            "%s revenue line%s skipped — money coming in is linked to an event or a "
            "revenue type, which is a different question from a fund. Reconcile %s on "
            "%s own row."
            % (len(revenue), '' if len(revenue) == 1 else 's',
               'it' if len(revenue) == 1 else 'them',
               'its' if len(revenue) == 1 else 'their'))
        lines = [t for t in lines if t.net_amount <= 0]

    already = [t for t in lines if t.is_fully_allocated and t.slice_count]
    if already:
        messages.info(request, "%s line%s already fully allocated and left alone."
                      % (len(already), ' was' if len(already) == 1 else 's were'))
        lines = [t for t in lines if not (t.is_fully_allocated and t.slice_count)]

    if not lines:
        return HttpResponseRedirect(redirect_to)

    can_settle = request.user.has_perm('finance.settle_subledger')
    done, settled, refused = 0, 0, []

    with reversion.create_revision():
        reversion.set_user(request.user)
        reversion.set_comment("Reconciled in bulk from the ingestion queue")
        for txn in lines:
            remaining = txn.unallocated_amount
            entry = ParsedTransaction(
                parent_transaction=txn,
                amount=remaining if remaining else txn.net_amount,
                effective_date=txn.accounting_date,
                description=txn.journal_line_memo or txn.description,
                fund_source=form.cleaned_data['fund_source'],
                lnl_spend_category=form.cleaned_data.get('lnl_spend_category'),
                project_tag=form.cleaned_data.get('project_tag'),
                created_by=request.user)
            try:
                entry.full_clean()
            except ValidationError as exc:
                refused.append((txn, exc))
                continue
            entry.save()
            done += 1
            # Settled here for the same reason the single-row path settles: a
            # line whose one slice is its whole value is complete by definition.
            if can_settle and txn.is_fully_allocated:
                txn.settle()
                settled += 1

    if done:
        messages.success(
            request, "Reconciled %s line%s%s." % (
                done, '' if done == 1 else 's',
                " and settled %s" % settled if settled else ''))
    for txn, exc in refused[:5]:
        messages.warning(request, "%s unchanged: %s" % (
            txn.reference, '; '.join(m for msgs in exc.message_dict.values() for m in msgs)))
    if len(refused) > 5:
        messages.warning(request, "...and %s more the settings would have invalidated."
                         % (len(refused) - 5))
    return HttpResponseRedirect(redirect_to)

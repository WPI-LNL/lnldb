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
from django.db import transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.views.decorators.http import require_POST

from finance.filters import filter_context, get_filter_state
from finance.forms import (BulkEncumbranceForm, BulkReconcileForm, EncumbranceForm,
                           ReconcileForm, WorkdayCSVUploadForm)
from finance.importers import (ImportError_, discard_staged, import_workday_export,
                               purge_stale_staged, read_staged, stage_upload)
from finance.models import (ZERO, ParsedTransaction, TransactionStatus,  # NOQA
                            WorkdayTransaction, money)
from finance.suggestions import (ENCUMBRANCE_CLOSE_ENOUGH, active_project_tags,
                                 active_suggestion_rules, encumbrance_match_is_close,
                                 encumbrance_match_label, suggest_all,
                                 suggest_encumbrance_matches, suggest_refund_targets)

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
        # Only ever a shortlist to choose from, so it is built per row rather
        # than prefetched: the queryset is narrow (pending, parentless, dated
        # near this line) and most ledgers carry a handful of open
        # encumbrances at a time, not a page of them.
        encumbrances = [
            {'entry': entry, 'label': encumbrance_match_label(entry, txn)}
            for entry in suggest_encumbrance_matches(txn)]
        # Everything in the window is offered; only a candidate of roughly the
        # right size earns the warning on the row itself.
        close_encumbrance = any(encumbrance_match_is_close(c['entry'], txn)
                                for c in encumbrances)

        rows.append({
            'txn': txn,
            'form': form,
            'suggestions': suggestions,
            'encumbrances': encumbrances,
            'close_encumbrance': close_encumbrance,
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
        # Every open reservation, not the per-row shortlist: a bulk draw spans
        # several lines, so no single line's ranking applies to it.
        'bulk_encumbrance_form': BulkEncumbranceForm() if can_edit else None,
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

    # Louder than an error would be wrong -- these rows are fine as far as the
    # ledger can tell -- but quieter than this is how a double-counted line got
    # all the way to a reconciled entry without anyone seeing it.
    suspects = result.suspects
    for row in suspects[:5]:
        messages.warning(request, "Line %s: %s" % (row.line_number, row.warning))
    if len(suspects) > 5:
        messages.warning(request, "...and %s more line(s) resembling something already in "
                                  "the ledger." % (len(suspects) - 5))

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
        'suspects': result.suspects[:5],
        'suspect_count': len(result.suspects),
        'more_suspects': max(0, len(result.suspects) - 5),
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
    else:
        payload['encumbrances'] = [{
            'value': str(entry.pk),
            'label': encumbrance_match_label(entry, txn),
        } for entry in suggest_encumbrance_matches(txn)]

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
            messages.success(
                request,
                "Encumbered $%s. It stays Pending until the matching Workday line is "
                "imported — that line will then offer this row under “Already "
                "encumbered?” in the queue." % abs(entry.amount))
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


def _name_a_few(labels, limit=5):
    """
    ``"A, B, C and 4 more"`` -- enough to recognise, not enough to scroll.

    A bulk action's report has to name the rows it did not finish, or the
    Treasurer has to go and find them; naming forty of them in a banner means
    nobody reads any.
    """
    labels = list(labels)
    named = ", ".join(labels[:limit])
    if len(labels) > limit:
        named += " and %s more" % (len(labels) - limit)
    return named


def _draw_message(txn, reserved, drawn, exhausted, settled):
    """
    What one drawdown did, in a sentence.

    Says all three of what the line took, what the reservation has left, and
    what the line still needs, because after this change any of them can be
    non-obvious: a reservation spanning ten lines is neither used up nor
    untouched, and the Treasurer has no other way to see where it stands
    without going and looking.
    """
    took = abs(money(drawn))
    estimate = abs(money(reserved))
    verb = "settled against" if settled else "matched to"

    if exhausted and took == estimate:
        message = "%s %s an encumbrance of $%s." % (txn.reference, verb, took)
    elif exhausted:
        message = ("%s %s an encumbrance reserved at $%s; $%s was drawn."
                   % (txn.reference, verb, estimate, took))
    else:
        message = ("%s %s $%s of a $%s encumbrance — $%s stays reserved."
                   % (txn.reference, verb, took, estimate, estimate - took))

    left = abs(money(txn.unallocated_amount))
    if left:
        message += (" $%s of this line is still unallocated — the reservation did not "
                    "cover it." % left)
    return message


def _encumbrance_draw(reserved, remaining):
    """
    How much of one reservation this bank line takes, and whether that ends it.

    Three shapes, and the arithmetic has to tell them apart because charging the
    wrong one of them to a budget line is invisible afterwards. Everything here
    is negative -- money going out -- so the comparisons are on magnitude.

    * **The reservation is larger than the line.** One encumbrance covering ten
      invoice lines is the ordinary case: somebody reserves what the whole job
      will cost and Workday delivers it a line at a time. The line takes what it
      needs and the reservation stays open for the rest.
    * **The line is larger, but not by much.** An estimate is a round number and
      an invoice is not, so $200.00 reserved against $203.55 charged is the
      estimate being an estimate. The reservation covers the line and closes.
    * **The line is larger by a lot.** A $200 reservation is not evidence about
      a $2,000 charge. It covers the $200 it was written for and the rest of the
      line stays in the queue to be routed on its own -- silently swallowing the
      difference would charge the budget line $1,800 nobody reserved, which is
      the exact failure this whole feature exists to prevent.

    :returns: ``(draw, exhausted)`` -- what this line takes, and whether the
        reservation has nothing left afterwards.
    """
    reserved, remaining = money(reserved), money(remaining)
    if abs(reserved) > abs(remaining):
        return remaining, False
    # Within the tolerance the difference is estimate noise, so the reservation
    # stretches to cover the line; beyond it, it covers only what it says.
    slack = abs(money(remaining)) * ENCUMBRANCE_CLOSE_ENOUGH
    covers_the_line = abs(remaining - reserved) <= slack
    return (remaining if covers_the_line else reserved), True


def _slice_from_encumbrance(entry, txn, amount, user):
    """
    One bank line's share of a reservation, as its own ledger entry.

    Written when the reservation is bigger than the line and so survives it.
    The routing is copied because that is the whole point -- somebody already
    decided what this money was for -- but the receipt is not: it is evidence of
    a purchase that has cleared, and what is left reserved has not.

    ``created_by`` is the person allocating, while the reservation keeps whoever
    wrote it. The two are different facts and the ledger has room for both.
    """
    return ParsedTransaction(
        parent_transaction=txn,
        amount=amount,
        status=TransactionStatus.PENDING,
        effective_date=txn.accounting_date,
        description=entry.description,
        audit_explanation=entry.audit_explanation,
        is_projection=entry.is_projection,
        fund_source=entry.fund_source,
        lnl_spend_category=entry.lnl_spend_category,
        fr_line_target=entry.fr_line_target,
        project_tag=entry.project_tag,
        linked_event=entry.linked_event,
        created_by=user,
    )


def draw_from_encumbrance(entry, txn, user):
    """
    Charge as much of ``entry`` as ``txn`` accounts for against ``txn``.

    The reservation is the thing that persists. It keeps its primary key, its
    author and its whole revision history across every line it pays for, and
    shrinks as each one lands; only the line that finishes it off takes the row
    itself. That is what lets ten Workday lines map to one encumbrance without
    the reservation's identity churning underneath the Treasurer -- it stays the
    same row in the picker, reading down towards zero.

    Raises ``ValidationError`` if the result would not be a legal entry, having
    written nothing: the caller runs inside an atomic revision.

    :returns: ``(drawn, exhausted)`` -- how much this line took, and whether the
        reservation is now closed.
    """
    remaining = txn.unallocated_amount
    draw, exhausted = _encumbrance_draw(entry.amount, remaining)

    if not exhausted:
        # The reservation outlives this line, so the line gets a copy and the
        # reservation is written down by what it just paid for.
        slice_ = _slice_from_encumbrance(entry, txn, draw, user)
        slice_.full_clean()
        slice_.save()
        entry.amount = money(entry.amount) - money(draw)
        entry.full_clean()
        entry.save()
        return draw, False

    # Nothing left over, so the reservation becomes this line's entry rather
    # than spawning one and deleting itself -- the row keeps its history.
    entry.parent_transaction = txn
    entry.amount = draw
    entry.effective_date = txn.accounting_date
    entry.full_clean()
    entry.save()
    return draw, True


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def match_encumbrance(request, pk):
    """
    Attach a pending encumbrance to the bank line that turned out to be it.

    This is the other half of :func:`encumbrance`, and until now it did not
    exist: three places in the UI told the Treasurer an encumbrance "stays
    Pending until it is matched to an imported transaction", and nothing in
    the app could do the matching. The consequence was not merely a missing
    convenience -- reconciling the imported line the ordinary way writes a
    *second* entry, so the funding request line was charged both the estimate
    and the actual, and the only sign of it was a balance quietly $200 short.

    Three things are settled here, all of which are wrong to leave to the
    person doing it:

    * **The amount becomes the actual.** An encumbrance is an estimate and the
      bank line is what happened, so the entry takes the line's unallocated
      remainder. An over-estimate keeps its difference reserved --
      see :func:`_carve_remainder`.
    * **The date becomes the accounting date.** ``effective_date`` is filled in
      only when blank, so an encumbrance carries the day it was *written*. A
      June reservation settling a July charge would otherwise stay in FY25
      while its bank line sits in FY26, splitting one purchase across two
      fiscal years on the ledger, the cash-flow chart and the award balance.
    * **Routing is left exactly as it was.** Somebody already decided what this
      money was for; the arrival of the invoice is not new information about
      that.
    """
    txn = get_object_or_404(WorkdayTransaction, pk=pk)
    redirect_to = request.POST.get('next') or reverse('finance:queue')
    wants_json = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    def fail(message, status=400):
        if wants_json:
            return JsonResponse({'ok': False, 'reference': txn.reference,
                                 'message': message}, status=status)
        messages.error(request, message)
        return HttpResponseRedirect(redirect_to)

    # The picker's first option is "not encumbered", which is a real answer and
    # the common one -- it just is not this button's answer.
    chosen = (request.POST.get('encumbrance') or '').strip()
    if not chosen.isdigit():
        return fail("Pick an encumbrance from the list first, or reconcile %s with the form "
                    "below if it was never encumbered." % txn.reference)

    entry = ParsedTransaction.objects.filter(
        pk=int(chosen),
        parent_transaction__isnull=True,
        status=TransactionStatus.PENDING).first()
    if entry is None:
        # Nearly always two people working the queue at once: the row was on
        # screen when the page rendered and matched by someone else since.
        return fail("That encumbrance is no longer pending — it may have been matched or "
                    "deleted already. Reload the queue and try again.", status=409)

    remaining = txn.unallocated_amount
    if not remaining:
        return fail("%s is already fully allocated, so there is nothing for an encumbrance "
                    "to settle." % txn.reference, status=409)
    if (remaining > 0) != (entry.amount > 0):
        # An encumbrance is always money out; a positive line is a receipt.
        return fail("%s is money coming in, and an encumbrance reserves money going out."
                    % txn.reference)

    reserved = entry.amount

    try:
        with reversion.create_revision():
            reversion.set_user(request.user)
            reversion.set_comment("Matched to %s from the ingestion queue" % txn.reference)
            drawn, exhausted = draw_from_encumbrance(entry, txn, request.user)
    except ValidationError as exc:
        # Attaching a parent brings the partition rules into play for the first
        # time, so a cross-partition encumbrance can fail here having been
        # perfectly valid as a standalone row.
        return fail("%s could not be matched: %s"
                    % (txn.reference, " ".join(exc.messages)))

    settled = txn.is_fully_allocated and request.user.has_perm('finance.settle_subledger')
    if settled:
        txn.settle()

    message = _draw_message(txn, reserved, drawn, exhausted, settled)

    if wants_json:
        txn.refresh_from_db()
        return JsonResponse({
            'ok': True,
            'reference': txn.reference,
            'message': message,
            'settled': settled,
            'done': txn.is_fully_allocated,
            'unallocated': str(txn.unallocated_amount),
            # The queue's Undo deletes a row's allocations outright. That is
            # the right way back out of an allocation typed a second ago and
            # the wrong way back out of an encumbrance logged weeks ago -- it
            # would take the description, the reason and the reservation with
            # it, and none of that came from the bank line. Correcting a wrong
            # match is an edit on the entry, not a deletion.
            'undoable': False,
        })

    messages.success(request, message)
    return HttpResponseRedirect(redirect_to)


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


@login_required
@permission_required('finance.edit_subledger', raise_exception=True)
@require_POST
def bulk_match_encumbrance(request):
    """
    Draw one reservation down across every selected queue row.

    One encumbrance written for a job, delivered by Workday as ten invoice
    lines, is the ordinary shape of a big purchase -- and matching them one at
    a time is the same repetition the bulk bar exists to remove, with a running
    balance to keep in your head between clicks.

    Oldest line first, because that is the order the money actually left and it
    makes the drawdown reproducible: the same selection and the same reservation
    always produce the same allocation, whichever order the rows were ticked in.

    Stops when the reservation runs out rather than stretching it, and says how
    many lines were left over. A reservation is evidence about the purchase it
    was written for, not about whatever else is on the same export.
    """
    form = BulkEncumbranceForm(request.POST)
    redirect_to = request.POST.get('next') or reverse('finance:queue')

    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return HttpResponseRedirect(redirect_to)

    entry = form.cleaned_data.get('encumbrance')
    if entry is None:
        messages.error(request, "Pick the encumbrance to draw from.")
        return HttpResponseRedirect(redirect_to)

    ids = form.selected_ids
    if not ids:
        messages.warning(request, "Nothing was selected.")
        return HttpResponseRedirect(redirect_to)

    lines = list(WorkdayTransaction.objects.filter(pk__in=ids)
                 .order_by('accounting_date', 'pk'))

    revenue = [t for t in lines if t.net_amount > 0]
    if revenue:
        messages.warning(
            request, "%s revenue line%s skipped — an encumbrance reserves money going out."
            % (len(revenue), '' if len(revenue) == 1 else 's'))
    lines = [t for t in lines if t.net_amount < 0 and t.unallocated_amount]

    if not lines:
        messages.info(request, "Nothing was left to allocate on the selected lines.")
        return HttpResponseRedirect(redirect_to)

    reserved = entry.amount
    can_settle = request.user.has_perm('finance.settle_subledger')
    covered, settled, refused, untouched = [], 0, [], []
    exhausted = False

    with reversion.create_revision():
        reversion.set_user(request.user)
        reversion.set_comment("Drawn from an encumbrance in bulk from the ingestion queue")
        for index, txn in enumerate(lines):
            if exhausted:
                # Nothing left to draw, so every remaining line is untouched
                # rather than partly done -- and is named below.
                untouched = lines[index:]
                break
            try:
                # Each row is validated on its own and a failure leaves it
                # alone: a bulk action must never write a row the rest of the
                # app would have rejected. Savepointed so one refusal does not
                # take the successful draws before it down with it.
                with transaction.atomic():
                    drawn, exhausted = draw_from_encumbrance(entry, txn, request.user)
            except ValidationError as exc:
                refused.append((txn, exc))
                continue
            covered.append((txn, drawn))
            if can_settle and txn.is_fully_allocated:
                txn.settle()
                settled += 1

    if covered:
        total = abs(sum((money(d) for _, d in covered), ZERO))
        messages.success(
            request, "Drew $%s from the encumbrance across %s line%s%s. %s" % (
                total, len(covered), '' if len(covered) == 1 else 's',
                " and settled %s" % settled if settled else '',
                "The reservation is now closed." if exhausted else
                "$%s stays reserved." % (abs(money(reserved)) - total)))

    # A line the reservation reached but did not finish. It stays in the queue,
    # which is correct and easy to miss among nine that left it -- the eye reads
    # "settled 9" and stops.
    short = [(t, t.unallocated_amount) for t, _ in covered if t.unallocated_amount]
    if short:
        messages.info(
            request, "The reservation did not cover all of %s: %s. %s still in the queue."
            % ("one line" if len(short) == 1 else "%s lines" % len(short),
               _name_a_few("%s ($%s left)" % (t.reference, abs(money(left)))
                           for t, left in short),
               "It is" if len(short) == 1 else "They are"))

    # The lines the reservation did not reach. Named rather than counted: the
    # Treasurer has to route them by hand and needs to know which.
    if untouched:
        messages.info(
            request, "The encumbrance ran out before %s line%s: %s. Reconcile %s on %s own."
            % (len(untouched), '' if len(untouched) == 1 else 's',
               _name_a_few(t.reference for t in untouched),
               'it' if len(untouched) == 1 else 'them',
               'its' if len(untouched) == 1 else 'their'))

    for txn, exc in refused[:5]:
        messages.warning(request, "%s unchanged: %s" % (txn.reference, " ".join(exc.messages)))
    if len(refused) > 5:
        messages.warning(request, "...and %s more the reservation would have invalidated."
                         % (len(refused) - 5))

    return HttpResponseRedirect(redirect_to)

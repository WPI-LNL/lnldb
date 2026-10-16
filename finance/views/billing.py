"""
The pages for billing an event: the Billing page, bills and multi-bills, the
multi-bill invoice, recording the worktag and the ISD a bill is charged to,
and deciding an event needs no bill.

The Billing page lists every bill by the stage it is at (see
:mod:`finance.billing`) and offers the next thing to do about each. It
replaced the events app's six billing lists, whose old addresses lead to its
tabs.

The bill pages moved here from the events app with the bills, unchanged apart
from their addresses, which are now under ``/db/finance/billing/``. They
still send people back to the event's own page. The multi-bill pages were
rewritten here; see *Multi-bills* below. All of them check the events app's
``Bill event`` permission, which is what Officers hold. The client's worktag
form stays in the events app: every bill email ever sent links to it there.

Either kind of bill is marked paid through one form, *Mark paid* (see
*Marking a bill paid* below), unless the payment filed for it in the
ingestion queue already did. The Billing page then closes the events, one at
a time or ticked together, as long as no money is still owed on them.
"""
from collections import OrderedDict
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls.base import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, UpdateView
from pypdf import PdfWriter

from emails.generators import BillingEmailGenerator, DefaultLNLEmailGenerator as DLEG
from events.models import BaseEvent
from finance.billing import (CLOSABLE, CREATE_ISD, NO_BILL_NEEDED, PAID, READY, STAGE_HELP, STAGES,
                             WAITING_ON_APPROVAL, WAITING_ON_CLIENT, BillItem, attach_payments, billing_items,
                             by_stage, closable_items, close_item, event_item, filter_items, ready_sections)
from finance.billing_forms import (BillingEmailForm, BillingForm, BillingUpdateForm, BillISDForm, BillPaidForm,
                                   BillWorktagForm, MultiBillChargeForm, MultiBillForm, MultiBillingEmailForm,
                                   NoBillNeededForm, bill_events, clear_isd, client_tally)
from finance.calculators import bill_payments, latest_bill
from finance.filters import filter_context, get_filter_state
from finance.models import (ZERO, Billing, BillingEmail, MultiBilling, MultiBillingCharge, MultiBillingEmail,
                            NoBillNeeded, books_start_date, money, no_bill_needed_for)
from helpers.mixins import HasPermMixin, LoginRequiredMixin, SetFormMsgMixin
from helpers.revision import set_revision_comment
from pdfs.views import generate_event_bill_pdf_standalone, write_weasyprint_pdf


class BillingCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = Billing
    form_class = BillingForm
    template_name = "form_crispy_cbv.html"
    msg = "New Bill"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(BaseEvent, pk=self.kwargs['event'])
        if self.event.closed:
            messages.add_message(request, messages.ERROR, 'Event is closed.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.kwargs['event'],)))
        decided = no_bill_needed_for(self.event)
        if decided is not None:
            messages.error(request, "%s is marked No bill needed (%s). Undo that first to bill it."
                           % (self.event.event_name, decided.get_reason_display()))
            return HttpResponseRedirect(reverse('events:detail', args=(self.kwargs['event'],)) + "#billing")
        return super(BillingCreate, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(BillingCreate, self).get_context_data(**kwargs)
        if self.event.closed:
            raise PermissionDenied
        orgs = self.event.org.all()
        orgstrings = ",".join(["%s's billing account was last verified: %s" % (
            o.name, o.verifications.latest().date if o.verifications.exists() else "Never") for o in orgs])
        context['extra'] = orgstrings
        return context

    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingCreate, self).get_form_kwargs()
        kwargs['event'] = self.event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Bill Created!", extra_tags='success')
        return super(BillingCreate, self).form_valid(form)

    def get_success_url(self):
        if 'save-and-make-email' in self.request.POST:
            return reverse("finance:bill-email", args=(self.kwargs['event'], self.object.pk))
        else:
            return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"


class BillingUpdate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, UpdateView):
    model = Billing
    form_class = BillingUpdateForm
    template_name = "form_crispy_cbv.html"
    msg = "Update Bill"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(BaseEvent, pk=self.kwargs['event'])
        if self.event.closed:
            messages.add_message(request, messages.ERROR, 'Event is closed.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.kwargs['event'],)))
        return super(BillingUpdate, self).dispatch(request, *args, **kwargs)

    def get_object(self, *args, **kwargs):
        """ Validate preconditions for editing a bill """
        obj = super(BillingUpdate, self).get_object(*args, **kwargs)
        if obj.event.closed:
            raise PermissionDenied
        else:
            return obj

    def get_form_kwargs(self):
        kwargs = super(BillingUpdate, self).get_form_kwargs()
        kwargs['event'] = self.event
        return kwargs

    def get(self, request, *args, **kwargs):
        response = super(BillingUpdate, self).get(request, *args, **kwargs)
        if self.object.isd_number:
            messages.warning(request, isd_warning(self.object))
        return response

    def form_valid(self, form):
        messages.success(self.request, "Billing Updated!", extra_tags='success')
        response = super(BillingUpdate, self).form_valid(form)
        if self.object.isd_differs:
            messages.warning(self.request, isd_now_differs(self.object))
        return response

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"


class BillingDelete(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, DeleteView):
    model = Billing
    template_name = "form_delete_cbv.html"
    msg = "Delete Bill"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.event = get_object_or_404(BaseEvent, pk=self.kwargs['event'])
        if self.event.closed:
            messages.add_message(request, messages.ERROR, 'Event is closed.')
            return HttpResponseRedirect(reverse('events:detail', args=(self.kwargs['event'],)))
        return super(BillingDelete, self).dispatch(request, *args, **kwargs)

    def get_object(self, *args, **kwargs):
        """ Validate preconditions for deleting a bill """
        obj = super(BillingDelete, self).get_object(*args, **kwargs)
        if obj.date_paid:
            raise PermissionDenied
        if obj.event.closed:
            raise PermissionDenied
        else:
            return obj

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"


class MultiBillingDelete(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, DeleteView):
    model = MultiBilling
    template_name = "form_delete_cbv.html"
    msg = "Delete MultiBill"
    perms = 'events.bill_event'

    def get_object(self, *args, **kwargs):
        """ Validate preconditions for deleting a multibill """
        obj = super(MultiBillingDelete, self).get_object(*args, **kwargs)
        if obj.date_paid:
            raise PermissionDenied
        if obj.events.filter(closed=True).exists():
            raise PermissionDenied
        else:
            return obj

    def get_success_url(self):
        return reverse("finance:multibill-list")


class BillingEmailCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = BillingEmail
    form_class = BillingEmailForm
    template_name = "form_crispy.html"
    msg = "New Billing Email"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.billing = get_object_or_404(Billing, pk=self.kwargs['billing'])
        return super(BillingEmailCreate, self).dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingEmailCreate, self).get_form_kwargs()
        kwargs['billing'] = self.billing
        kwargs['initial'] = {'subject': render_to_string('emails/email_billing_subject.txt', {'billing': self.billing},
                                                         request=self.request),
                             'message': render_to_string('emails/email_billing_message.txt', {'billing': self.billing},
                                                         request=self.request)}
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Billing Email Created!", extra_tags='success')
        response = super(BillingEmailCreate, self).form_valid(form)
        # send the email
        i = form.instance
        event = self.billing.event
        to = list(i.email_to_users.values_list('email', flat=True))
        to.extend(list(i.email_to_orgs.values_list('exec_email', flat=True)))
        pdf_handle = generate_event_bill_pdf_standalone(event, request=self.request)
        filename = "%s-bill.pdf" % slugify(event.event_name)
        attachments = [{"file_handle": pdf_handle, "name": filename}]
        email = BillingEmailGenerator(event=event, subject=i.subject, body=i.message, to_emails=to, attachments=attachments)
        email.send()
        i.sent_at = timezone.now()
        i.save()
        return response

    def get_success_url(self):
        return reverse("events:detail", args=(self.billing.event_id,)) + "#billing"


class MultiBillingEmailCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = MultiBillingEmail
    form_class = MultiBillingEmailForm
    template_name = "form_crispy.html"
    msg = "New Billing Email"
    perms = 'events.bill_event'

    def dispatch(self, request, *args, **kwargs):
        self.multibilling = get_object_or_404(MultiBilling, pk=self.kwargs['multibilling'])
        return super(MultiBillingEmailCreate, self).dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super(MultiBillingEmailCreate, self).get_form_kwargs()
        kwargs['multibilling'] = self.multibilling
        # Written out as for a single bill, so the Treasurer edits a draft
        # rather than starting from nothing every time it is sent.
        context = {'bill': self.multibilling, 'breakdown': self.multibilling.breakdown()}
        kwargs['initial'] = {
            'subject': render_to_string('finance/emails/multibill_subject.txt', context,
                                        request=self.request).strip(),
            'message': render_to_string('finance/emails/multibill_message.txt', context, request=self.request),
        }
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Billing Email Created!", extra_tags='success')
        response = super(MultiBillingEmailCreate, self).form_valid(form)
        # send the email
        i = form.instance
        to = list(i.email_to_users.values_list('email', flat=True))
        to.extend(list(i.email_to_orgs.values_list('exec_email', flat=True)))
        pdf_handle = multibill_invoice_pdf(self.multibilling, request=self.request)
        attachments = [{"file_handle": pdf_handle, "name": multibill_invoice_name(self.multibilling)}]
        email = DLEG(subject=i.subject, body=i.message, to_emails=to, reply_to=[settings.EMAIL_TARGET_T],
                     bcc=[settings.EMAIL_TARGET_T], attachments=attachments)
        email.send()
        i.sent_at = timezone.now()
        i.save()
        return response

    def get_success_url(self):
        return reverse("finance:multibill-detail", args=(self.multibilling.pk,))


# ---------------------------------------------------------------------------
# What a bill is charged to, and events that need no bill
#
# The worktag, when the client sent it by email; then the ISD created in
# Workday for it, with its number. Both kinds of bill take the same forms. And
# the Treasurer's decision that an event will not be billed, which can be
# undone.
# ---------------------------------------------------------------------------

def isd_warning(bill):
    """ What to say before a bill with a recorded ISD is changed. """
    return ("ISD %s was created for $%s. If this changes what the bill comes to, the ISD in Workday will no longer "
            "match it: change the ISD in Workday too, then record the new amount."
            % (bill.isd_number, money(bill.isd_amount)))


def isd_now_differs(bill):
    """ What to say once a change has left a bill no longer matching its ISD. """
    return ("ISD %s charges $%s, but the bill now comes to $%s. Change the ISD in Workday, then record the new "
            "amount." % (bill.isd_number, money(bill.isd_amount), money(bill.amount)))


def _bill_closed(request, bill, events):
    """ The response refusing to change a bill with a closed event, or ``None``. """
    if any(event.closed for event in events):
        messages.error(request, "An event on this bill is closed, so the bill cannot be changed.")
        return HttpResponseRedirect(_bill_url(bill))
    return None


def _bill_url(bill):
    if isinstance(bill, MultiBilling):
        return reverse('finance:multibill-detail', args=(bill.pk,))
    return reverse('events:detail', args=(bill.event_id,)) + '#billing'


def _record_workday(request, bill, form_class):
    """
    Record a bill's worktag, or its ISD, with ``form_class``, and go back to
    the Billing page at the stage the bill has reached.

    A paid bill is past both; so is any bill with a closed event, as for every
    other change to a bill. On the ISD form, *Remove the ISD* takes a recorded
    ISD off again.
    """
    events = bill_events(bill)
    refused = _bill_closed(request, bill, events)
    if refused:
        return refused
    if bill.date_paid:
        messages.error(request, "This bill was paid on %s, so what it was charged to is settled."
                       % date_format(bill.date_paid, 'M j, Y'))
        return HttpResponseRedirect(_bill_url(bill))
    item = BillItem(None, events, bill)
    name = item.name
    if request.method == 'POST' and 'remove-isd' in request.POST and bill.isd_number:
        number = bill.isd_number
        set_revision_comment("Removed ISD %s from the bill" % number, None)
        clear_isd(bill, events)
        messages.success(request, "Removed ISD %s from %s. It is back at Create ISD." % (number, name))
        return HttpResponseRedirect(_back_to(request, billing_url(CREATE_ISD)))
    form = form_class(request.POST or None, bill=bill, events=events)
    if request.method == 'POST' and form.is_valid():
        if form_class is BillISDForm:
            set_revision_comment("Recorded ISD %s" % form.cleaned_data['isd_number'], None)
            form.save(user=request.user)
            messages.success(request, "Recorded ISD %s for %s. It is waiting on approval."
                             % (bill.isd_number, name))
            if bill.isd_differs:
                messages.warning(request, "The ISD charges $%s, and the bill comes to $%s."
                                 % (money(bill.isd_amount), money(bill.amount)))
            return HttpResponseRedirect(_back_to(request, billing_url(WAITING_ON_APPROVAL)))
        form.save(user=request.user)
        messages.success(request, "Recorded worktag %s for %s. It is ready for its ISD." % (bill.worktag_charged, name))
        return HttpResponseRedirect(_back_to(request, billing_url(CREATE_ISD)))
    isd = form_class is BillISDForm
    context = _billing_context(
        request, h2=("Record the ISD for %s" if isd else "Record the worktag for %s") % name, bill=bill,
        item=item, form=form, isd=isd, cancel_url=_back_to(request, billing_url()))
    return render(request, 'finance/bill_workday_form.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def bill_worktag(request, event, pk):
    """ Record the worktag a client sent by email for their bill. """
    return _record_workday(request, get_object_or_404(Billing, pk=pk, event_id=event), BillWorktagForm)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def bill_isd(request, event, pk):
    """ Record the ISD created in Workday for a bill, or change or remove it. """
    return _record_workday(request, get_object_or_404(Billing, pk=pk, event_id=event), BillISDForm)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibill_worktag(request, pk):
    """ Record the worktag a multi-bill's client sent back. """
    return _record_workday(request, get_object_or_404(MultiBilling, pk=pk), BillWorktagForm)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibill_isd(request, pk):
    """ Record the ISD created in Workday for a multi-bill, or change or remove it. """
    return _record_workday(request, get_object_or_404(MultiBilling, pk=pk), BillISDForm)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def no_bill_needed(request, event):
    """
    Decide that an event reviewed for billing will not be billed, and why, or
    change the reason. Only for an event with no bill: one that has a bill is
    being billed.
    """
    event = get_object_or_404(BaseEvent, pk=event)
    page = reverse('events:detail', args=(event.pk,)) + '#billing'
    if event.closed or not event.reviewed:
        messages.error(request, "%s is %s." % (event.event_name,
                                               'closed' if event.closed else 'not reviewed for billing yet'))
        return HttpResponseRedirect(page)
    if latest_bill(event) is not None:
        messages.error(request, "%s has a bill. Delete the bill first if it should not be billed." % event.event_name)
        return HttpResponseRedirect(page)
    decided = no_bill_needed_for(event)
    item = event_item(event, None, no_bill=decided)
    form = NoBillNeededForm(request.POST or None, instance=decided or NoBillNeeded(event=event),
                            suggested=decided is None and item.suggest_no_bill)
    if request.method == 'POST' and form.is_valid():
        record = form.save(commit=False)
        record.decided_by = request.user
        record.decided_on = timezone.now()
        record.save()
        messages.success(request, "%s needs no bill: %s." % (event.event_name, record.get_reason_display()))
        return HttpResponseRedirect(_back_to(request, billing_url(READY)))
    context = _billing_context(request, h2="No bill needed for %s" % event.event_name, event=event, item=item,
                               form=form, decided=decided, cancel_url=_back_to(request, billing_url(READY)))
    return render(request, 'finance/no_bill_needed_form.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
@require_POST
def no_bill_needed_undo(request, event):
    """ Undo deciding an event needs no bill, so it is ready to bill again. """
    decided = get_object_or_404(NoBillNeeded.objects.select_related('event'), event_id=event)
    if decided.event.closed:
        messages.error(request, "%s is closed." % decided.event.event_name)
        return HttpResponseRedirect(reverse('events:detail', args=(event,)))
    decided.delete()
    messages.success(request, "%s is ready to bill again." % decided.event.event_name)
    return HttpResponseRedirect(_back_to(request, billing_url(NO_BILL_NEEDED)))


# ---------------------------------------------------------------------------
# The Billing page
#
# Every bill by the stage it is at, one tab per stage, longest-waiting first,
# each row with the next thing to do about it. The stages are worked out in
# finance.billing, which the event page's Next step box and the Owed to LNL
# report read too.
# ---------------------------------------------------------------------------

def billing_url(stage=None):
    """ The Billing page, open at a stage's tab. """
    url = reverse('finance:billing')
    return '%s?stage=%s' % (url, stage) if stage else url


@login_required
@permission_required('events.bill_event', raise_exception=True)
def billing_page(request):
    """
    The Billing page: one tab per stage, with how many bills are at each.

    The filter bar's fiscal year narrows the rows to events that started in
    it, and each tab says how many more are waiting in other years, because a
    bill does not stop needing work when the year turns. The partition keeps
    film showings (Projection) apart from everything else.
    """
    stage = request.GET.get('stage')
    if stage not in STAGES:
        stage = READY
    state = get_filter_state(request)
    every_year = filter_items(billing_items(request.user), is_projection=state.projection_flag)
    this_year = by_stage(filter_items(every_year, fiscal_year=state.fiscal_year))
    all_years = by_stage(every_year)
    tabs = [{'stage': key, 'label': label, 'count': len(this_year[key]),
             'elsewhere': len(all_years[key]) - len(this_year[key])}
            for key, label in STAGES.items()]
    rows = this_year[stage]
    if stage in (WAITING_ON_CLIENT, CREATE_ISD, WAITING_ON_APPROVAL):
        attach_payments(rows)
    elif stage in CLOSABLE:
        # A paid bill too, for whether anything is still owed on it.
        attach_payments(rows, paid=True)
    context = _billing_context(
        request, h2="Billing", stage=stage, stage_label=STAGES[stage], stage_help=STAGE_HELP[stage], tabs=tabs,
        rows=rows, elsewhere=len(all_years[stage]) - len(rows), here=request.get_full_path(),
        can_close=stage in CLOSABLE and request.user.has_perm('events.close_event'))
    if stage == READY:
        context['ready'] = ready_sections(rows)
    return render(request, 'finance/billing.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
@permission_required('events.close_event', raise_exception=True)
@require_POST
def billing_close(request):
    """
    Close events from the Billing page's Paid and No bill needed tabs: the
    row whose Close button was pressed (``only``), or every ticked row
    (``close``). A multi-bill's row closes each of its events still open.

    Each event is closed exactly as the event page's Close button closes it,
    by the same permission, and named "Closed" in its history. A row with
    money still owed on it is refused (see
    :func:`finance.billing.close_refusal`), and so is one no longer at either
    stage -- reopened, paid again, or closed since the page was drawn.
    """
    back = _back_to(request, billing_url(PAID))
    keys = list(OrderedDict.fromkeys(request.POST.getlist('only') or request.POST.getlist('close')))
    if not keys:
        messages.info(request, "Tick the events to close first.")
        return HttpResponseRedirect(back)
    items = {item.key: item for item in closable_items(request.user)}
    set_revision_comment("Closed", None)
    closed, refused, gone = [], [], 0
    for key in keys:
        item = items.get(key)
        if item is None:
            gone += 1
        elif item.close_refusal:
            refused.append("%s: %s" % (item.name, item.close_refusal))
        else:
            closed.extend(close_item(item, request.user))
    if closed:
        messages.success(request, "Closed %s: %s." % (
            _count(len(closed), "event"), ", ".join(event.event_name for event in closed)))
    if refused:
        messages.error(request, "Not closed, because money is still owed. %s. File the payment from the queue, "
                                "or, if it was paid some other way, close the event from its own page."
                       % ". ".join(refused))
    if gone:
        messages.warning(request, "%s no longer paid or needing no bill, or already closed, so %s left alone."
                         % (_count(gone, "row was", "rows were"), "it was" if gone == 1 else "they were"))
    return HttpResponseRedirect(back)


def _count(n, one, many=None):
    """ "1 event", "3 events". """
    return "%s %s" % (n, one if n == 1 else (many or one + "s"))


# ---------------------------------------------------------------------------
# Multi-bills
#
# One bill for several events. Its total is worked out, not typed (see
# MultiBilling.breakdown), and saved whenever its events or charges change
# while it is unpaid. Once it is paid nothing about it can change until it is
# marked unpaid again, and an event on it that has been closed locks it the way
# a closed event locks its own bill.
# ---------------------------------------------------------------------------

def _billing_context(request, **extra):
    """ What every billing page needs: the finance chrome, with the Billing tab lit. """
    context = {'fin_page': 'billing'}
    context.update(extra)
    context.update(filter_context(request))
    return context


def _refuse_change(request, bill):
    """
    Why a multi-bill cannot be changed now, as the response to send instead,
    or ``None`` when it can.

    A closed event locks the bill outright, as it did before multi-bills moved
    here. A paid bill only needs marking unpaid first, so that is said rather
    than refused.
    """
    if bill.events.filter(closed=True).exists():
        raise PermissionDenied
    if bill.date_paid:
        messages.error(request, "%s was marked paid on %s, so it cannot be changed. Mark it unpaid first."
                       % (bill.display_name, date_format(bill.date_paid, 'M j, Y')))
        return HttpResponseRedirect(reverse('finance:multibill-detail', args=(bill.pk,)))
    return None


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibill_list(request):
    """ Every multi-bill, newest first, with where each stands. """
    bills = (MultiBilling.objects.select_related('org').prefetch_related('events')
             .annotate(last_emailed=Max('multibillingemail__sent_at'),
                       closed_events=Count('events', filter=Q(events__closed=True), distinct=True))
             .order_by('-date_billed', '-pk'))
    page = Paginator(bills, 40).get_page(request.GET.get('page'))
    return render(request, 'finance/multibillings.html',
                  _billing_context(request, h2="Multi-bills", page=page))


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibill_detail(request, pk):
    """
    One multi-bill: what it covers, what it comes to and why, who it went to
    and when, and what can be done with it next.
    """
    bill = get_object_or_404(MultiBilling.objects.select_related('org').prefetch_related('charges'), pk=pk)
    breakdown = bill.breakdown()
    saved = money(bill.amount)
    has_closed = any(row['event'].closed for row in breakdown['events'])
    received, last_payment = bill_payments(bill)
    emails = (bill.multibillingemail_set.order_by('-sent_at', '-pk')
              .prefetch_related('email_to_users', 'email_to_orgs'))
    context = _billing_context(
        request, h2=bill.display_name, bill=bill, breakdown=breakdown, saved_total=saved,
        total_differs=breakdown['total'] != saved, clients=client_tally(row['event'] for row in breakdown['events']),
        has_closed_events=has_closed, can_change=not has_closed and not bill.date_paid,
        received=received, last_payment=last_payment, emails=emails)
    return render(request, 'finance/multibill_detail.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibill_edit(request, pk=None):
    """
    Create a multi-bill, or change an unpaid one: its events, who it is billed
    to, its name. The total follows on its own.
    """
    bill = None
    if pk:
        bill = get_object_or_404(MultiBilling, pk=pk)
        refused = _refuse_change(request, bill)
        if refused:
            return refused
    # The events ticked on the Billing page's Ready to bill tab come ticked
    # here, and the list widens to every billable event when one of them is
    # not marked to be billed in bulk, so it is there to be ticked. They stay
    # in the address the form posts back to, so the list is the same then.
    chosen = [] if bill else [value for value in request.GET.getlist('events') if value.isdigit()]
    show = request.GET.get('show_nonbulk_events')
    include_unmarked = (show == 'true' if show else
                        BaseEvent.objects.filter(pk__in=chosen, billed_in_bulk=False).exists())
    form = MultiBillForm(request.POST or None, instance=bill, include_unmarked=include_unmarked,
                         initial={'events': chosen} if chosen else None)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, "%s %s. It comes to %s."
                         % ("Saved" if pk else "Created", saved.display_name, money(saved.amount)))
        if saved.isd_differs:
            messages.warning(request, isd_now_differs(saved))
        if 'save-and-email' in request.POST:
            return HttpResponseRedirect(reverse('finance:multibill-email', args=(saved.pk,)))
        return HttpResponseRedirect(reverse('finance:multibill-detail', args=(saved.pk,)))
    cancel_url = (reverse('finance:multibill-detail', args=(bill.pk,)) if bill
                  else reverse('finance:multibill-list'))
    context = _billing_context(
        request, h2="Change %s" % bill.display_name if bill else "New multi-bill", bill=bill, form=form,
        include_unmarked=include_unmarked, cancel_url=cancel_url)
    return render(request, 'finance/multibill_form.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibill_charge(request, pk, charge_pk=None):
    """ Add one of a multi-bill's own charges, or change one. The total follows. """
    bill = get_object_or_404(MultiBilling, pk=pk)
    refused = _refuse_change(request, bill)
    if refused:
        return refused
    charge = (get_object_or_404(MultiBillingCharge, pk=charge_pk, multibilling=bill) if charge_pk
              else MultiBillingCharge(multibilling=bill))
    form = MultiBillChargeForm(request.POST or None, instance=charge)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        bill.recalculate()
        messages.success(request, "%s %s. %s now comes to %s."
                         % ("Saved" if charge_pk else "Added", saved.description, bill.display_name,
                            money(bill.amount)))
        if bill.isd_differs:
            messages.warning(request, isd_now_differs(bill))
        return HttpResponseRedirect(reverse('finance:multibill-detail', args=(bill.pk,)))
    context = _billing_context(
        request, h2="Change a charge" if charge_pk else "Add a charge to %s" % bill.display_name,
        bill=bill, form=form, cancel_url=reverse('finance:multibill-detail', args=(bill.pk,)))
    return render(request, 'finance/multibill_charge_form.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
@require_POST
def multibill_charge_delete(request, pk, charge_pk):
    """ Take one of a multi-bill's own charges off it. The total follows. """
    bill = get_object_or_404(MultiBilling, pk=pk)
    refused = _refuse_change(request, bill)
    if refused:
        return refused
    charge = get_object_or_404(MultiBillingCharge, pk=charge_pk, multibilling=bill)
    charge.delete()
    bill.recalculate()
    messages.success(request, "Removed %s. %s now comes to %s."
                     % (charge.description, bill.display_name, money(bill.amount)))
    if bill.isd_differs:
        messages.warning(request, isd_now_differs(bill))
    return HttpResponseRedirect(reverse('finance:multibill-detail', args=(bill.pk,)))


@login_required
@permission_required('events.bill_event', raise_exception=True)
@require_POST
def multibill_update_total(request, pk):
    """
    Save what an unpaid multi-bill comes to now, after an event's price
    changed since the total was last saved.
    """
    bill = get_object_or_404(MultiBilling, pk=pk)
    refused = _refuse_change(request, bill)
    if refused:
        return refused
    before = money(bill.amount)
    if bill.recalculate():
        messages.success(request, "%s now comes to %s; it was %s."
                         % (bill.display_name, money(bill.amount), before))
        if bill.isd_differs:
            messages.warning(request, isd_now_differs(bill))
    else:
        messages.info(request, "%s already comes to %s." % (bill.display_name, before))
    return HttpResponseRedirect(reverse('finance:multibill-detail', args=(bill.pk,)))


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibill_mark_paid(request, pk):
    """ The *Mark paid* form for a multi-bill. See :func:`_mark_paid`. """
    bill = get_object_or_404(MultiBilling, pk=pk)
    return _mark_paid(request, bill)


@login_required
@permission_required('events.bill_event', raise_exception=True)
@require_POST
def multibill_mark_unpaid(request, pk):
    """ Undo marking a multi-bill paid, so it can be changed again. """
    bill = get_object_or_404(MultiBilling, pk=pk)
    return _mark_unpaid(request, bill)


# ---------------------------------------------------------------------------
# Marking a bill paid
#
# A bill is marked paid either when the payment filed for it in the ingestion
# queue covers it -- the queue offers to, dated the day the money arrived --
# or here. This form is the only other way, for either kind of bill: it
# replaced the events app's one-click Mark Paid, which stamped today's date
# whenever the money had actually arrived, and finance's own Mark bill paid
# button. When no payment filed from Workday covers the bill it asks how it
# was paid, so a bill marked paid with nothing behind it always says why.
# ---------------------------------------------------------------------------

def _bill_name(bill):
    """ "the bill for Spring Gala", or a multi-bill's name. """
    if isinstance(bill, MultiBilling):
        return bill.display_name
    return "the bill for %s" % bill.event.event_name


def _mark_paid(request, bill):
    """
    When a bill was paid, and how, if not through Workday.

    The date starts as the day the last of its payment reached Workday when
    the payments filed against its events cover it, and today otherwise -- a
    check handed over, or a bill from before the books start, has nothing
    filed to read a date from, and then how it was paid must be said.
    """
    back = _bill_url(bill)
    refused = _bill_closed(request, bill, bill_events(bill))
    if refused:
        return refused
    name = _bill_name(bill)
    if bill.date_paid:
        messages.info(request, "%s was already marked paid on %s."
                      % (name[0].upper() + name[1:], date_format(bill.date_paid, 'M j, Y')))
        return HttpResponseRedirect(back)
    received, last_payment = bill_payments(bill)
    owed = money(bill.amount)
    covered = owed > 0 and received >= owed and last_payment is not None
    form = BillPaidForm(request.POST or None, covered=covered,
                        initial={'date_paid': last_payment if covered else timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        bill.date_paid = form.cleaned_data['date_paid']
        bill.paid_note = form.cleaned_data['paid_note']
        bill.save(update_fields=['date_paid', 'paid_note'])
        messages.success(request, "Marked %s paid on %s." % (name, date_format(bill.date_paid, 'M j, Y')))
        return HttpResponseRedirect(_back_to(request, back))
    start = books_start_date()
    before_books = start is not None and any(
        timezone.localtime(event.datetime_start).date() < start for event in bill_events(bill))
    context = _billing_context(request, h2="Mark %s paid" % name, bill=bill, form=form, received=received,
                               owed=owed, covered=covered, last_payment=last_payment, books_start=start,
                               before_books=before_books, is_multibill=isinstance(bill, MultiBilling),
                               cancel_url=_back_to(request, back))
    return render(request, 'finance/bill_paid_form.html', context)


def _mark_unpaid(request, bill):
    """ Take a bill's paid date off, and how it was paid, so it can be changed again. """
    back = _bill_url(bill)
    refused = _bill_closed(request, bill, bill_events(bill))
    if refused:
        return refused
    bill.date_paid = None
    bill.paid_note = ''
    bill.save(update_fields=['date_paid', 'paid_note'])
    name = _bill_name(bill)
    messages.success(request, "%s is unpaid again." % (name[0].upper() + name[1:]))
    return HttpResponseRedirect(_back_to(request, back))


@login_required
@permission_required('events.bill_event', raise_exception=True)
def bill_mark_paid(request, event, pk):
    """ The *Mark paid* form for one event's bill. See :func:`_mark_paid`. """
    bill = get_object_or_404(Billing.objects.select_related('event'), event_id=event, pk=pk)
    return _mark_paid(request, bill)


@login_required
@permission_required('events.bill_event', raise_exception=True)
@require_POST
def bill_mark_unpaid(request, event, pk):
    """ Undo marking one event's bill paid. """
    bill = get_object_or_404(Billing.objects.select_related('event'), event_id=event, pk=pk)
    return _mark_unpaid(request, bill)


def _back_to(request, default):
    """ Where to go after a save: the page that asked, if it is one of ours. """
    target = request.POST.get('next') or request.GET.get('next')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return target
    return default


# ---------------------------------------------------------------------------
# The multi-bill invoice
#
# Drawn in the 2025 invoice's style, by the same engine (WeasyPrint) and from
# the same stylesheet as the single-event invoice, so the two look alike. When
# the bill says so, each event's own invoice follows it, made by the code that
# makes it when the event is billed alone.
# ---------------------------------------------------------------------------

def get_multibill_data(multibilling):
    """
    What the invoice draws: the bill and its clients, its events, and its own
    charges grouped the way the 2025 invoice groups an event's.

    A percentage fee or discount sits under the events it is a percentage of,
    as an event's sits under its services. Rentals carrying LNL's fee come
    first, then one fee line for each rate, then the rest, as an event's
    rentals do. One-offs are the additional fees.
    """
    breakdown = multibilling.breakdown()
    events = [row['event'] for row in breakdown['events']]
    orgs = []
    for event in events:
        for org in event.org.all():
            if org not in orgs:
                orgs.append(org)
    charges = {kind: [] for kind, _ in MultiBillingCharge.KIND_CHOICES}
    for row in breakdown['charges']:
        charges[row['charge'].kind].append(row)
    adjustments = charges[MultiBillingCharge.PERCENT]
    rentals = charges[MultiBillingCharge.RENTAL]
    oneoffs = charges[MultiBillingCharge.ONE_OFF]
    rental_fees = {}
    for row in rentals:
        if row['charge'].rental_fee_percent:
            percent = row['charge'].rental_fee_percent
            rental_fees[percent] = rental_fees.get(percent, ZERO) + row['fee']
    return {
        'multibilling': multibilling, 'breakdown': breakdown, 'events': events, 'orgs': orgs,
        'billing_org': multibilling.org, 'orgs_differ': bool(orgs) and orgs != [multibilling.org],
        'mixed_clients': len(client_tally(events)) > 1,
        'has_sga_funded': any(getattr(event, 'is_sga_funded', False) for event in events),
        'first_start': events[0].datetime_start if events else None,
        'last_end': max(event.datetime_end for event in events) if events else None,
        'adjustments': adjustments,
        'events_subtotal': breakdown['events_total'] + sum((row['total'] for row in adjustments), ZERO),
        'rentals_with_fee': [row for row in rentals if row['charge'].rental_fee_percent],
        'rental_fees': sorted(rental_fees.items()),
        'rentals_without_fee': [row for row in rentals if not row['charge'].rental_fee_percent],
        'oneoffs': oneoffs,
        'oneoffs_total': sum((row['total'] for row in oneoffs), ZERO),
        'total_cost': breakdown['total'],
    }


def multibill_invoice_name(multibilling):
    """ The invoice's file name, the same for the download and the email: "fall-films-bill.pdf". """
    return '%s-bill.pdf' % slugify(multibilling.display_name)


def multibill_invoice_pdf(multibilling, request=None):
    """
    The invoice as PDF bytes: the bill's own page, followed -- when the bill
    says so -- by each event's invoice, earliest event first.

    Each event's invoice is the one it would get billed alone: the 2025 style,
    or the old style for an event priced before the 2025 pricelists. Making
    one saves a copy on its event, every time, as billing the event alone
    does.
    """
    data = get_multibill_data(multibilling)
    html = render_to_string('finance/multibill_invoice.html', data, request=request)
    invoice = write_weasyprint_pdf(html, BytesIO())
    if not multibilling.attach_event_invoices:
        return invoice.getvalue()
    writer = PdfWriter()
    writer.append(invoice)
    for event in data['events']:
        writer.append(generate_event_bill_pdf_standalone(event, request=request, return_stream=True))
    joined = BytesIO()
    writer.write(joined)
    return joined.getvalue()


@login_required
def generate_multibill_pdf(request, multibilling):
    """ The multi-bill's invoice. ``?raw=true`` gives the bill's own page as HTML, without the events' invoices. """
    if not request.user.has_perm('events.view_event_billing'):
        raise PermissionDenied
    multibilling = get_object_or_404(MultiBilling, pk=multibilling)
    if request.GET.get('raw'):
        return HttpResponse(render_to_string('finance/multibill_invoice.html', get_multibill_data(multibilling),
                                             request=request))
    resp = HttpResponse(multibill_invoice_pdf(multibilling, request=request), content_type='application/pdf')
    resp['Content-Disposition'] = 'inline; filename="%s"' % multibill_invoice_name(multibilling)
    return resp

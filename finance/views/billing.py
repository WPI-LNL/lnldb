"""
The pages for billing an event: creating, editing, emailing and paying bills
and multi-bills, the list of multi-bills, the multi-bill invoice, and marking
an event entered into Workday.

They moved here from the events app with the bills themselves, unchanged
apart from their addresses, which are now under ``/db/finance/billing/``.
They still check the events app's ``Bill event`` permission, which is what
Officers hold, and still send people back to the event's own page. The
client's worktag form stays in the events app: every bill email ever sent
links to it there.
"""
from io import BytesIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db.models import Case, Count, IntegerField, Sum, When
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls.base import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, UpdateView
from xhtml2pdf import pisa

from emails.generators import BillingEmailGenerator, DefaultLNLEmailGenerator as DLEG
from events.models import BaseEvent, Event2019
from events.views.list import FakeExtendedField, FakeField, map_fields, paginate_helper
from finance.billing_forms import (BillingEmailForm, BillingForm, BillingUpdateForm, MultiBillingEmailForm,
                                   MultiBillingForm, MultiBillingUpdateForm)
from finance.models import Billing, BillingEmail, MultiBilling, MultiBillingEmail
from helpers.mixins import HasPermMixin, LoginRequiredMixin, SetFormMsgMixin
from helpers.revision import set_revision_comment
from pdfs.views import generate_event_bill_pdf_standalone, generate_pdf, link_callback


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

    def form_valid(self, form):
        messages.success(self.request, "Billing Updated!", extra_tags='success')
        return super(BillingUpdate, self).form_valid(form)

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


class MultiBillingCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = MultiBilling
    form_class = MultiBillingForm
    template_name = "form_crispy.html"
    msg = "New MultiBill"
    perms = 'events.bill_event'

    def get_form_kwargs(self):
        kwargs = super(MultiBillingCreate, self).get_form_kwargs()
        kwargs['show_nonbulk_events'] = self.request.GET.get('show_nonbulk_events') == 'true'
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "MultiBill Created!", extra_tags='success')
        return super(MultiBillingCreate, self).form_valid(form)

    def get_success_url(self):
        if 'save-and-make-email' in self.request.POST:
            return reverse("finance:multibill-email", args=(self.object.pk,))
        else:
            return reverse("finance:multibill-list")


class MultiBillingUpdate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, UpdateView):
    model = MultiBilling
    form_class = MultiBillingUpdateForm
    template_name = "form_crispy.html"
    msg = "Update MultiBill"
    perms = 'events.bill_event'

    def get_object(self, *args, **kwargs):
        """ Validate preconditions for editing a multibill """
        obj = super(MultiBillingUpdate, self).get_object(*args, **kwargs)
        if obj.events.filter(closed=True).exists():
            raise PermissionDenied
        else:
            return obj

    def form_valid(self, form):
        messages.success(self.request, "MultiBill Updated!", extra_tags='success')
        return super(MultiBillingUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse("finance:multibill-list")


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


@require_POST
@login_required
def pay_bill(request, event, pk):
    """
    Quietly pays a bill, showing a message on the next page. POST only.
    """
    bill = get_object_or_404(Billing, event_id=event, id=pk)
    if not request.user.has_perm('events.bill_event', bill.event):
        raise PermissionDenied
    if bill.event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(bill.event_id,)))
    if bill.date_paid:
        messages.info(request, "Bill has already been paid", extra_tags="info")
    else:
        bill.date_paid = timezone.now()
        bill.save()
        if 'next' in request.GET:
            messages.success(request, "Marked latest bill paid for %s" % bill.event.event_name, extra_tags="success")
        else:
            messages.success(request, "Bill paid!", extra_tags="success")
    if 'next' in request.GET:
        return HttpResponseRedirect(request.GET['next'])
    else:
        return HttpResponseRedirect(reverse('events:detail', args=(bill.event_id,)) + "#billing")


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
        # pass "user" keyword argument with the current user to your form
        kwargs = super(MultiBillingEmailCreate, self).get_form_kwargs()
        kwargs['multibilling'] = self.multibilling
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Billing Email Created!", extra_tags='success')
        response = super(MultiBillingEmailCreate, self).form_valid(form)
        # send the email
        i = form.instance
        to = list(i.email_to_users.values_list('email', flat=True))
        to.extend(list(i.email_to_orgs.values_list('exec_email', flat=True)))
        pdf_handle = generate_multibill_pdf_standalone(self.multibilling, request=self.request)
        filename = "bill.pdf"
        attachments = [{"file_handle": pdf_handle, "name": filename}]
        email = DLEG(subject=i.subject, body=i.message, to_emails=to, reply_to=[settings.EMAIL_TARGET_T],
                     bcc=[settings.EMAIL_TARGET_T], attachments=attachments)
        email.send()
        i.sent_at = timezone.now()
        i.save()
        return response

    def get_success_url(self):
        return reverse("finance:multibill-list")


@require_POST
@login_required
def mark_entered_into_workday(request, id):
    """
    Marks an event as entered into Workday. POST only.
    """
    event = get_object_or_404(Event2019, id=id)
    if not request.user.has_perm('events.bill_event', event):
        raise PermissionDenied
    if event.closed:
        messages.add_message(request, messages.ERROR, 'Event is closed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if event.entered_into_workday:
        messages.info(request, "Event has already been marked entered into Workday.", extra_tags="info")
    if not event.reviewed:
        messages.add_message(request, messages.ERROR, 'Event has not been reviewed for billing.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    if not event.last_bill:
        messages.add_message(request, messages.ERROR, 'Event has not been billed.')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
    else:
        event.entered_into_workday = True
        set_revision_comment("Marked entered into Workday", None)
        event.save()
        messages.success(request, "Marked %s as entered into Workday." % event.event_name, extra_tags="success")
    return HttpResponseRedirect(reverse('events:awaitingworkday'))


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibill_list(request):
    """ Lists all multibills """
    context = {}

    multibills = MultiBilling.objects.annotate(num_closed_events=Sum(Case(
        When(events__closed=True, then=1),
        default=0,
        output_field=IntegerField())))

    page = request.GET.get('page')
    sort = request.GET.get('sort') or '-date_billed'
    multibills = paginate_helper(multibills, page, sort)

    context['h2'] = "MultiBills"
    context['multibillings'] = multibills
    context['cols'] = ['events', FakeField('org', verbose_name="Client", sortable=True),
                       FakeExtendedField('date_billed', model=MultiBilling),
                       FakeExtendedField('date_paid', model=MultiBilling), 'amount', FakeField('email_sent'),
                       FakeField('tasks')]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'finance/multibillings.html', context)


def get_multibill_data(multibilling):
    data = {'multibilling': multibilling}
    orgsets = map(lambda event: event.org.all(), multibilling.events.all())
    orgs = next(iter(orgsets))
    for orgset in orgsets:
        orgs |= orgset
    orgs = orgs.distinct()
    data['orgs'] = orgs
    billing_org = multibilling.org
    data['billing_org'] = billing_org
    events = multibilling.events.order_by('datetime_start')
    data['events'] = events
    data['total_cost'] = sum(map(lambda event: event.cost_total, multibilling.events.all()))
    return data


@login_required
def generate_multibill_pdf(request, multibilling):
    if not request.user.has_perm('events.view_event_billing'):
        raise PermissionDenied
    # Prepare context
    multibilling = get_object_or_404(MultiBilling.objects.annotate(num_events=Count('events')), pk=multibilling)
    data = get_multibill_data(multibilling)

    # Render html content through html template with context
    resp = generate_pdf(data, 'finance/multibill_pdf.html', request)

    resp['Content-Disposition'] = 'inline; filename="bill.pdf"'
    return resp


def generate_multibill_pdf_standalone(multibilling, request=None):
    """
    Generate multibill PDF without HttpResponse

    :returns: PDF file
    """
    # Prepare context
    multibilling = MultiBilling.objects.annotate(num_events=Count('events')).get(id=multibilling.id)
    data = get_multibill_data(multibilling)

    # Render html content through html template with context
    html = render_to_string('finance/multibill_pdf.html', context=data, request=request)

    # Write PDF to file
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    return pdf_file.getvalue()

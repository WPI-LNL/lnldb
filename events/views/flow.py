from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.urlresolvers import reverse
from django.forms.models import inlineformset_factory
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.functional import curry
from django.utils.text import slugify
from django.views.generic import CreateView, DeleteView, UpdateView
from reversion.models import Version

from emails.generators import DefaultLNLEmailGenerator as DLEG
from events.forms import (AttachmentForm, BillingForm, BillingUpdateForm,
                          CCIForm, CrewAssign, EventApprovalForm,
                          EventDenialForm, EventReviewForm, ExtraForm,
                          InternalReportForm, MKHoursForm)
from events.models import (Billing, CCReport, Event, EventArbitrary,
                           EventAttachment, EventCCInstance, ExtraInstance,
                           Hours, ReportReminder)
from helpers.mixins import (ConditionalFormMixin, HasPermMixin,
                            LoginRequiredMixin, SetFormMsgMixin)
from pdfs.views import generate_pdfs_standalone


@login_required
@permission_required('events.approve_event', raise_exception=True)
def approval(request, id):
    context = {}
    context['msg'] = "Approve Event"
    event = get_object_or_404(Event, pk=id)
    if not request.user.has_perm('events.approve_event', event):
        raise PermissionDenied
    if event.approved:
        messages.add_message(request, messages.INFO, 'Event has already been approved!')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    if request.method == 'POST':
        form = EventApprovalForm(request.POST, instance=event)
        if form.is_valid():
            e = form.save(commit=False)
            e.approved = True
            e.approved_on = timezone.now()
            e.approved_by = request.user
            e.save()
            # confirm with user
            messages.add_message(request, messages.INFO, 'Approved Event')
            if e.contact and e.contact.email:
                email_body = 'Your event "%s" has been approved!' % event.event_name
                email = DLEG(subject="Event Approved", to_emails=[e.contact.email], body=email_body,
                             bcc=[settings.EMAIL_TARGET_VP])
                email.send()
            else:
                messages.add_message(request, messages.INFO,
                                     'No contact info on file for approval. Please give them the good news!')

            return HttpResponseRedirect(reverse('events:detail', args=(e.id,)))
        else:
            context['formset'] = form
    else:
        unbilled_events = Event.objects.filter(org__in=event.org.all()).filter(billings__date_paid__isnull=True, billings__date_billed__isnull=False).filter(closed=False).filter(cancelled=False).filter(test_event=False)
        unbilled_events = map(str, unbilled_events)
        if event.org.exists() and unbilled_events:
            messages.add_message(request, messages.WARNING, "Organization has unbilled events: %s" % ", ".join(unbilled_events))
        form = EventApprovalForm(instance=event)
        context['formset'] = form
    return render(request, 'form_crispy.html', context)


@login_required
def denial(request, id):
    context = {}
    context['msg'] = "Deny Event"
    event = get_object_or_404(Event, pk=id)
    if not request.user.has_perm('events.decline_event', event):
        raise PermissionDenied
    if event.cancelled:
        messages.add_message(request, messages.INFO, 'Event has already been cancelled!')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    if request.method == 'POST':
        form = EventDenialForm(request.POST, instance=event)
        if form.is_valid():
            e = form.save(commit=False)
            e.cancelled = True
            e.cancelled_on = timezone.now()
            e.cancelled_by = request.user
            e.closed_by = request.user
            e.closed_on = timezone.now()
            e.save()
            # confirm with user
            messages.add_message(request, messages.INFO, 'Denied Event')
            if e.contact and e.contact.email:
                email_body = 'Sorry, but your event "%s" has been denied. \n Reason: "%s"' % (
                    event.event_name, event.cancelled_reason)
                email = DLEG(subject="Event Denied", to_emails=[e.contact.email], body=email_body,
                             bcc=[settings.EMAIL_TARGET_VP])
                email.send()
            else:
                messages.add_message(request, messages.INFO,
                                     'No contact info on file for denial. Please give them the bad news.')
            return HttpResponseRedirect(reverse('events:detail', args=(e.id,)))
        else:
            context['formset'] = form
    else:
        form = EventDenialForm(instance=event)
        context['formset'] = form
    return render(request, 'form_crispy.html', context)


@login_required
def review(request, id):
    context = {}
    context['h2'] = "Review Event for Billing"
    event = get_object_or_404(Event, pk=id)

    if not request.user.has_perm('events.review_event', event):
        raise PermissionDenied

    if event.reviewed:
        messages.add_message(request, messages.INFO, 'Event has already been reviewed!')
        return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))

    context['event'] = event

    if request.method == 'POST':
        form = EventReviewForm(request.POST, instance=event, event=event)
        if form.is_valid():
            e = form.save(commit=False)
            e.reviewed = True
            e.reviewed_on = timezone.now()
            e.reviewed_by = request.user
            e.save()
            # confirm with user
            messages.add_message(request, messages.INFO, 'Event has been reviewed and is ready for billing!')

            return HttpResponseRedirect(reverse('events:detail', args=(e.id,)) + "#billing")
        else:
            context['formset'] = form
    else:
        form = EventReviewForm(instance=event, event=event)
        context['formset'] = form
    return render(request, 'event_review.html', context)


@login_required
def reviewremind(request, id, uid):
    event = get_object_or_404(Event, pk=id)
    if event.closed or event.reviewed:
        return HttpResponse("Event Closed")

    cci = event.ccinstances.filter(crew_chief_id=uid)
    if cci:
        # only do heavy lifting if we need to

        pdf_handle = generate_pdfs_standalone([event.id])
        filename = "%s.workorder.pdf" % slugify(event.event_name)
        attachments = [{"file_handle": pdf_handle, "name": filename}]

        cci = cci[0]
        ReportReminder.objects.create(event=cci.event, crew_chief=cci.crew_chief)
        email_body = 'This is a reminder that you have a pending crew chief report for "%s" \n' \
                     ' Please Visit %s%s to complete it' % (event.event_name,
                                                            request.get_host(),
                                                            reverse("my-ccreport", args=[event.id]))
        email = DLEG(subject="LNL Crew Chief Report Reminder Email", to_emails=[cci.crew_chief.email], body=email_body,
                     attachments=attachments)
        email.send()
        messages.add_message(request, messages.INFO, 'Reminder Sent')
        return HttpResponseRedirect(reverse("events:review", args=(event.id,)))
    else:
        return HttpResponse("Bad Call")


@login_required
def close(request, id):
    context = {}
    context['msg'] = "Closing Event"
    event = get_object_or_404(Event, pk=id)
    if not request.user.has_perm('events.close_event', event):
        raise PermissionDenied
    event.closed = True
    event.closed_by = request.user
    event.closed_on = timezone.now()

    event.save()

    return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))


@login_required
def cancel(request, id):
    context = {}
    context['msg'] = "Event Cancelled"
    event = get_object_or_404(Event, pk=id)
    if not request.user.has_perm('events.cancel_event', event):
        raise PermissionDenied
    event.cancelled = True
    event.cancelled_by = request.user
    event.cancelled_on = timezone.now()
    event.save()

    if event.contact and event.contact.email:
        targets = [event.contact.email]
    else:
        targets = []

    email_body = 'The event "%s" has been cancelled by %s. If this is incorrect, please contact our vice president at lnl-vp@wpi.edu.' % (event.event_name, str(request.user))
    if request.user.email:
        email_body = email_body[:-1]
        email_body += " or try them at %s." % request.user.email
    email = DLEG(subject="Event Cancelled", to_emails=targets, body=email_body, bcc=[settings.EMAIL_TARGET_VP])
    email.send()
    return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))


@login_required
def reopen(request, id):
    context = {}
    context['msg'] = "Event Reopened"
    event = get_object_or_404(Event, pk=id)
    if not request.user.has_perm('events.reopen_event', event):
        raise PermissionDenied
    event.closed = False
    event.closed_by = None
    event.closed_on = None

    event.save()

    return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))


@login_required
def rmcrew(request, id, user):
    event = get_object_or_404(Event, pk=id)
    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied
    event.crew.remove(user)
    return HttpResponseRedirect(reverse('events.views.flow.assigncrew', args=(event.id,)))


@login_required
def assigncrew(request, id):
    context = {}
    context['msg'] = "Crew"

    event = get_object_or_404(Event, pk=id)
    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied
    context['event'] = event

    if request.method == 'POST':
        formset = CrewAssign(request.POST, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
        else:
            context['formset'] = formset

    else:
        formset = CrewAssign(instance=event)

        context['formset'] = formset

    return render(request, 'form_crew_add.html', context)


@login_required
def hours_bulk_admin(request, id):
    context = {}

    context['msg'] = "Bulk Hours Entry"
    event = get_object_or_404(Event, pk=id)
    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied

    context['event'] = event

    mk_hours_formset = inlineformset_factory(Event, Hours, extra=15, exclude=[])
    mk_hours_formset.form = staticmethod(curry(MKHoursForm, event=event))

    if request.method == 'POST':
        formset = mk_hours_formset(request.POST, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
        else:
            context['formset'] = formset

    else:
        formset = mk_hours_formset(instance=event)

        context['formset'] = formset

    return render(request, 'formset_hours_bulk.html', context)


@login_required
def rmcc(request, id, user):
    event = get_object_or_404(Event, pk=id)
    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied
    event.crew_chief.remove(user)
    return HttpResponseRedirect(reverse('events.views.flow.assigncc', args=(event.id,)))


@login_required
def assigncc(request, id):
    context = {}
    context['msg'] = "CrewChief"

    event = get_object_or_404(Event, pk=id)

    if not (request.user.has_perm('events.edit_event_hours') or
            request.user.has_perm('events.edit_event_hours', event)):
        raise PermissionDenied

    context['event'] = event

    cc_formset = inlineformset_factory(Event, EventCCInstance, extra=3, exclude=[])
    cc_formset.form = staticmethod(curry(CCIForm, event=event))

    if request.method == 'POST':
        formset = cc_formset(request.POST, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
        else:
            context['formset'] = formset

    else:
        formset = cc_formset(instance=event)

        context['formset'] = formset

    return render(request, 'formset_crispy_helpers.html', context)


@login_required
def assignattach(request, id):
    context = {}
    context['msg'] = "Attachments"

    event = get_object_or_404(Event, pk=id)
    if not (request.user.has_perm('events.event_attachments') or
            request.user.has_perm('events.event_attachments', event)):
        raise PermissionDenied
    context['event'] = event

    att_formset = inlineformset_factory(Event, EventAttachment, extra=1, exclude=[])
    att_formset.form = staticmethod(curry(AttachmentForm, event=event))

    if request.method == 'POST':
        formset = att_formset(request.POST, request.FILES, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)))
        else:
            context['formset'] = formset

    else:
        formset = att_formset(instance=event)

        context['formset'] = formset

    return render(request, 'formset_crispy_attachments.html', context)


@login_required
def assignattach_external(request, id):
    context = {}
    context['msg'] = "Attachments"

    event = get_object_or_404(Event, pk=id)
    if event.closed or event.cancelled:
        return HttpResponse("Event does not allow attachment upload at this time")

    context['event'] = event

    mk_att_formset = inlineformset_factory(Event, EventAttachment, extra=1, exclude=[])
    # mk_att_formset.queryset = mk_att_formset.queryset.filter(externally_uploaded=True)
    mk_att_formset.form = staticmethod(curry(AttachmentForm, event=event, externally_uploaded=True))

    if request.method == 'POST':
        formset = mk_att_formset(request.POST, request.FILES, instance=event,
                                 queryset=EventAttachment.objects.filter(externally_uploaded=True))
        if formset.is_valid():
            f = formset.save(commit=False)
            for i in f:
                i.externally_uploaded = True
                i.save()
            return HttpResponseRedirect(reverse('my:workorders', ))
        else:
            context['formset'] = formset

    else:
        formset = mk_att_formset(instance=event, queryset=EventAttachment.objects.filter(externally_uploaded=True))

        context['formset'] = formset

    return render(request, 'formset_crispy_attachments.html', context)


@login_required
def extras(request, id):
    """ This form is for adding extras to an event """
    context = {}
    context['msg'] = "Extras"

    event = get_object_or_404(Event, pk=id)

    if not (request.user.has_perm('events.adjust_event_charges') or request.user.has_perm('events.adjust_event_charges',
                                                                                          event)):
        raise PermissionDenied

    context['event'] = event

    mk_extra_formset = inlineformset_factory(Event, ExtraInstance, extra=1, exclude=[])
    mk_extra_formset.form = staticmethod(curry(ExtraForm))

    if request.method == 'POST':
        formset = mk_extra_formset(request.POST, request.FILES, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)) + "#billing")
        else:
            context['formset'] = formset

    else:
        formset = mk_extra_formset(instance=event)

        context['formset'] = formset

    return render(request, 'formset_crispy_extras.html', context)


@login_required
def oneoff(request, id):
    """ This form is for adding oneoff fees to an event """
    context = {}
    context['msg'] = "One-Off Charges"

    event = get_object_or_404(Event, pk=id)
    context['event'] = event

    if not (request.user.has_perm('events.adjust_event_charges') or request.user.has_perm('events.adjust_event_charges',
                                                                                          event)):
        raise PermissionDenied

    mk_oneoff_formset = inlineformset_factory(Event, EventArbitrary, extra=1, exclude=[])

    if request.method == 'POST':
        formset = mk_oneoff_formset(request.POST, request.FILES, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events:detail', args=(event.id,)) + "#billing")
        else:
            context['formset'] = formset

    else:
        formset = mk_oneoff_formset(instance=event)

        context['formset'] = formset

    return render(request, 'formset_crispy_arbitrary.html', context)


@login_required
def viewevent(request, id):
    context = {}
    event = get_object_or_404(Event, pk=id)
    if not (request.user.has_perm('events.view_event') or request.user.has_perm('events.view_event', event)):
        raise PermissionDenied

    context['event'] = event
    context['history'] = Version.objects.get_for_object(event).get_unique()
    return render(request, 'uglydetail.html', context)


class CCRCreate(SetFormMsgMixin, HasPermMixin, ConditionalFormMixin, LoginRequiredMixin, CreateView):
    model = CCReport
    form_class = InternalReportForm
    template_name = "form_crispy_cbv.html"
    msg = "New Crew Chief Report"
    perms = 'events.add_event_report'

    def get_form_kwargs(self):
        kwargs = super(CCRCreate, self).get_form_kwargs()
        event = get_object_or_404(Event, pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Crew Chief Report Created!", extra_tags='success')
        return super(CCRCreate, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],))


class CCRUpdate(SetFormMsgMixin, ConditionalFormMixin, HasPermMixin, LoginRequiredMixin, UpdateView):
    model = CCReport
    form_class = InternalReportForm
    template_name = "form_crispy_cbv.html"
    msg = "Update Crew Chief Report"
    perms = 'events.add_event_report'

    def get_form_kwargs(self):
        kwargs = super(CCRUpdate, self).get_form_kwargs()
        event = get_object_or_404(Event, pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Crew Chief Report Updated!", extra_tags='success')
        return super(CCRUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],))


class CCRDelete(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, DeleteView):
    model = CCReport
    template_name = "form_delete_cbv.html"
    msg = "Deleted Crew Chief Report"
    perms = 'events.add_event_report'

    def get_object(self, queryset=None):
        """ Hook to ensure object isn't closed """
        obj = super(CCRDelete, self).get_object()
        if obj.event.closed:
            raise ValidationError("Event is closed")
        else:
            return obj

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],))


class BillingCreate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = Billing
    form_class = BillingForm
    template_name = "form_crispy_cbv.html"
    msg = "New Bill"

    perms = 'events.bill_event'

    def get_context_data(self, **kwargs):
        context = super(BillingCreate, self).get_context_data(**kwargs)
        event = get_object_or_404(Event, pk=self.kwargs['event'])
        orgs = event.org.all()
        orgstrings = ",".join(["%s's billing account was last verified: %s" % (
            o.name, o.verifications.latest().date if o.verifications.exists() else "Never") for o in orgs])
        context['extra'] = orgstrings
        return context

    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingCreate, self).get_form_kwargs()
        event = get_object_or_404(Event, pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Bill Created!", extra_tags='success')
        return super(BillingCreate, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"


class BillingUpdate(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, UpdateView):
    model = Billing
    form_class = BillingUpdateForm
    template_name = "form_crispy_cbv.html"
    msg = "Update Bill"
    perms = 'events.bill_event'

    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingUpdate, self).get_form_kwargs()
        event = get_object_or_404(Event, pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Billing Updated!", extra_tags='success')
        return super(BillingUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"


class BillingDelete(HasPermMixin, LoginRequiredMixin, DeleteView):
    model = Billing
    template_name = "form_delete_cbv.html"
    msg = "Deleted Bill"
    perms = 'events.bill_event'

    def get_object(self, queryset=None):
        """ Hook to ensure object isn't closed """
        obj = super(BillingDelete, self).get_object()
        if obj.event.closed:
            raise ValidationError("Event is closed")
        else:
            return obj

    def get_success_url(self):
        return reverse("events:detail", args=(self.kwargs['event'],)) + "#billing"

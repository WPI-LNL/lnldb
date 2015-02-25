from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.conf import settings
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages

from django.forms.models import inlineformset_factory
from django.utils.functional import curry
from django.db.models import Q

from emails.generators import DefaultLNLEmailGenerator as DLEG

from events.forms import EventApprovalForm,EventDenialForm, BillingForm, BillingUpdateForm, EventReviewForm, InternalReportForm
from events.forms import CrewAssign,CrewChiefAssign, CCIForm, AttachmentForm, ExtraForm,MKHoursForm
from events.models import Event,Organization,Billing,EventCCInstance,EventAttachment,Service,ExtraInstance,EventArbitrary, CCReport, Hours, ReportReminder
from helpers.challenges import is_officer

from django.utils.text import slugify
from pdfs.views import generate_pdfs_standalone

import datetime

from django.views.generic import UpdateView,CreateView, DeleteView
from helpers.mixins import LoginRequiredMixin, OfficerMixin, SetFormMsgMixin

from django.core.exceptions import ValidationError

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def approval(request,id):
    context = RequestContext(request)
    context['msg'] = "Approve Event"
    event = get_object_or_404(Event,pk=id)
    if event.approved:
        messages.add_message(request, messages.INFO, 'Event has already been approved!')
        return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
    
    
    if request.method == 'POST':
        form = EventApprovalForm(request.POST,instance=event)
        if form.is_valid():
            e = form.save(commit=False)
            e.approved = True
            e.approved_on = datetime.datetime.now()
            e.approved_by = request.user
            e.save()
            # confirm with user
            messages.add_message(request, messages.INFO, 'Approved Event')
            if e.contact and e.contact.email:
                email_body = 'Your event "%s" has been approved!' % event.event_name
                email = DLEG(subject="Event Approved", to_emails = [e.contact.email], body=email_body, bcc=[settings.EMAIL_TARGET_VP])
                email.send()
            else:
                messages.add_message(request, messages.INFO, 'No contact info on file for approval. Please give them the good news!')
        
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(e.id,)))
        else:
            context['formset'] = form
    else:
        form = EventApprovalForm(instance=event)
        context['formset'] = form
    return render_to_response('form_crispy.html', context) 

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def denial(request,id):
    context = RequestContext(request)
    context['msg'] = "Deny Event"
    event = get_object_or_404(Event,pk=id)
    if event.cancelled:
        messages.add_message(request, messages.INFO, 'Event has already been cancelled!')
        return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
    
    
    if request.method == 'POST':
        form = EventDenialForm(request.POST,instance=event)
        if form.is_valid():
            e = form.save(commit=False)
            e.cancelled = True
            e.cancelled_on = datetime.datetime.now()
            e.cancelled_by = request.user
            e.closed_by = request.user
            e.closed_on = datetime.datetime.now()
            e.save()
            # confirm with user
            messages.add_message(request, messages.INFO, 'Denied Event')
            if e.contact and e.contact.email:
                email_body = 'Your event "%s" has been denied! \n Reason: "%s"' % (event.event_name, event.cancelled_reason)
                email = DLEG(subject="Event Denied", to_emails = [e.contact.email], body=email_body, bcc=[settings.EMAIL_TARGET_VP]) 
                email.send()
            else:
                messages.add_message(request, messages.INFO, 'No contact info on file for denial. Please give them the bad news.')
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(e.id,)))
        else:
            context['formset'] = form
    else:
        form = EventDenialForm(instance=event)
        context['formset'] = form
    return render_to_response('form_crispy.html', context) 

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def review(request,id):
    context = RequestContext(request)
    context['h2'] = "Review Event for Billing"
    event = get_object_or_404(Event,pk=id)
    
    if event.reviewed:
        messages.add_message(request, messages.INFO, 'Event has already been reviewed!')
        return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
        
    context['event'] = event
    
    if request.method == 'POST':
        form = EventReviewForm(request.POST,instance=event, event=event)
        if form.is_valid():
            e = form.save(commit=False)
            e.reviewed = True
            e.reviewed_on = datetime.datetime.now()
            e.reviewed_by = request.user
            e.save()
            # confirm with user
            messages.add_message(request, messages.INFO, 'Event has been reviewed and is ready for billing!')
        
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(e.id,)))
        else:
            context['formset'] = form
    else:
        form = EventReviewForm(instance=event,event=event)
        context['formset'] = form
    return render_to_response('event_review.html', context) 

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def reviewremind(request,id,uid):
    context = RequestContext(request)
    
    event = get_object_or_404(Event,pk=id)
    if event.closed or event.reviewed:
        return HttpResponse("Event Closed")
    
    cci = event.ccinstances.filter(crew_chief_id=uid)
    if cci:
        # only do heavy lifting if we need to
        
        pdf_handle = generate_pdfs_standalone([event.id])
        filename = "%s.workorder.pdf" % slugify(event.event_name)
        attachments = [{"file_handle":pdf_handle, "name": filename}]
        
        cci = cci[0]
        ReportReminder.objects.create(event=cci.event, crew_chief=cci.crew_chief)
        email_body = 'This is a reminder that you have a pending crew chief report for "%s" \n Please Visit %s%s to complete it' % (event.event_name,request.get_host(),reverse("my-ccreport", args=[event.id]))
        email = DLEG(subject="LNL Crew Chief Report Reminder EMail", to_emails = [cci.crew_chief.email], body=email_body, attachments=attachments) 
        email.send()
        messages.add_message(request, messages.INFO, 'Reminder Sent')
        return HttpResponseRedirect(reverse('event-review',args=(event.id,)))
    else:
        return HttpResponse("Bad Call")

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def close(request,id):
    context = RequestContext(request)
    context['msg'] = "Closing Event"
    event = get_object_or_404(Event,pk=id)
    
    event.closed = True
    event.closed_by = request.user
    event.closed_on = datetime.datetime.now()
    
    event.save()
    
    return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
    
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def rmcrew(request,id,user):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=id)
    event.crew.remove(user)
    return HttpResponseRedirect(reverse('events.views.flow.assigncrew',args=(event.id,)))
        
        
        
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def assigncrew(request,id):
    context = RequestContext(request)
    context['msg'] = "Crew"
    
    event = get_object_or_404(Event,pk=id)
    context['event'] = event
    
    if request.method == 'POST':
        formset = CrewAssign(request.POST,instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = CrewAssign(instance=event)
        
        context['formset'] = formset
        
    return render_to_response('form_crew_add.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def hours_bulk_admin(request,id):
    context = RequestContext(request)
    user = request.user
    
    context['msg'] = "Bulk Hours Entry"
    event = get_object_or_404(Event,pk=id)
    
    context['event'] = event
    
    FS = inlineformset_factory(Event,Hours,extra=15)
    FS.form = staticmethod(curry(MKHoursForm, event=event))
    
    if request.method == 'POST':
        formset = FS(request.POST,instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = FS(instance=event)
        
        context['formset'] = formset
        
    return render_to_response('formset_hours_bulk.html', context)    
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def rmcc(request,id,user):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=id)
    event.crew_chief.remove(user)
    return HttpResponseRedirect(reverse('events.views.flow.assigncc',args=(event.id,)))
        
        
        
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def assigncc(request,id):
    context = RequestContext(request)
    context['msg'] = "CrewChief"
    
    event = get_object_or_404(Event,pk=id)
    context['event'] = event
    
    CrewChiefFS = inlineformset_factory(Event,EventCCInstance,extra=3)
    CrewChiefFS.form = staticmethod(curry(CCIForm, event=event))
    
    if request.method == 'POST':
        formset = CrewChiefFS(request.POST,instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = CrewChiefFS(instance=event)
        
        context['formset'] = formset
        
    return render_to_response('formset_crispy_helpers.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def assignattach(request,id):
    context = RequestContext(request)
    context['msg'] = "Attachments"
    
    event = get_object_or_404(Event,pk=id)
    context['event'] = event
    
    AttachmentFS = inlineformset_factory(Event,EventAttachment,extra=1)
    AttachmentFS.form = staticmethod(curry(AttachmentForm, event=event))
    
    if request.method == 'POST':
        formset = AttachmentFS(request.POST,request.FILES,instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = AttachmentFS(instance=event)
        
        context['formset'] = formset
        
    return render_to_response('formset_crispy_attachments.html', context)

@login_required
def assignattach_external(request,id):
    context = RequestContext(request)
    context['msg'] = "Attachments"
    
    event = get_object_or_404(Event,pk=id)
    if event.over or event.closed or event.cancelled:
        return HttpResponse("Event does not allow attachment upload at this time")
        
    context['event'] = event
    
    AttachmentFS = inlineformset_factory(Event,EventAttachment,extra=1)
    #AttachmentFS.queryset = AttachmentFS.queryset.filter(externally_uploaded=True)
    AttachmentFS.form = staticmethod(curry(AttachmentForm, event=event, externally_uploaded=True))
    
    if request.method == 'POST':
        formset = AttachmentFS(request.POST,request.FILES,instance=event, queryset = EventAttachment.objects.filter(externally_uploaded=True))
        if formset.is_valid():
            f = formset.save(commit=False)
            for i in f:
                i.externally_uploaded = True
                i.save()
            return HttpResponseRedirect(reverse('my-wo',))
        else:
            context['formset'] = formset
            
    else:
        formset = AttachmentFS(instance=event, queryset = EventAttachment.objects.filter(externally_uploaded=True))
        
        context['formset'] = formset
        
    return render_to_response('formset_crispy_attachments_ext.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def extras(request,id):
    """ This form is for adding extras to an event """
    context = RequestContext(request)
    context['msg'] = "Extras"
    
    event = get_object_or_404(Event,pk=id)
    context['event'] = event
    
    ExtrasFS = inlineformset_factory(Event,ExtraInstance,extra=1)
    ExtrasFS.form = staticmethod(curry(ExtraForm))
    
    if request.method == 'POST':
        formset = ExtrasFS(request.POST,request.FILES,instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = ExtrasFS(instance=event)
        
        context['formset'] = formset
        
    return render_to_response('formset_crispy_extras.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def oneoff(request,id):
    """ This form is for adding oneoff fees to an event """
    context = RequestContext(request)
    context['msg'] = "One-Off Charges"
    
    event = get_object_or_404(Event,pk=id)
    context['event'] = event
    
    OneOffFS = inlineformset_factory(Event,EventArbitrary,extra=1)
    
    if request.method == 'POST':
        formset = OneOffFS(request.POST,request.FILES,instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = OneOffFS(instance=event)
        
        context['formset'] = formset
        
    return render_to_response('formset_crispy_arbitrary.html', context)
    
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def viewevent(request,id):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=id)
    
    context['event'] = event
    
    return render_to_response('uglydetail.html', context)


class CCRCreate(SetFormMsgMixin,OfficerMixin,LoginRequiredMixin,CreateView):
    model = CCReport
    form_class = InternalReportForm
    template_name = "form_crispy_cbv.html"
    msg = "New Crew Chief Report"
    
    def get_form_kwargs(self):
        kwargs = super(CCRCreate, self).get_form_kwargs()
        event = get_object_or_404(Event,pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self,form):
        messages.success(self.request,"Crew Chief Report Created!", extra_tags='success')
        return super(CCRCreate,self).form_valid(form)
    
    def get_success_url(self):
        return reverse("events-detail",args=(self.kwargs['event'],))

    
class CCRUpdate(SetFormMsgMixin,OfficerMixin,LoginRequiredMixin,UpdateView):
    model = CCReport
    form_class = InternalReportForm
    template_name = "form_crispy_cbv.html"
    msg = "Update Crew Chief Report"
    
    def get_form_kwargs(self):
        kwargs = super(CCRUpdate, self).get_form_kwargs()
        event = get_object_or_404(Event,pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self,form):
        messages.success(self.request,"Crew Chief Report Updated!", extra_tags='success')
        return super(CCRUpdate,self).form_valid(form)
    
    def get_success_url(self):
        return reverse("events-detail",args=(self.kwargs['event'],))


class CCRDelete(SetFormMsgMixin,OfficerMixin,LoginRequiredMixin,DeleteView):
    model = CCReport
    template_name = "form_delete_cbv.html"
    msg = "Deleted Crew Chief Report"
    
    def get_object(self, queryset=None):
        """ Hook to ensure object isn't closed """
        obj = super(CCRDelete, self).get_object()
        if obj.event.closed:
            raise ValidationError("Event is closed")
        else:
            return obj
        
    def get_success_url(self):
        return reverse("events-detail",args=(self.kwargs['event'],))
    


class BillingCreate(SetFormMsgMixin,OfficerMixin,LoginRequiredMixin,CreateView):
    model = Billing
    form_class = BillingForm
    template_name = "form_crispy_cbv.html"
    msg = "New Bill"
    
    def get_context_data(self, **kwargs):
        context = super(BillingCreate, self).get_context_data(**kwargs)
        event = get_object_or_404(Event,pk=self.kwargs['event'])
        orgs = event.org.all()
        orgstrings = ",".join(["%s's billing account was last verified: %s" % (o.name, o.verifications.latest().date if o.verifications.exists() else "Never") for o in orgs])
        context['extra'] = orgstrings
        return context
    
    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingCreate, self).get_form_kwargs()
        event = get_object_or_404(Event,pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self,form):
        messages.success(self.request,"Bill Created!", extra_tags='success')
        return super(BillingCreate,self).form_valid(form)
    
    def get_success_url(self):
        return reverse("events-detail",args=(self.kwargs['event'],))
    
class BillingUpdate(SetFormMsgMixin,OfficerMixin,LoginRequiredMixin,UpdateView):
    model = Billing
    form_class = BillingUpdateForm
    template_name = "form_crispy_cbv.html"
    msg = "Update Bill"
    
    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingUpdate, self).get_form_kwargs()
        event = get_object_or_404(Event,pk=self.kwargs['event'])
        kwargs['event'] = event
        return kwargs

    def form_valid(self,form):
        messages.success(self.request,"Billing Updated!", extra_tags='success')
        return super(BillingUpdate,self).form_valid(form)
    
    def get_success_url(self):
        return reverse("events-detail",args=(self.kwargs['event'],))
    
class BillingDelete(OfficerMixin,LoginRequiredMixin,DeleteView):
    model = Billing
    template_name = "form_delete_cbv.html"
    msg = "Deleted Bill"
    
    def get_object(self, queryset=None):
        """ Hook to ensure object isn't closed """
        obj = super(BillingDelete, self).get_object()
        if obj.event.closed:
            raise ValidationError("Event is closed")
        else:
            return obj
        
    def get_success_url(self):
        return reverse("events-detail",args=(self.kwargs['event'],))

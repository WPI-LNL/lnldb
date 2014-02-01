from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages

from django.forms.models import inlineformset_factory
from django.utils.functional import curry
from django.db.models import Q

from events.forms import EventApprovalForm,EventDenialForm, BillingForm, BillingUpdateForm
from events.forms import CrewAssign,CrewChiefAssign, CCIForm, AttachmentForm, ExtraForm
from events.models import Event,Organization,Billing,EventCCInstance,EventAttachment,Service,ExtraInstance
from helpers.challenges import is_officer

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
        
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(e.id,)))
        else:
            context['formset'] = form
    else:
        form = EventDenialForm(instance=event)
        context['formset'] = form
    return render_to_response('form_crispy.html', context) 

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
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def extras(request,id):
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
def viewevent(request,id):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=id)
    
    context['event'] = event
    
    return render_to_response('uglydetail.html', context)

class BillingCreate(SetFormMsgMixin,OfficerMixin,LoginRequiredMixin,CreateView):
    model = Billing
    form_class = BillingForm
    template_name = "form_crispy_cbv.html"
    msg = "New Bill"
    
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
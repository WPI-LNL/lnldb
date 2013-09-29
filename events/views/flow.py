from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages

from events.forms import EventApprovalForm, BillingForm
from events.forms import CrewAssign,CrewChiefAssign
from events.models import Event,Organization,Billing
from helpers.challenges import is_officer

import datetime

from django.views.generic import UpdateView,CreateView
from helpers.mixins import LoginRequiredMixin, OfficerMixin, SetFormMsgMixin

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
    
    if request.method == 'POST':
        formset = CrewChiefAssign(request.POST,instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = CrewChiefAssign(instance=event)
        
        context['formset'] = formset
        
    return render_to_response('form_crew_chiefadd.html', context)

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
        kwargs['event'] = self.kwargs['event']
        return kwargs

    def form_valid(self,form):
        messages.success(self.request,"Bill Created!", extra_tags='success')
        return super(BillingCreate,self).form_valid(form)
    
    def get_success_url(self):
        return reverse("events-detail",args=(self.kwargs['event'],))
    
class BillingUpdate(SetFormMsgMixin,OfficerMixin,LoginRequiredMixin,UpdateView):
    model = Billing
    form_class = BillingForm
    template_name = "form_crispy_cbv.html"
    msg = "Update Bill"
    
    def get_form_kwargs(self):
        # pass "user" keyword argument with the current user to your form
        kwargs = super(BillingUpdate, self).get_form_kwargs()
        kwargs['event'] = self.kwargs['event']
        return kwargs

    def form_valid(self,form):
        messages.success(self.request,"Billing Updated!", extra_tags='success')
        return super(BillingUpdate,self).form_valid(form)
    
    def get_success_url(self):
        return reverse("events-detail",args=(self.kwargs['event'],))
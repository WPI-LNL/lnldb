from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages

from events.forms import EventApprovalForm
from events.forms import CrewAssign,CrewChiefAssign
from events.models import Event,Organization
from helpers.challenges import is_officer

import datetime

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def approval(request,id):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=id)
    if event.approved:
        pass # gb2 event page
    
    
    if request.method == 'POST':
        form = EventApprovalForm(request.POST,instance=event)
        e = form.save(commit=False)
        e.approved = True
        e.save()
        # confirm with user
        messages.add_message(request, messages.INFO, 'Approved Event')
        
        return HttpResponseRedirect(reverse('events.views.flow.viewevent',args=(e.id,)))
    else:
        form = EventApprovalForm(instance=event)
        context['formset'] = form
        return render_to_response('form_crispy.html', context) 
    
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
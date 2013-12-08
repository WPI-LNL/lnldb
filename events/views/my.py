from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.models import User

from events.models import Event,Organization,CCReport,Hours
from events.forms import ReportForm,MKHoursForm,EditHoursForm

import datetime,time

from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_lnlmember

### USER FACING SHIT
@login_required
def my(request):
    """ Landing Page For User Related Functions"""
    context = RequestContext(request)

    is_lnl = is_lnlmember(request.user)
    context['is_lnl'] = is_lnl
    return render_to_response('my.html', context)


@login_required
def myacct(request):
    """ Account Change Page """
    context = RequestContext(request)
    return render_to_response('myacct.html', context)


@login_required
def mywo(request):
    """ List Events (if lnl member will list their events)"""
    context = RequestContext(request)
    
    user = request.user
    orgs = user.orgusers.get_query_set()
    
    events = Event.objects.filter(org__in=orgs)
    l = {}
    for org in orgs:
        l[org.name] = Event.objects.filter(org=org)
    
    #context['events'] = events
    context['events'] = l
    return render_to_response('mywo.html', context)


@login_required
def myorgs(request):
    """ List of associated organizations """
    context = RequestContext(request)
    
    user = request.user
    orgs = user.orgusers.get_query_set()
        
    context['orgs'] = orgs
    return render_to_response('myorgs.html', context)


@login_required
#@user_passes_test(is_lnlmember, login_url='/lnldb/fuckoffkitty/')
def myevents(request):
    """ List Events That Have been CC'd / involved """
    context = RequestContext(request)

    user = request.user
    context['user'] = user
    
    if user.groups.exclude(name__in=["Contact"]).exists():
        member = True
    else:
        member = False
        
    context['member'] = member

    return render_to_response('myevents.html', context)

@login_required
def myeventdetail(request,id):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=id)
    
    u = request.user
    if not event.usercanseeevent(u):
        return HttpResponse("You can't see this event, sorry")
    else:
        context['event'] = event
        return render_to_response('eventdetail.html', context)
    
    
@login_required
def ccreport(request,eventid):
    context = RequestContext(request)
    context['msg'] = "Crew Chief Report"
        
    user = request.user
    
    event = user.crewchiefx.filter(pk=eventid)
    
    if not event:
        return HttpResponse("This Event Must not Have been yours")
        
    event = event[0]
    
    report,created = CCReport.objects.get_or_create(event=event, crew_chief=user)
    
    if request.method == 'POST':
        formset = ReportForm(request.POST,instance=report)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('my-events'))
        else:
            context['formset'] = formset
            
    else:
        formset = ReportForm(instance=report)
        
        context['formset'] = formset
        
    return render_to_response('mycrispy.html', context)
    
@login_required
def hours_list(request,eventid):
    context = RequestContext(request)
    user = request.user
    
    event = user.crewchiefx.filter(pk=eventid)
    
    if not event:
        return HttpResponse("You must not have cc'd this event")
    event = event[0]
    context['event'] = event
    
    hours = event.hours.all()
    context['hours'] = hours
        
    
    return render_to_response('myhours.html', context)

@login_required
def hours_mk(request,eventid):
    context = RequestContext(request)
    
    user = request.user
    event = user.crewchiefx.filter(pk=eventid)
    if not event:
        return HttpResponse("You must not have cc'd this event")
    event = event[0]
    context['msg'] = "Hours for '%s'" % event.event_name
    if request.method == 'POST':
        formset = MKHoursForm(event,request.POST)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('my-cchours',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = MKHoursForm(event)
        
        context['formset'] = formset
        
    return render_to_response('mycrispy.html', context)

@login_required
def hours_edit(request,eventid,userid):
    context = RequestContext(request)
    user = request.user
    event = user.crewchiefx.filter(pk=eventid)
    if not event:
        return HttpResponse("You must not have cc'd this event")
    event = event[0]
    
    hours = get_object_or_404(Hours,event=event,user_id=userid)
    u = get_object_or_404(User,pk=userid)
    context['msg'] = "Hours for '%s' on '%s'" % (u,event.event_name)
    if request.method == 'POST':
        formset = EditHoursForm(request.POST,instance=hours)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('my-cchours',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = EditHoursForm(instance=hours)
        
        context['formset'] = formset
        
    return render_to_response('mycrispy.html', context)
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.models import User

from events.models import Event,Organization,CCReport,Hours
from events.forms import ReportForm,MKHoursForm,EditHoursForm,SelfServiceOrgRequestForm

import datetime,time
from django.utils import timezone

from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_lnlmember

from emails.generators import generate_selfservice_notice_email

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
def myorgform(request):
    """ Organization Creation Request Form"""
    context = RequestContext(request)
    context['msg'] = "Client Request"
    if request.method == "POST":
        form = SelfServiceOrgRequestForm(request.POST)
        if form.is_valid():
            email_context = {}
            email_context['client_name'] = form.cleaned_data['client_name']
            email_context['email'] = form.cleaned_data['email']
            email_context['address'] = form.cleaned_data['address']
            email_context['phone'] = form.cleaned_data['phone']
            email_context['fund_info'] = form.cleaned_data['fund_info']
            email_context['user'] = request.user
            email_context['submitted_ip'] = request.META['REMOTE_ADDR']
            email = generate_selfservice_notice_email(email_context)
            email.send()
            return render_to_response('org.service.html', context)
        else:
            context['formset'] = form
            return render_to_response('mycrispy.html', context)
    else:
        form = SelfServiceOrgRequestForm()
        context['formset'] = form
    
        return render_to_response('mycrispy.html', context)
        

# lnl facing

@login_required
#@user_passes_test(is_lnlmember, login_url='/lnldb/fuckoffkitty/')
def myevents(request):
    """ List Events That Have been CC'd / involved """
    context = RequestContext(request)

    user = request.user
    context['user'] = user
    
    now = datetime.datetime.now(timezone.get_current_timezone())
    context['now'] = now
    
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
def eventfiles(request,eventid):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=eventid)
    
    context['event'] = event
    return render_to_response('myeventfiles.html',context)
@login_required
def ccreport(request,eventid):
    context = RequestContext(request)
    
        
    user = request.user
    
    event = user.ccinstances.filter(event__pk=eventid)
    
    if not event:
        return HttpResponse("This Event Must not Have been yours, or is closed")
    if not event.reports_editable:
        return HttpResponse("The deadline for report submission and hours has past...")
        
    event = event[0].event
    x = event.ccinstances.filter(crew_chief=user)
    context['msg'] = "Crew Chief Report for '<em>%s</em>' (%s)" % (event,",".join([str(i.service) for i in x]))
    
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
    
    event = user.ccinstances.filter(event__pk=eventid)
    
    if not event:
        return HttpResponse("You must not have cc'd this event, or it's closed")
    event = event[0].event
    context['event'] = event
    
    hours = event.hours.all()
    context['hours'] = hours
        
    
    return render_to_response('myhours.html', context)

@login_required
def hours_mk(request,eventid):
    context = RequestContext(request)
    
    user = request.user
    event = user.ccinstances.filter(event__pk=eventid)
    if not event:
        return HttpResponse("You must not have cc'd this event, or is closed")
    if not event.reports_editable:
        return HttpResponse("The deadline for report submission and hours has past...")
    event = event[0].event
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
    event = user.ccinstances.filter(event__pk=eventid)
    if not event:
        return HttpResponse("You must not have cc'd this event, or it's closed")
    if not event.reports_editable:
        return HttpResponse("The deadline for report submission and hours has past...")
    event = event[0].event
    
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
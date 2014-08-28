from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.models import User
from django.forms.models import inlineformset_factory
from django.utils.functional import curry
from django.db.models import Q

from events.models import Event,Organization,CCReport,Hours
from events.forms import ReportForm,MKHoursForm,EditHoursForm,SelfServiceOrgRequestForm,WorkorderRepeatForm

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
    ic_orgs = user.orgowner.get_query_set()
    
    ##combined = orgs|ic_orgs
    #combined = ic_orgs
    values = orgs.distinct().values_list('id',flat=True)
    
    events = Event.objects.filter(org__in=values)
    l = {}
    for org in orgs:
        l[org.name] = Event.objects.filter(org=org)
    
    #context['events'] = events
    context['events'] = l
    owned = ic_orgs.values_list('name',flat=True)
    assoc = orgs.values_list('name',flat=True)
    context['owned'] = list(set(list(owned) + list(assoc)))
    return render_to_response('mywo.html', context)

@login_required
def myworepeat(request,eventid):
    context = RequestContext(request)
    context['msg'] = "Workorder Repeat"
    
    event = get_object_or_404(Event,pk=eventid)
    if request.method == "POST":
        f = WorkorderRepeatForm(request.POST,instance=event)
        if f.is_valid():
            o = f.save(commit=False)
            o.contact = request.user
            # reset some fields for our standard workflow
            o.id = None # for copy
            o.closed = False
            o.closed_on = None
            o.closed_by = None
            o.approved = False
            o.approved_on = None
            o.approved_by = None
            o.cancelled = False
            o.cancelled_on = None
            o.cancelled_by = None
            o.cancelled_reason = None
            o.save()
            return render_to_response('wizard_finished.html',context)
        else:
            context['formset'] = f
            return render_to_response('mycrispy.html', context)
    else:
        f = WorkorderRepeatForm(instance=event)
        context['formset'] = f
        return render_to_response('mycrispy.html', context)
    


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
    context['extra_text'] = 'Note: The information being requested here is not your personal information, this can be edited <a href="%s"> here </a>. This information should relate to the client account that is being requested and should only mirror your personal information if you are requesting a personal account be made.' % (reverse("my-acct"))
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
        

### lnl facing

@login_required
#@user_passes_test(is_lnlmember, login_url='/lnldb/fuckoffkitty/')
def myevents(request):
    """ List Events That Have been CC'd / involved """
    context = RequestContext(request)

    user = request.user
    context['user'] = user
    
    
    totalhours = sum([x.hours for x in user.hours.all()])
    context['totalhours'] = totalhours
    
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
    """ Shows detail for users event """
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
    """ Files for an event"""
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=eventid)
    
    context['event'] = event
    return render_to_response('myeventfiles.html',context)



### Views Relating to Crew Chiefs
@login_required
def ccreport(request,eventid):
    """ Submits a crew chief report """
    context = RequestContext(request)
    
        
    user = request.user
    
    uevent = user.ccinstances.filter(event__pk=eventid)
    # check that the event in question belongs to the user
    if not uevent:
        return HttpResponse("This Event Must not Have been yours, or is closed")
    
    event = Event.objects.get(pk=eventid)
    if not event.reports_editable:
        return HttpResponse("The deadline for report submission and hours has past...")
        
    # get event
    event = uevent[0].event
    x = event.ccinstances.filter(crew_chief=user)
    context['msg'] = "Crew Chief Report for '<em>%s</em>' (%s)" % (event,",".join([str(i.service) for i in x]))
    
    # create report
    report,created = CCReport.objects.get_or_create(event=event, crew_chief=user)
    
    # standard save flow
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
    """ Lists a users' hours """
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
    """ Hour Entry Form for CC """
    context = RequestContext(request)
    
    user = request.user
    uevent = user.ccinstances.filter(event__pk=eventid)
    
    if not uevent:
        return HttpResponse("This Event Must not Have been yours, or is closed")
    
    event = Event.objects.get(pk=eventid)
    if not event.reports_editable:
        return HttpResponse("The deadline for report submission and hours has past...")
        
    event = uevent[0].event
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
    """ Hour Entry Form for CC (editing)"""
    context = RequestContext(request)
    user = request.user
    uevent = user.ccinstances.filter(event__pk=eventid)
    
    if not uevent:
        return HttpResponse("You must not have cc'd this event, or it's closed")
    
    event = Event.objects.get(pk=eventid)
    if not event.reports_editable:
        return HttpResponse("The deadline for report submission and hours has past...")
    event = uevent[0].event
    
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

@login_required
def hours_bulk(request,eventid):
    """ Bulk Hours Entry Form """
    context = RequestContext(request)
    user = request.user
    uevent = user.ccinstances.filter(event__pk=eventid)
    
    if not uevent:
        return HttpResponse("You must not have cc'd this event, or it's closed")
    
    event = Event.objects.get(pk=eventid)
    if not event.reports_editable:
        return HttpResponse("The deadline for report submission and hours has past...")
    event = uevent[0].event
    
    context['msg'] = "Bulk Hours Entry"
    
    context['event'] = event
    
    FS = inlineformset_factory(Event,Hours,extra=15)
    FS.form = staticmethod(curry(MKHoursForm, event=event))
    
    if request.method == 'POST':
        formset = FS(request.POST,instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('my-cchours',args=(event.id,)))
        else:
            context['formset'] = formset
            
    else:
        formset = FS(instance=event)
        
        context['formset'] = formset
        
    return render_to_response('formset_hours_bulk.html', context)
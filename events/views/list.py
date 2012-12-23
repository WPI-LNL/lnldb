# Create your views here.

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.models import Event,Organization

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_officer

import datetime,time
### EVENT VIEWS
# these more or less do what they say on the tin. Might need some work and refinement
@login_required
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def upcoming(request,limit=True):
    """
    Lists Upcoming Events
    if limit = False, then it'll show all upcoming events that are more than a week away.
    """
    context = RequestContext(request)
    
    today = datetime.date.today()
    weekfromnow = today + datetime.timedelta(weeks=1)
    
    events = Event.objects.filter(approved=True).filter(closed=False).filter(paid=False).filter(datetime_start__gte=today)
    if limit:
        events = events.filter(datetime_start__lte=weekfromnow)
    
    context['events'] = events
    
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def incoming(request):
    context = RequestContext(request)
    
    events = Event.objects.filter(approved=False).filter(closed=False).filter(paid=False)
    
    context['events'] = events
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def openworkorders(request):
    context = RequestContext(request)
    
    events = Event.objects.filter(closed=False)
    
    context['events'] = events
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def paid(request):
    context = RequestContext(request)
    
    events = Event.objects.filter(approved=True).filter(paid=True)
    
    context['events'] = events
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def unpaid(request):
    context = RequestContext(request)
    
    today = datetime.date.today()
    now = time.time()
    events = Event.objects.filter(approved=True).filter(time_setup_start__lte=datetime.datetime.now()).filter(date_setup_start__lte=today)
    
    context['events'] = events
    return render_to_response('events.html', context)    


@login_required
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def closed(request):
    context = RequestContext(request)
     
    events = Event.objects.filter(closed=True)
    
    context['events'] = events
    return render_to_response('events.html', context)       


@login_required
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def assigncrew(request,id):
    context = RequestContext(request)
    
    event = get_object_or_404(Event,pk=id)
    
    if request.method == 'POST':
        formset = CrewAssign(request.POST)
        if formset.is_valid():
            formset.save()
            
        else:
            context['formset'] = formset
            
    else:
        formset = CrewAssign
        
        context['formset'] = formset
        
    return render_to_response('form_master.html', context)
    


@login_required
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def viewevent(request,id):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=id)
    
    context['event'] = event
    
    return render_to_response('uglydetail.html', context)
    
# Create your views here.

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test

from events.forms import WorkorderSubmit,CrewAssign,OrgForm
from events.models import Event,Organization
from helpers.challenges import is_officer

import datetime

### FRONT 3 PAGES
def index(request):
    """Landing Page"""
    context = RequestContext(request)
    
    is_off = is_officer(request.user)
    context['is_officer'] = is_off
    return render_to_response('index.html', context) 

def workorder(request):
    """ Workorder Page, deprecated cause CBV workorder in wizard.py"""
    context = RequestContext(request)
    
    if request.method == 'POST':
        formset = WorkorderSubmit(request.POST)
        if formset.is_valid():
            neworder = formset.save(commit=False)
            neworder.submitted_by = request.user
            neworder.submitted_ip = request.META['REMOTE_ADDR']
            neworder.save()

        else:
            context['formset'] = formset
            #todo: BITCH

    else:
        formset = WorkorderSubmit()

        context['formset'] = formset
        
    return render_to_response('workorder.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def admin(request,msg=None):
    """ admin landing page """

    context = RequestContext(request)
    context['msg'] = msg
    
    today = datetime.datetime.now()
    # get today's events 
    starting = Event.objects.filter(datetime_start__year=today.year,datetime_start__month=today.month,datetime_start__day=today.day)
    context['starting'] = starting
    
    #in progress
    ip = Event.objects.filter(datetime_start__lte=today,datetime_end__gte=today)
    context['ip'] = ip
    
    #ended
    et =  Event.objects.filter(datetime_end__year=today.year,datetime_end__month=today.month,datetime_end__day=today.day)
    context['et'] = et
    
    context['now'] = today
    
    return render_to_response('admin.html', context) 


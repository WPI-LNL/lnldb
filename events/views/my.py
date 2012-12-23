from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.models import Event,Organization

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
    
    events = Event.objects.filter(group__in=orgs)
    
    context['events'] = events
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
@user_passes_test(is_lnlmember, login_url='/lnldb/fuckoffkitty/')
def myevents(request):
    """ List Events That Have been CC'd / involved """
    context = RequestContext(request)

    user = request.user

    return render_to_response('myevents.html', context)
    
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
@user_passes_test(is_officer, login_url='/lnldb/fuckoffkitty/')
def admin(request,msg=None):
    """ admin landing page """
    context = RequestContext(request)
    context['msg'] = msg
    return render_to_response('admin.html', context) 


# Create your views here.

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.models import Event,Organization
from events.forms import IOrgForm,ExternalOrgUpdateForm

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_officer

import datetime,time

### ORGANIZATION VIEWS

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def vieworgs(request):
    """ Views all organizations, """
    #todo add filters
    context = RequestContext(request)
    
    orgs = Organization.objects.all()
    
    context['orgs'] = orgs
    
    return render_to_response('orgs.html', context)
    
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')    
def addeditorgs(request,id=None):
    """form for adding an org """
    # need to fix this 
    context = RequestContext(request)
    if id:
        instance = get_object_or_404(Organization,pk=id)
        msg = "Edit Client"
    else:
        instance= None
        msg = "New Client"
        
    if request.method == 'POST': 
        formset = IOrgForm(request.POST,instance=instance)
        if formset.is_valid():
            formset.save()
            #return HttpResponseRedirect(reverse('events.views.admin', kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('events.views.orgs.vieworgs'))
        
        else:
            context['formset'] = formset
    else:
        
        formset = IOrgForm(instance=instance)
        
        context['formset'] = formset
        context['msg'] = msg
    
    return render_to_response('form_crispy.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')    
def orgdetail(request,id):
    context = RequestContext(request)
    org = get_object_or_404(Organization,pk=id)
    context['org'] = org
    return render_to_response('org_detail.html', context)

### External Form Editing Views
@login_required
def orglist(request):
    context = RequestContext(request)
    orgs = Organization.objects.filter(user_in_charge=request.user)
    context['orgs'] = orgs
    
    return render_to_response('ext_orgs.html',context)

def orgedit(request,id):
    context = RequestContext(request)
    orgs = Organization.objects.filter(user_in_charge=request.user)
    
    org = get_object_or_404(orgs,pk=id)
    msg = "> Modify Organization"
    context['msg'] = msg
    
    if request.method == 'POST': 
        formset = ExternalOrgUpdateForm(request.POST,instance=org)
        if formset.is_valid():
            formset.save()
            #return HttpResponseRedirect(reverse('events.views.admin', kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('events.views.orgs.orglist'))
        
        else:
            context['formset'] = formset
    else:
        
        formset = ExternalOrgUpdateForm(instance=org)
        
        context['formset'] = formset
        
    
    return render_to_response('mycrispy.html', context)
# Create your views here.

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.models import Event,Organization

import datetime,time

### ORGANIZATION VIEWS

def vieworgs(request):
    """ Views all organizations, """
    #todo add filters
    context = RequestContext(request)
    
    orgs = Organization.objects.all()
    
    context['orgs'] = orgs
    
    return render_to_response('orgs.html', context)
    
    
def addorgs(request):
    """form for adding an org """
    # need to fix this 
    context = RequestContext(request)
    
    if request.method == 'POST': 
        formset = OrgForm(request.POST)
        if formset.is_valid():
            formset.save()
            #return HttpResponseRedirect(reverse('events.views.admin', kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('events.views.admin'))
        
        else:
            context['formset'] = formset
    else:
        msg = "New Client"
        formset = OrgForm
        
        context['formset'] = formset
        context['msg'] = msg
    
    return render_to_response('form_master.html', context)

#TODO edit org form
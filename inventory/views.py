from django.template.defaultfilters import slugify
# Create your views here.


from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.forms import WorkorderSubmit,CrewAssign,OrgForm
from inventory.forms import InvForm

import datetime,time

from inventory.models import Equipment,Category
SUCCESS_MSG_INV = "Successfully added new inventory Item"
def view(request):
    context = RequestContext(request)
    
    inv = Equipment.objects.all()
    
    context['inv'] = inv
    return render_to_response('inv.html', context)


def catview(request,cat):
    pass


def add(request):
    context = RequestContext(request)
    
    if request.method == 'POST': 
        formset = InvForm(request.POST)
        if formset.is_valid():
            formset.save()
            #return HttpResponseRedirect(reverse('lnldb.events.views.admin', kwargs={'msg':slugify(SUCCESS_MSG_INV)}))
            return HttpResponseRedirect(reverse('events.views.admin'))
        
        else:
            context['formset'] = formset
    else:
        msg = "New Inventory"
        formset = InvForm
        
        context['formset'] = formset
        context['msg'] = msg
    
    return render_to_response('form_master.html', context)
    
def categories(request):
    context = RequestContext(request)
    
    categories = Category.objects.all()
    
    context['cats'] = categories
    return render_to_response('cats.html', context)

#TODO fix all this shit to make it less shit
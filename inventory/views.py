from django.template.defaultfilters import slugify
# Create your views here.


from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.forms import WorkorderSubmit,CrewAssign,OrgForm
from inventory.models import Equipment,Category,SubCategory
from inventory.forms import InvForm,EntryForm

import datetime,time


SUCCESS_MSG_INV = "Successfully added new inventory Item"
def view(request):
    context = RequestContext(request)
    
    inv = Equipment.objects.all()
    categories = Category.objects.all()
    
    context['h2'] = "Inventory List"
    context['inv'] = inv
    context['cats'] = categories
    return render_to_response('inv.html', context)


def cat(request,category):
    context = RequestContext(request)
    cat = get_object_or_404(Category,name=category)
    
    inv = Equipment.objects.filter(subcategory__category=cat)
    subcategories = cat.subcategory_set.all()
    
    context['h2'] = "Category: %s" % cat.name
    context['inv'] = inv
    context['scats'] = subcategories
    return render_to_response('inv.html', context)

def subcat(request,category,subcategory):
    context = RequestContext(request)
    cat = get_object_or_404(SubCategory,name=subcategory)
    
    inv = Equipment.objects.filter(subcategory=cat)
    
    context['h2'] = "SubCategory: %s" % cat.name
    context['inv'] = inv
    return render_to_response('inv.html', context)


def add(request):
    context = RequestContext(request)
    
    if request.method == 'POST': 
        formset = InvForm(request.POST)
        if formset.is_valid():
            x= formset.save()
            #return HttpResponseRedirect(reverse('lnldb.events.views.admin', kwargs={'msg':slugify(SUCCESS_MSG_INV)}))
            return HttpResponseRedirect(reverse('inventory.views.view'))
        
        else:
            context['formset'] = formset
    else:
        msg = "New Inventory"
        formset = InvForm()
        
        context['formset'] = formset
        context['msg'] = msg
    
    return render_to_response('form_crispy.html', context)
    
def categories(request):
    context = RequestContext(request)
    
    categories = Category.objects.all()
    
    context['cats'] = categories
    return render_to_response('cats.html', context)

#TODO fix all this shit to make it less shit

def detail(request,id):
    context = RequestContext(request)
    e = get_object_or_404(Equipment,pk=id)
    context['e'] = e 
    
    return render_to_response('invdetail.html', context)

def addentry(request,id):
    context = RequestContext(request)
    msg = "New Maintenance Entry"
    context['msg'] = msg
    
    inv = get_object_or_404(Equipment,pk=id)
    
    if request.method == 'POST': 
        formset = EntryForm(request.user,inv,request.POST)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('inv-detail', args=(id,)))
        
        else:
            context['formset'] = formset
    else:
        
        formset = EntryForm(request.user,inv)
        
        context['formset'] = formset
        
    
    return render_to_response('form_crispy.html', context)
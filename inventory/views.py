# Create your views here.


from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.template import RequestContext

from inventory.models import Equipment, Category, SubCategory
from inventory.forms import InvForm, EntryForm


SUCCESS_MSG_INV = "Successfully added new inventory Item"


def view(request):
    context = {}

    inv = Equipment.objects.all()
    categories = Category.objects.all()

    context['h2'] = "Inventory List"
    context['inv'] = inv
    context['cats'] = categories
    return render(request, 'inv.html', context)


def cat(request, category):
    context = {}
    cat = get_object_or_404(Category, name=category)

    inv = Equipment.objects.filter(subcategory__category=cat)
    subcategories = cat.subcategory_set.all()

    context['h2'] = "Category: %s" % cat.name
    context['inv'] = inv
    context['scats'] = subcategories
    return render(request, 'inv.html', context)


def subcat(request, category, subcategory):
    context = {}
    cat = get_object_or_404(SubCategory, name=subcategory)

    inv = Equipment.objects.filter(subcategory=cat)

    context['h2'] = "SubCategory: %s" % cat.name
    context['inv'] = inv
    return render(request, 'inv.html', context)


def add(request):
    context = {}

    if request.method == 'POST':
        formset = InvForm(request.POST)
        if formset.is_valid():
            formset.save()
            # return HttpResponseRedirect(reverse('lnldb.events.views.admin', kwargs={'msg':slugify(SUCCESS_MSG_INV)}))
            return HttpResponseRedirect(reverse('inventory.views.view'))

        else:
            context['formset'] = formset
    else:
        msg = "New Inventory"
        formset = InvForm()

        context['formset'] = formset
        context['msg'] = msg

    return render(request, 'form_crispy.html', context)


def categories(request):
    context = {}

    categories = Category.objects.all()

    context['cats'] = categories
    return render(request, 'cats.html', context)


# TODO fix all this shit to make it less shit

def detail(request, id):
    context = {}
    e = get_object_or_404(Equipment, pk=id)
    context['e'] = e

    return render(request, 'invdetail.html', context)


def addentry(request, id):
    context = {}
    msg = "New Maintenance Entry"
    context['msg'] = msg

    inv = get_object_or_404(Equipment, pk=id)

    if request.method == 'POST':
        formset = EntryForm(request.user, inv, request.POST)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse('inv-detail', args=(id,)))

        else:
            context['formset'] = formset
    else:

        formset = EntryForm(request.user, inv)

        context['formset'] = formset

    return render(request, 'form_crispy.html', context)
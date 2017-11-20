from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.core.urlresolvers import reverse
from django.db.models import Count
from django.forms.models import inlineformset_factory
from django.http import (HttpResponseBadRequest, HttpResponseNotFound,
                         HttpResponseRedirect)
from django.shortcuts import get_object_or_404, render

from . import forms, models

NUM_IN_PAGE = 25


@login_required
def view_all(request):
    if not request.user.has_perm('inventory.view_equipment'):
        raise PermissionDenied

    context = {}
    inv = models.EquipmentClass.objects.order_by('name') \
        .annotate(item_count=Count('items'))
    categories = models.EquipmentCategory.objects.all()

    paginator = Paginator(inv, NUM_IN_PAGE)

    page = request.GET.get('page')
    try:
        context['inv'] = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        context['inv'] = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        context['inv'] = paginator.page(paginator.num_pages)

    context['h2'] = "Inventory: Item List"
    context['cats'] = categories
    return render(request, 'inventory/list.html', context)


@login_required
def cat(request, category_id):
    if not request.user.has_perm('inventory.view_equipment'):
        raise PermissionDenied

    context = {}
    category = get_object_or_404(models.EquipmentCategory, pk=category_id)

    if 'exclusive' in request.GET and request.GET['exclusive']:
        inv = models.EquipmentClass.objects.filter(category=category)
        context['exclusive'] = True
    else:
        inv = models.EquipmentClass.objects.filter(category__in=category.get_descendants_inclusive)
        context['exclusive'] = False

    inv = inv.order_by('category__level', 'category__name', 'name') \
        .annotate(item_count=Count('items'))
    subcategories = models.EquipmentCategory.objects.all()

    paginator = Paginator(inv, NUM_IN_PAGE)

    page = request.GET.get('page')
    try:
        context['inv'] = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        context['inv'] = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        context['inv'] = paginator.page(paginator.num_pages)

    context['h2'] = "Inventory: %s" % category.name
    context['cat'] = category
    context['cats'] = subcategories

    return render(request, 'inventory/list.html', context)


@login_required
def quick_bulk_add(request, type_id):
    if request.method != 'POST':
        return HttpResponseBadRequest('Invalid operation')
    if 'num_to_add' not in request.POST:
        return HttpResponseBadRequest('Missing parameters')

    try:
        num_to_add = int(request.POST['num_to_add'])
    except (ValueError, TypeError):
        return HttpResponseBadRequest('Bad parameters')

    try:
        e_type = models.EquipmentClass.objects.get(pk=int(type_id))
    except models.EquipmentClass.DoesNotExist:
        return HttpResponseNotFound()

    if not request.user.has_perm('inventory.add_equipmentitem', e_type):
        raise PermissionDenied

    models.EquipmentItem.objects.bulk_add_helper(e_type, num_to_add)

    messages.add_message(request, messages.SUCCESS,
                         "%d items added and saved. Now editing." % num_to_add)

    return HttpResponseRedirect(reverse('inventory:bulk_edit',
                                        kwargs={'type_id': type_id}))


@login_required
def quick_bulk_edit(request, type_id):
    e_type = get_object_or_404(models.EquipmentClass, pk=int(type_id))

    if not request.user.has_perm('inventory.change_equipmentitem', e_type):
        raise PermissionDenied

    can_delete = request.user.has_perm('inventory.delete_equipmentitem', e_type)
    fs_factory = inlineformset_factory(models.EquipmentClass, models.EquipmentItem,
                                       form=forms.EquipmentItemForm,
                                       extra=0, can_delete=can_delete)

    if request.method == 'POST':
        formset = fs_factory(request.POST, request.FILES, instance=e_type)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Items saved.")
            return HttpResponseRedirect(reverse('inventory:type_detail',
                                                kwargs={'type_id': type_id}))
    else:
        formset = fs_factory(instance=e_type)
        qs = models.EquipmentCategory.possible_locations()
        for form in formset:
            form.fields['home'].queryset = qs
    return render(request, "formset_grid.html", {
        'msg': "Bulk inventory edit for '%s'" % e_type.name,
        "formset": formset,
        'form_show_errors': True
    })


@login_required
def type_edit(request, type_id):
    try:
        e_type = models.EquipmentClass.objects.get(pk=int(type_id))
    except models.EquipmentClass.DoesNotExist:
        return HttpResponseNotFound()

    if not request.user.has_perm('inventory.change_equipmentclass', e_type):
        raise PermissionDenied

    if request.method == 'POST':
        formset = forms.EquipmentClassForm(request.POST, request.FILES, instance=e_type)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Equipment type saved.")
            return HttpResponseRedirect(reverse('inventory:type_detail',
                                                kwargs={'type_id': type_id}))
    else:
        formset = forms.EquipmentClassForm(instance=e_type)
    return render(request, "form_crispy.html", {
        'msg': "Edit '%s'" % e_type.name,
        "formset": formset,
    })


@login_required
def type_mk(request):
    if not request.user.has_perm('inventory.add_equipmentclass'):
        raise PermissionDenied

    category = request.GET.get('default_cat')

    if request.method == 'POST':
        formset = forms.EquipmentClassForm(request.POST, request.FILES)
        if formset.is_valid():
            obj = formset.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Equipment type added.")
            return HttpResponseRedirect(reverse('inventory:type_detail',
                                                kwargs={'type_id': obj.pk}))
    else:
        formset = forms.EquipmentClassForm(initial={'category': category})
    return render(request, "form_crispy.html", {
        'msg': "Create Equipment Type",
        "formset": formset,
    })


@login_required
def type_rm(request, type_id):
    obj = get_object_or_404(models.EquipmentClass, pk=int(type_id))
    return_page = reverse('inventory:cat', args=[obj.category.pk])

    if not request.user.has_perm('inventory.delete_equipmentclass', obj):
        raise PermissionDenied

    if request.method == 'POST':
        if obj.items.exists():
            return HttpResponseBadRequest("There are still items of this type")
        else:
            obj.delete()
            return HttpResponseRedirect(return_page)
    else:
        return HttpResponseBadRequest("Bad method")


@login_required
def cat_edit(request, category_id):
    category = get_object_or_404(models.EquipmentCategory, pk=category_id)

    if not request.user.has_perm('inventory.change_equipmentcategory', category):
        raise PermissionDenied

    if request.method == 'POST':
        formset = forms.CategoryForm(request.POST, request.FILES, instance=category)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Category saved.")
            return HttpResponseRedirect(reverse('inventory:cat',
                                                kwargs={'category_id': category_id}))
    else:
        formset = forms.CategoryForm(instance=category)
    return render(request, "form_crispy.html", {
        'msg': "Edit Category",
        "formset": formset,
    })


@login_required
def cat_mk(request):
    if not request.user.has_perm('inventory.add_equipmentcategory'):
        raise PermissionDenied

    parent = request.GET.get('parent')

    if request.method == 'POST':
        formset = forms.CategoryForm(request.POST, request.FILES)
        if formset.is_valid():
            obj = formset.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Category added.")
            return HttpResponseRedirect(reverse('inventory:cat',
                                                kwargs={'category_id': obj.pk}))
    else:
        formset = forms.CategoryForm(initial={'parent': parent})
    return render(request, "form_crispy.html", {
        'msg': "Create Category",
        "formset": formset,
    })


@login_required
def cat_rm(request, category_id):
    ecat = get_object_or_404(models.EquipmentCategory, pk=int(category_id))
    if ecat.parent:
        return_url = reverse('inventory:cat', args=[ecat.parent.pk])
    else:
        return_url = reverse('inventory:view_all')

    if not request.user.has_perm('inventory.delete_equipmentcategory', ecat):
        raise PermissionDenied

    if request.method == 'POST':
        if ecat.get_children().exists():
            return HttpResponseBadRequest("There are still subcategories of this type")
        elif ecat.equipmentclass_set.exists():
            return HttpResponseBadRequest("There are still items in this category")
        else:
            ecat.delete()
            return HttpResponseRedirect(return_url)
    else:
        return HttpResponseBadRequest("Bad method")


@login_required
def fast_mk(request):
    if not request.user.has_perm('inventory.add_equipmentitem'):
        raise PermissionDenied

    try:
        category = int(request.GET['default_cat'])
    except (ValueError, KeyError, TypeError):
        category = None

    if request.method == 'POST':
        formset = forms.FastAdd(request.user, request.POST, request.FILES)
        if formset.is_valid():
            obj = formset.save()
            messages.add_message(request, messages.SUCCESS,
                                 "%d items added and saved. Now editing." % formset.cleaned_data['num_to_add'])
            return HttpResponseRedirect(reverse('inventory:bulk_edit',
                                                kwargs={'type_id': obj.pk}))
    else:
        formset = forms.FastAdd(request.user, initial={'item_cat': category})
    return render(request, "form_crispy.html", {
        'msg': "Fast Add Item(s)",
        "formset": formset,
    })


# def add(request):
#     context = {}
#
#     if request.method == 'POST':
#         formset = InvForm(request.POST)
#         if formset.is_valid():
#             formset.save()
#             # return HttpResponseRedirect(reverse("home",
#  kwargs={'msg':slugify(SUCCESS_MSG_INV)}))
#             return HttpResponseRedirect(reverse('inventory:view'))
#
#         else:
#             context['formset'] = formset
#     else:
#         msg = "New Inventory"
#         formset = InvForm()
#
#         context['formset'] = formset
#         context['msg'] = msg
#
#     return render(request, 'form_crispy.html', context)
#
#
#


@login_required
def type_detail(request, type_id):
    e = get_object_or_404(models.EquipmentClass, pk=type_id)

    return render(request, 'inventory/type_detail.html', {
        'breadcrumbs': e.breadcrumbs,
        'equipment': e
    })


@login_required
def item_detail(request, item_id):
    item = get_object_or_404(models.EquipmentItem, pk=item_id)

    return render(request, 'inventory/item_detail.html', {
        'breadcrumbs': item.breadcrumbs,
        'item': item
    })


@login_required
def item_edit(request, item_id):
    try:
        item = models.EquipmentItem.objects.get(pk=int(item_id))
    except models.EquipmentItem.DoesNotExist:
        return HttpResponseNotFound()

    if not request.user.has_perm('inventory.change_equipmentitem', item):
        raise PermissionDenied

    if request.method == 'POST':
        formset = forms.EquipmentItemForm(request.POST, request.FILES, instance=item)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Item saved.")
            return HttpResponseRedirect(reverse('inventory:item_detail',
                                                kwargs={'item_id': item_id}))
    else:
        formset = forms.EquipmentItemForm(instance=item)
    return render(request, "form_crispy.html", {
        'msg': "Edit '%s'" % str(item),
        "formset": formset,
    })


@login_required
def item_rm(request, item_id):
    obj = get_object_or_404(models.EquipmentItem, pk=int(item_id))
    return_page = reverse('inventory:type_detail', args=[obj.item_type.pk])

    if not request.user.has_perm('inventory.delete_equipmentitem', obj):
        raise PermissionDenied

    if request.method == 'POST':
        if obj.unsafe_to_delete:
            return HttpResponseBadRequest("There are still items of this type")
        else:
            obj.delete()
            return HttpResponseRedirect(return_page)
    else:
        return HttpResponseBadRequest("Bad method")


#
# def addentry(request, id):
#     context = {}
#     msg = "New Maintenance Entry"
#     context['msg'] = msg
#
#     inv = get_object_or_404(Equipment, pk=id)
#
#     if request.method == 'POST':
#         formset = EntryForm(request.user, inv, request.POST)
#         if formset.is_valid():
#             formset.save()
#             return HttpResponseRedirect(reverse('inv-detail', args=(id,)))
#
#         else:
#             context['formset'] = formset
#     else:
#
#         formset = EntryForm(request.user, inv)
#
#         context['formset'] = formset
#
#     return render(request, 'form_crispy.html', context)

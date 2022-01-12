from io import BytesIO
import json
import re
import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count
from django.forms.models import inlineformset_factory
from django.http import (HttpResponse, HttpResponseBadRequest, HttpResponseNotFound,
                         HttpResponseRedirect)
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls.base import reverse
from django.utils import timezone
from xhtml2pdf import pisa

from . import forms, models, api
from events.models import Location
from emails.generators import DefaultLNLEmailGenerator
from pdfs.views import link_callback

NUM_IN_PAGE = 25


@login_required
def view_all(request):
    """ Lists all items in LNL's inventory (no longer maintained - read-only) """
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
    """
    List items by category

    :param category_id: The primary key value of the equipment category
    """
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


# Inventory is currently read-only now that we are using Snipe
# @login_required
# def quick_bulk_add(request, type_id):
#     if request.method != 'POST':
#         return HttpResponseBadRequest('Invalid operation')
#     if 'num_to_add' not in request.POST:
#         return HttpResponseBadRequest('Missing parameters')
#
#     try:
#         num_to_add = int(request.POST['num_to_add'])
#     except (ValueError, TypeError):
#         return HttpResponseBadRequest('Bad parameters')
#
#     try:
#         e_type = models.EquipmentClass.objects.get(pk=int(type_id))
#     except models.EquipmentClass.DoesNotExist:
#         return HttpResponseNotFound()
#
#     if not request.user.has_perm('inventory.add_equipmentitem', e_type):
#         raise PermissionDenied
#
#     models.EquipmentItem.objects.bulk_add_helper(e_type, num_to_add)
#
#     messages.add_message(request, messages.SUCCESS,
#                          "%d items added and saved. Now editing." % num_to_add)
#
#     return HttpResponseRedirect(reverse('inventory:bulk_edit',
#                                         kwargs={'type_id': type_id}))
#
#
# @login_required
# def quick_bulk_edit(request, type_id):
#     e_type = get_object_or_404(models.EquipmentClass, pk=int(type_id))
#
#     if not request.user.has_perm('inventory.change_equipmentitem', e_type):
#         raise PermissionDenied
#
#     can_delete = request.user.has_perm('inventory.delete_equipmentitem', e_type)
#     fs_factory = inlineformset_factory(models.EquipmentClass, models.EquipmentItem,
#                                        form=forms.EquipmentItemForm,
#                                        extra=0, can_delete=can_delete)
#
#     if request.method == 'POST':
#         formset = fs_factory(request.POST, request.FILES, instance=e_type)
#         if formset.is_valid():
#             formset.save()
#             messages.add_message(request, messages.SUCCESS,
#                                  "Items saved.")
#             return HttpResponseRedirect(reverse('inventory:type_detail',
#                                                 kwargs={'type_id': type_id}))
#     else:
#         formset = fs_factory(instance=e_type)
#         qs = models.EquipmentCategory.possible_locations()
#         for form in formset:
#             form.fields['home'].queryset = qs
#     return render(request, "formset_grid.html", {
#         'msg': "Bulk inventory edit for '%s'" % e_type.name,
#         "formset": formset,
#         'form_show_errors': True
#     })
#
#
# @login_required
# def type_edit(request, type_id):
#     try:
#         e_type = models.EquipmentClass.objects.get(pk=int(type_id))
#     except models.EquipmentClass.DoesNotExist:
#         return HttpResponseNotFound()
#
#     if not request.user.has_perm('inventory.change_equipmentclass', e_type):
#         raise PermissionDenied
#
#     if request.method == 'POST':
#         form = forms.EquipmentClassForm(request.POST, request.FILES, instance=e_type)
#         if form.is_valid():
#             form.save()
#             messages.add_message(request, messages.SUCCESS,
#                                  "Equipment type saved.")
#             return HttpResponseRedirect(reverse('inventory:type_detail',
#                                                 kwargs={'type_id': type_id}))
#     else:
#         form = forms.EquipmentClassForm(instance=e_type)
#     return render(request, "form_crispy.html", {
#         'msg': "Edit '%s'" % e_type.name,
#         "form": form,
#     })
#
#
# @login_required
# def type_mk(request):
#     if not request.user.has_perm('inventory.add_equipmentclass'):
#         raise PermissionDenied
#
#     category = request.GET.get('default_cat')
#
#     if request.method == 'POST':
#         form = forms.EquipmentClassForm(request.POST, request.FILES)
#         if form.is_valid():
#             obj = form.save()
#             messages.add_message(request, messages.SUCCESS,
#                                  "Equipment type added.")
#             return HttpResponseRedirect(reverse('inventory:type_detail',
#                                                 kwargs={'type_id': obj.pk}))
#     else:
#         form = forms.EquipmentClassForm(initial={'category': category})
#     return render(request, "form_crispy.html", {
#         'msg': "Create Equipment Type",
#         "form": form,
#     })
#
#
# @login_required
# def type_rm(request, type_id):
#     obj = get_object_or_404(models.EquipmentClass, pk=int(type_id))
#     return_page = reverse('inventory:cat', args=[obj.category.pk])
#
#     if not request.user.has_perm('inventory.delete_equipmentclass', obj):
#         raise PermissionDenied
#
#     if request.method == 'POST':
#         if obj.items.exists():
#             return HttpResponseBadRequest("There are still items of this type")
#         else:
#             obj.delete()
#             return HttpResponseRedirect(return_page)
#     else:
#         return HttpResponseBadRequest("Bad method")
#
#
# @login_required
# def cat_edit(request, category_id):
#     category = get_object_or_404(models.EquipmentCategory, pk=category_id)
#
#     if not request.user.has_perm('inventory.change_equipmentcategory', category):
#         raise PermissionDenied
#
#     if request.method == 'POST':
#         form = forms.CategoryForm(request.POST, request.FILES, instance=category)
#         if form.is_valid():
#             form.save()
#             messages.add_message(request, messages.SUCCESS,
#                                  "Category saved.")
#             return HttpResponseRedirect(reverse('inventory:cat',
#                                                 kwargs={'category_id': category_id}))
#     else:
#         form = forms.CategoryForm(instance=category)
#     return render(request, "form_crispy.html", {
#         'msg': "Edit Category",
#         "form": form,
#     })
#
#
# @login_required
# def cat_mk(request):
#     if not request.user.has_perm('inventory.add_equipmentcategory'):
#         raise PermissionDenied
#
#     parent = request.GET.get('parent')
#
#     if request.method == 'POST':
#         form = forms.CategoryForm(request.POST, request.FILES)
#         if form.is_valid():
#             obj = form.save()
#             messages.add_message(request, messages.SUCCESS,
#                                  "Category added.")
#             return HttpResponseRedirect(reverse('inventory:cat',
#                                                 kwargs={'category_id': obj.pk}))
#     else:
#         form = forms.CategoryForm(initial={'parent': parent})
#     return render(request, "form_crispy.html", {
#         'msg': "Create Category",
#         "form": form,
#     })
#
#
# @login_required
# def cat_rm(request, category_id):
#     ecat = get_object_or_404(models.EquipmentCategory, pk=int(category_id))
#     if ecat.parent:
#         return_url = reverse('inventory:cat', args=[ecat.parent.pk])
#     else:
#         return_url = reverse('inventory:view_all')
#
#     if not request.user.has_perm('inventory.delete_equipmentcategory', ecat):
#         raise PermissionDenied
#
#     if request.method == 'POST':
#         if ecat.get_children().exists():
#             return HttpResponseBadRequest("There are still subcategories of this type")
#         elif ecat.equipmentclass_set.exists():
#             return HttpResponseBadRequest("There are still items in this category")
#         else:
#             ecat.delete()
#             return HttpResponseRedirect(return_url)
#     else:
#         return HttpResponseBadRequest("Bad method")
#
#
# @login_required
# def fast_mk(request):
#     if not request.user.has_perm('inventory.add_equipmentitem'):
#         raise PermissionDenied
#
#     try:
#         category = int(request.GET['default_cat'])
#     except (ValueError, KeyError, TypeError):
#         category = None
#
#     if request.method == 'POST':
#         form = forms.FastAdd(request.user, request.POST, request.FILES)
#         if form.is_valid():
#             obj = form.save()
#             messages.add_message(request, messages.SUCCESS,
#                                  "%d items added and saved. Now editing." % form.cleaned_data['num_to_add'])
#             return HttpResponseRedirect(reverse('inventory:bulk_edit',
#                                                 kwargs={'type_id': obj.pk}))
#     else:
#         form = forms.FastAdd(request.user, initial={'item_cat': category})
#     return render(request, "form_crispy.html", {
#         'msg': "Fast Add Item(s)",
#         "form": form,
#     })


@login_required
def type_detail(request, type_id):
    """ Detail page for a group of items """
    e = get_object_or_404(models.EquipmentClass, pk=type_id)

    return render(request, 'inventory/type_detail.html', {
        'breadcrumbs': e.breadcrumbs,
        'equipment': e
    })


@login_required
def item_detail(request, item_id):
    """ Detail page for a specific item """
    item = get_object_or_404(models.EquipmentItem, pk=item_id)

    return render(request, 'inventory/item_detail.html', {
        'breadcrumbs': item.breadcrumbs,
        'item': item
    })


# @login_required
# def item_edit(request, item_id):
#     try:
#         item = models.EquipmentItem.objects.get(pk=int(item_id))
#     except models.EquipmentItem.DoesNotExist:
#         return HttpResponseNotFound()
#
#     if not request.user.has_perm('inventory.change_equipmentitem', item):
#         raise PermissionDenied
#
#     if request.method == 'POST':
#         form = forms.EquipmentItemForm(request.POST, request.FILES, instance=item)
#         if form.is_valid():
#             form.save()
#             messages.add_message(request, messages.SUCCESS,
#                                  "Item saved.")
#             return HttpResponseRedirect(reverse('inventory:item_detail',
#                                                 kwargs={'item_id': item_id}))
#     else:
#         form = forms.EquipmentItemForm(instance=item)
#     return render(request, "form_crispy.html", {
#         'msg': "Edit '%s'" % str(item),
#         "form": form,
#     })
#
#
# @login_required
# def item_rm(request, item_id):
#     obj = get_object_or_404(models.EquipmentItem, pk=int(item_id))
#     return_page = reverse('inventory:type_detail', args=[obj.item_type.pk])
#
#     if not request.user.has_perm('inventory.delete_equipmentitem', obj):
#         raise PermissionDenied
#
#     if request.method == 'POST':
#         if obj.unsafe_to_delete:
#             return HttpResponseBadRequest("There are still items of this type")
#         else:
#             obj.delete()
#             return HttpResponseRedirect(return_page)
#     else:
#         return HttpResponseBadRequest("Bad method")


def update_tag_list(post_data, new_item):
    """
    Adds a new item to the list of asset tags stored in hidden fields on the Snipe Checkin and Checkout forms and
    returns an additional dictionary containing basic information for each verified item.

    :param post_data: The request's POST data
    :param new_item: The next asset or accessory to add to the list
    :returns: Updated form data and basic inventory item information (Dictionary and list of Dictionaries)
    """

    new_data = post_data.copy()
    tags = new_data['saved_tags'].split('\n')
    tags.append(str(new_item['id']) + "~~" + str(new_item['asset_tag']) + "~~" + new_item['name'] + "~~" +
                new_item['rental_cost'])
    if '' in tags:
        tags.remove('')
    new_data['saved_tags'] = '\n'.join(tags)
    new_data.pop('asset_tag')
    saved_tags = retrieve_saved_tags(new_data)
    return new_data, saved_tags


def retrieve_saved_tags(post_data):
    """
    Converts the asset tag data stored in a form into a list of dictionaries.

    :param post_data: The request's POST data
    :return: A list of dictionaries containing the metadata for the selected assets and/or accessories
    """

    tags = post_data['saved_tags'].split('\n')
    if '' in tags:
        tags.remove('')
    saved_tags = [{'id': item.split('~~')[0], 'tag': item.split('~~')[1], 'name': item.split('~~')[2],
                   'cost': float(item.split('~~')[3])} for item in tags]
    return saved_tags


def remove_saved_tag(post_data, tag):
    """
    Removes an item from the list of pending assets and/or accessories stored in a Snipe Checkin or Checkout form.

    :param post_data: The request's POST data
    :param tag: The asset tag value of the item to remove
    :return: The updated form data and list of item metadata dictionaries
    """

    new_data = post_data.copy()
    tags = new_data['saved_tags'].split('\n')
    item = next((item for item in tags if item.split("~~")[1] == tag))
    tags.remove(item)
    new_data['saved_tags'] = '\n'.join(tags)
    new_data.pop('asset_tag')
    saved_tags = retrieve_saved_tags(new_data)
    return new_data, saved_tags


@login_required
@permission_required('inventory.view_equipment', raise_exception=True)
def snipe_checkout(request):
    """ Equipment inventory checkout form. Communicates with the Snipe API. """

    rental_clients = api.load_rental_clients()

    if not rental_clients:
        return HttpResponse("Failed to retrieve rental clients from Snipe", status=501)

    saved_tags = []

    if request.method == 'POST':
        form = forms.SnipeRentalForm(rental_clients, True, request.POST, request.FILES)
        if form.is_valid():
            if request.POST['save'] == 'Add item' and request.POST['asset_tag'] not in ['', None]:
                # Save item to list (if it exists and can be checked out)
                new_tag = form.cleaned_data['asset_tag']
                item = api.get_item_info(new_tag)
                if item['status'] == 'OK':
                    if item['user_can_checkout']:
                        new_data, saved_tags = update_tag_list(request.POST, item)
                        form = forms.SnipeRentalForm(rental_clients, True, new_data, request.FILES)
                    else:
                        messages.add_message(request, messages.ERROR,
                                             "Item is not available for checkout at this time")
                        saved_tags = retrieve_saved_tags(request.POST)
                else:
                    messages.add_message(request, messages.ERROR, item['messages'])
                    saved_tags = retrieve_saved_tags(request.POST)

            # Attempt to check out all the items
            elif request.POST['save'] == 'Check out':
                errors = []
                receipt_data = []
                success_count = {'accessories': 0, 'assets': 0}
                for tag in retrieve_saved_tags(request.POST):
                    is_accessory = re.match('LNLACC([0-9]+)', tag['tag'])
                    if not is_accessory and tag in receipt_data:
                        continue
                    result = api.checkout(tag['id'], form.cleaned_data['renter'], is_accessory)
                    if result['status'] == 'error':
                        errors.append({'item': tag, 'reason': result['messages']})
                        continue

                    # Item was checked out successfully! Update count and add to receipt
                    if is_accessory:
                        success_count['accessories'] += 1
                    else:
                        success_count['assets'] += 1

                    receipt_data.append(tag)

                if success_count['assets'] > 0 or success_count['accessories'] > 0:
                    messages.add_message(request, messages.SUCCESS,
                                         'Successfully checked out {} assets and {} accessories'.format(
                                             success_count['assets'], success_count['accessories']))

                renter = next((item[1] for item in rental_clients if item[0] == form.cleaned_data['renter']))

                receipt_info, total = generate_receipt(request, receipt_data, renter)

                # Load the summary
                return render(request, 'inventory/checkout_summary.html', {
                    'receipt_info': receipt_info,
                    'total': total,
                    'errors': errors,
                    'num_assets': success_count['assets'],
                    'num_accessories': success_count['accessories'],
                    'checkout_to': form.cleaned_data['renter'],
                    'checkout_to_name': renter
                })

            # Remove a pending item from the list
            elif 'Delete' in request.POST['save']:
                tag = str(request.POST['save'].split('~')[1])
                new_data, saved_tags = remove_saved_tag(request.POST, tag)
                form = forms.SnipeRentalForm(rental_clients, True, new_data, request.FILES)

            else:
                saved_tags = retrieve_saved_tags(request.POST)
    else:
        if 'checkout_to' in request.GET:
            form = forms.SnipeRentalForm(rental_clients, True, initial={'renter': request.GET['checkout_to']})
        else:
            form = forms.SnipeRentalForm(rental_clients, True)
    return render(request, "form_rental.html", {
        'msg': 'Inventory checkout',
        'form': form,
        'tags': saved_tags,
        'submit_btn': "Check out"
    })


@login_required
@permission_required('inventory.view_equipment', raise_exception=True)
def snipe_checkin(request):
    """ Equipment inventory checkin form. Communicates with Snipe via their API. """

    rental_clients = api.load_rental_clients()

    if not rental_clients:
        return HttpResponse("Failed to retrieve rental clients from Snipe", status=501)

    saved_tags = []

    if request.method == 'POST':
        form = forms.SnipeRentalForm(rental_clients, False, request.POST, request.FILES)
        if form.is_valid():
            renter = next((client[1] for client in rental_clients if client[0] == form.cleaned_data['renter']))
            if request.POST['save'] == 'Add item' and request.POST['asset_tag'] not in ['', None]:
                # Save item to list (if it exists and can be checked in)
                new_tag = form.cleaned_data['asset_tag']
                item = api.get_item_info(new_tag)
                if item['status'] == 'OK':
                    # Check that the item has been checked out to the user
                    if item['resource_type'] == "accessory":
                        # Item is an accessory
                        active_rentals = api.checkedout(new_tag)
                        if "messages" in active_rentals:
                            messages.add_message(request, messages.ERROR,
                                                 "Failed to determine if the item has been checked out")
                            saved_tags = retrieve_saved_tags(request.POST)
                        else:
                            saved_tags = retrieve_saved_tags(request.POST)
                            rental_ids = [rental['assigned_pivot_id'] if rental['id'] == form.cleaned_data['renter']
                                          else None for rental in active_rentals]
                            rental_ids = list(filter(None, rental_ids))
                            num_ids = len(rental_ids)
                            if num_ids > 0:
                                for tag in saved_tags:
                                    if int(tag['id']) in rental_ids:
                                        rental_ids.remove(int(tag['id']))
                            if rental_ids:
                                item['id'] = rental_ids[0]
                                new_data, saved_tags = update_tag_list(request.POST, item)
                                form = forms.SnipeRentalForm(rental_clients, False, new_data, request.FILES)
                            else:
                                if num_ids > 0:
                                    messages.add_message(request, messages.ERROR,
                                                         "Only {} instances of {} were checked out to {}"
                                                         .format(num_ids, item['name'], renter))
                                else:
                                    messages.add_message(request, messages.ERROR,
                                                         "No instance of %s checked out to %s" % (item['name'], renter))
                                saved_tags = retrieve_saved_tags(request.POST)
                    else:
                        # Item is an asset
                        if ('assigned_to' not in item
                                or item['assigned_to'] is None
                                or 'type' not in item['assigned_to']
                                or item['assigned_to']['type'] != 'user'
                                or 'id' not in item['assigned_to']
                                or item['assigned_to']['id'] != form.cleaned_data['renter']):
                            messages.add_message(request, messages.ERROR, "Asset wasn't checked out to %s" % renter)
                            saved_tags = retrieve_saved_tags(request.POST)
                        else:
                            new_data, saved_tags = update_tag_list(request.POST, item)
                            form = forms.SnipeRentalForm(rental_clients, False, new_data, request.FILES)
                else:
                    messages.add_message(request, messages.ERROR, item['messages'])
                    saved_tags = retrieve_saved_tags(request.POST)

            # Attempt to check in all of the items
            elif request.POST['save'] == "Check in":
                errors = []
                receipt_data = []
                success_count = {'accessories': 0, 'assets': 0}
                for tag in retrieve_saved_tags(request.POST):
                    is_accessory = re.match('LNLACC([0-9]+)', tag['tag'])
                    if not is_accessory and tag in receipt_data:
                        continue
                    result = api.checkin(tag['id'], is_accessory)
                    if result['status'] == 'error':
                        errors.append({'item': tag, 'reason': result['messages']})
                        continue

                    # Item was checked in successfully! Update count and add to receipt
                    if is_accessory:
                        success_count['accessories'] += 1
                    else:
                        success_count['assets'] += 1

                    receipt_data.append(tag)

                if success_count['assets'] > 0 or success_count['accessories'] > 0:
                    messages.add_message(request, messages.SUCCESS,
                                         'Successfully checked in {} assets and {} accessories'.format(
                                             success_count['assets'], success_count['accessories']))

                receipt_info, total = generate_receipt(request, receipt_data, renter, True)

                # Load the summary
                return render(request, 'inventory/checkin_summary.html', {
                    'receipt_info': receipt_info,
                    'num_assets': success_count['assets'],
                    'num_accessories': success_count['accessories'],
                    'total': total,
                    'errors': errors,
                    'checkin_from': form.cleaned_data['renter'],
                    'checkin_from_name': renter,
                })

            # Remove a pending item from the list
            elif 'Delete' in request.POST['save']:
                tag = str(request.POST['save'].split('~')[1])
                new_data, saved_tags = remove_saved_tag(request.POST, tag)
                form = forms.SnipeRentalForm(rental_clients, False, new_data, request.FILES)

            else:
                saved_tags = retrieve_saved_tags(request.POST)
    else:
        if 'checkin_from' in request.GET:
            form = forms.SnipeRentalForm(rental_clients, False, initial={'renter': request.GET['checkin_from']})
        else:
            form = forms.SnipeRentalForm(rental_clients, False)
    return render(request, "form_rental.html", {
        'msg': 'Inventory checkin',
        'form': form,
        'tags': saved_tags,
        'submit_btn': 'Check in'
    })


def generate_receipt(request, data, renter, checkin=False):
    """
    Generate a checkin or checkout receipt

    :param data: List of dictionaries containing the metadata for each of the items that were just checked in or out
    :param renter: The name of the user or organization the items were rented to
    :param checkin: Set to True if generating a receipt for checkin
    :return: Itemized list of item details and the total rental price
    """

    itemized_list = {}
    success_count = {'accessories': 0, 'assets': 0}
    for item in data:
        asset_tag = item['tag']
        is_accessory = re.match('LNLACC([0-9]+)', asset_tag)
        if is_accessory:
            success_count['accessories'] += 1
            if asset_tag in itemized_list:
                itemized_list[asset_tag]['quantity'] += 1
            else:
                itemized_list[asset_tag] = {'name': item['name'], 'rental_price': item['cost'], 'quantity': 1}
        else:
            success_count['assets'] += 1
            if asset_tag not in itemized_list:
                itemized_list[asset_tag] = {'name': item['name'], 'rental_price': item['cost'], 'quantity': 1}

    # Determine total rental cost
    rental_prices = [(None if asset_info['rental_price'] is None else
                      asset_info['rental_price'] * asset_info['quantity']) for asset_info in itemized_list.values()]
    total_rental_price = None if None in rental_prices else sum(rental_prices)

    # Generate Receipt
    if checkin:
        html = render_to_string('pdf_templates/checkin_receipt.html', request=request, context={
            'title': 'Checkin Receipt',
            'receipt_info': itemized_list,
            'num_assets': success_count['assets'],
            'num_accessories': success_count['accessories'],
            'total_rental_price': total_rental_price,
            'checkin_from': renter,
        })
        action = "checkin"
    else:
        html = render_to_string('pdf_templates/checkout_receipt.html', request=request, context={
            'title': 'Checkout Receipt',
            'receipt_info': itemized_list,
            'num_assets': success_count['assets'],
            'num_accessories': success_count['accessories'],
            'total_rental_price': total_rental_price,
            'checkout_to': renter,
        })
        action = "checkout"
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)
    pdf_handle = pdf_file.getvalue()
    filename = 'LNL-{}-receipt-{}.pdf'.format(action, timezone.now().isoformat())
    attachments = [{'file_handle': pdf_handle, 'name': filename}]
    email = DefaultLNLEmailGenerator(subject='LNL Inventory {} Receipt'.format(action.capitalize()),
                                     to_emails=(request.user.email, settings.EMAIL_TARGET_RENTALS),
                                     attachments=attachments,
                                     body='A receipt for the rental {} by {} to {} is attached.'.format(
                                         action, request.user, renter))
    email.send()
    return itemized_list, total_rental_price


@login_required
@permission_required('inventory.view_equipment', raise_exception=True)
def old_snipe_checkout(request):
    """ Equipment inventory checkout form. Communicates with Snipe via their API. """
    if not settings.SNIPE_URL:
        return HttpResponse('This page is unavailable because SNIPE_URL is not set.', status=501)
    if not settings.SNIPE_API_KEY:
        return HttpResponse('This page is unavailable because SNIPE_API_KEY is not set.', status=501)
    # Get the list of users in the rental group from Snipe
    error_message = 'Error communicating with Snipe. Did not check out anything.'
    checkout_to_choices = []
    response = requests.request('GET', '{}api/v1/users'.format(settings.SNIPE_URL), headers={
        'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
        'accept': 'application/json',
        'content-type': 'application/json'
    })
    if response.status_code == 200:
        try:
            data = json.loads(response.text)
            if data.get('status') == 'error':
                return HttpResponse(error_message, status=502)
            checkout_to_choices = [(user['id'], user['name']) for user in data['rows'] if 'rental' in ((group['name'] for group in user['groups']['rows']) if user['groups'] is not None else ())]
        except ValueError:
            return HttpResponse(error_message, status=502)
    else:
        return HttpResponse(error_message, status=502)

    # Handle the form
    error_message = 'Error communicating with Snipe. Some things may have been checked out while some were not. ' \
                    'Please go check Snipe.'
    if request.method == 'POST':
        receipt_info = {}
        form = forms.SnipeCheckoutForm(checkout_to_choices, request.POST, request.FILES)
        if form.is_valid():
            success_count_assets = 0
            success_count_accessories = 0
            for tag in [tag for tag in re.split('[^a-zA-Z0-9]', form.cleaned_data['asset_tags']) if tag]:
                match = re.match('LNLACC([0-9]+)', tag)
                if match:
                    tag = match.group(1)
                    # This tag represents an accessory
                    response = requests.request('GET', '{}api/v1/accessories/{}'.format(settings.SNIPE_URL, tag),
                                                headers={'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                                                         'accept': 'application/json', 'content-type': 'application/json'})
                    if response.status_code == 200:
                        try:
                            data = json.loads(response.text)
                            if data.get('status') == 'error':
                                # No accessory with that ID exists in Snipe
                                messages.add_message(request, messages.ERROR, 'No such accessory with ID {}'.format(tag))
                                continue
                            accessory_name = data['name']
                            rental_price = float(data['order_number']) if data['order_number'] is not None else None
                            # Check out the accessory
                            response = requests.request('POST', '{}api/v1/accessories/{}/checkout'.format(settings.SNIPE_URL, tag), data=json.dumps({
                                'assigned_to': form.cleaned_data['checkout_to'],
                            }), headers={
                                'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                                'accept': 'application/json',
                                'content-type': 'application/json',
                            })
                            if response.status_code == 200:
                                data = json.loads(response.text)
                                if data.get('status') == 'error':
                                    # Snipe refused to check out the accessory (maybe they are all checked out)
                                    messages.add_message(request, messages.ERROR, 'Unable to check out accessory {}. Snipe says: {}'.format(tag, data['messages']))
                                    continue
                                # The accessory was successfully checked out
                                success_count_accessories += 1
                                if tag in receipt_info:
                                    if receipt_info[tag]['name'] != accessory_name \
                                            or receipt_info[tag]['rental_price'] != rental_price:
                                        return HttpResponse(error_message, status=502)
                                    receipt_info[tag]['quantity'] += 1
                                else:
                                    receipt_info[tag] = {'name': accessory_name, 'rental_price': rental_price,
                                                         'quantity': 1}
                            else:
                                return HttpResponse(error_message, status=502)
                        except ValueError:
                            return HttpResponse(error_message, status=502)
                    else:
                        return HttpResponse(error_message, status=502)
                else:
                    # This tag represents an asset
                    response = requests.request('GET', '{}api/v1/hardware/bytag/{}'.format(settings.SNIPE_URL, tag),
                                                headers={'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                                                         'accept': 'application/json', 'content-type': 'application/json'})
                    if response.status_code == 200:
                        try:
                            data = json.loads(response.text)
                            if data.get('status') == 'error':
                                # The asset tag does not exist in Snipe
                                messages.add_message(request, messages.ERROR, 'No such asset tag {}'.format(tag))
                                continue
                            asset_name = data['name']
                            if 'custom_fields' in data and 'Rental Price' in data['custom_fields'] and \
                                    'value' in data['custom_fields']['Rental Price'] and data['custom_fields']['Rental Price']['value'] is not None:
                                rental_price = float(data['custom_fields']['Rental Price']['value'])
                            else:
                                rental_price = None
                            # Check out the asset
                            response = requests.request('POST', '{}api/v1/hardware/{}/checkout'.format(settings.SNIPE_URL, data['id']), data=json.dumps({
                                'checkout_to_type': 'user',
                                'assigned_user': form.cleaned_data['checkout_to'],
                            }), headers={
                                'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                                'accept': 'application/json',
                                'content-type': 'application/json',
                            })
                            if response.status_code == 200:
                                data = json.loads(response.text)
                                if data.get('status') == 'error':
                                    # Snipe refused to check out the asset (maybe it is already checked out)
                                    messages.add_message(request, messages.ERROR, 'Unable to check out asset {} - {}. Snipe says: {}'.format(tag, asset_name, data['messages']))
                                    continue
                                # The asset was successfully checked out
                                success_count_assets += 1
                                if tag in receipt_info:
                                    return HttpResponse(error_message, status=502)
                                receipt_info[tag] = {'name': asset_name, 'rental_price': rental_price, 'quantity': 1}
                            else:
                                return HttpResponse(error_message, status=502)
                        except ValueError:
                            return HttpResponse(error_message, status=502)
                    else:
                        return HttpResponse(error_message, status=502)
            if success_count_assets > 0 or success_count_accessories > 0:
                messages.add_message(request, messages.SUCCESS, 'Successfully checked out {} assets and {} accessories'.format(success_count_assets, success_count_accessories))
            rental_prices = [(None if asset_info['rental_price'] is None else asset_info['rental_price'] * asset_info['quantity']) for asset_info in receipt_info.values()]
            total_rental_price = None if None in rental_prices else sum(rental_prices)
            checkout_to_name = next((item[1] for item in checkout_to_choices if item[0] == form.cleaned_data['checkout_to']))
            # Before returning the response, email a PDF receipt
            html = render_to_string('pdf_templates/checkout_receipt.html', request=request, context={
                'title': 'Checkout Receipt',
                'receipt_info': receipt_info,
                'num_assets': success_count_assets,
                'num_accessories': success_count_accessories,
                'total_rental_price': total_rental_price,
                'checkout_to': checkout_to_name,
            })
            pdf_file = BytesIO()
            pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)
            pdf_handle = pdf_file.getvalue()
            filename = 'LNL-checkout-receipt-{}.pdf'.format(timezone.now().isoformat())
            attachments = [{'file_handle': pdf_handle, 'name': filename}]
            email = DefaultLNLEmailGenerator(subject='LNL Inventory Checkout Receipt', to_emails=(request.user.email, settings.EMAIL_TARGET_RENTALS), attachments=attachments,
                body='A receipt for the rental checkout by {} to {} is attached.'.format(request.user, checkout_to_name))
            email.send()
            # Return the response
            return render(request, 'inventory/checkout_summary.html', {
                'receipt_info': receipt_info,
                'num_assets': success_count_assets,
                'num_accessories': success_count_accessories,
                'total': total_rental_price,
                'checkout_to': form.cleaned_data['checkout_to'],
                'checkout_to_name': checkout_to_name,
            })
        else:
            form = forms.SnipeCheckoutForm(checkout_to_choices, initial={'checkout_to': form.cleaned_data['checkout_to']})
    else:
        if 'checkout_to' in request.GET:
            form = forms.SnipeCheckoutForm(checkout_to_choices, initial={'checkout_to': request.GET['checkout_to']})
        else:
            form = forms.SnipeCheckoutForm(checkout_to_choices)
    return render(request, "form_crispy.html", {
        'msg': 'Inventory checkout',
        'form': form,
    })


@login_required
@permission_required('inventory.view_equipment', raise_exception=True)
def old_snipe_checkin(request):
    """ Equipment inventory checkin form. Communicates with Snipe via their API. """
    if not settings.SNIPE_URL:
        return HttpResponse('This page is unavailable because SNIPE_URL is not set.', status=501)
    if not settings.SNIPE_API_KEY:
        return HttpResponse('This page is unavailable because SNIPE_API_KEY is not set.', status=501)
    # Get the list of users in the rental group from Snipe
    error_message = 'Error communicating with Snipe. Did not check in anything.'
    checkin_from_choices = []
    response = requests.request('GET', '{}api/v1/users'.format(settings.SNIPE_URL), headers={
        'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
        'accept': 'application/json',
        'content-type': 'application/json'
    })
    if response.status_code == 200:
        try:
            data = json.loads(response.text)
            if data.get('status') == 'error':
                return HttpResponse(error_message, status=502)
            checkin_from_choices = [(user['id'], user['name']) for user in data['rows'] if 'rental' in ((group['name'] for group in user['groups']['rows']) if user['groups'] is not None else ())]
            checkin_from_usernames = {user['id']: user['username'] for user in data['rows'] if 'rental' in ((group['name'] for group in user['groups']['rows']) if user['groups'] is not None else ())}
        except ValueError:
            return HttpResponse(error_message, status=502)
    else:
        return HttpResponse(error_message, status=502)

    # Handle the form
    error_message = 'Error communicating with Snipe. Some things may have been checked in while some were not. Please go check Snipe.'
    if request.method == 'POST':
        form = forms.SnipeCheckinForm(checkin_from_choices, request.POST, request.FILES)
        if form.is_valid():
            receipt_info = {}
            receipt_info_extra = {}
            checkin_from_name = next((item[1] for item in checkin_from_choices if item[0] == form.cleaned_data['checkin_from']))
            checkin_from_username = checkin_from_usernames[form.cleaned_data['checkin_from']]
            success_count_assets = 0
            success_count_accessories = 0
            extra_count_assets = 0
            extra_count_accessories = 0
            for tag in [tag for tag in re.split('[^a-zA-Z0-9]', form.cleaned_data['asset_tags']) if tag]:
                match = re.match('LNLACC([0-9]+)', tag)
                if match:
                    tag = match.group(1)
                    # This tag represents an accessory
                    response = requests.request('GET', '{}api/v1/accessories/{}'.format(settings.SNIPE_URL, tag), headers={
                        'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                        'accept': 'application/json', 'content-type': 'application/json'
                    })
                    if response.status_code == 200:
                        try:
                            data = json.loads(response.text)
                            if data.get('status') == 'error':
                                # No accessory with that ID exists in Snipe
                                messages.add_message(request, messages.ERROR, 'No such accessory with ID {}'.format(tag))
                                continue
                            accessory_name = data['name']
                            rental_price = float(data['order_number']) if data['order_number'] is not None else None
                            # Get the list of checked out instances of the accessory
                            response = requests.request('GET', '{}api/v1/accessories/{}/checkedout'.format(settings.SNIPE_URL, tag), headers={
                                'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                                'accept': 'application/json', 'content-type': 'application/json'
                            })
                            if response.status_code == 200:
                                data = json.loads(response.text)
                                if data.get('status') == 'error':
                                    return HttpResponse(error_message, status=502)
                                accessory_instances = [a for a in data['rows'] if a['username'] == checkin_from_username]
                                if len(accessory_instances) == 0:
                                    # There are no instances of that accessory checked out to the specified Snipe user
                                    messages.add_message(request, messages.ERROR, 'No instance of {} checked out to {}'.format(accessory_name, checkin_from_name))
                                    extra_count_accessories += 1
                                    if tag in receipt_info_extra:
                                        if receipt_info_extra[tag]['name'] != accessory_name \
                                                or receipt_info_extra[tag]['rental_price'] != rental_price:
                                            return HttpResponse(error_message, status=502)
                                        receipt_info_extra[tag]['quantity'] += 1
                                    else:
                                        receipt_info_extra[tag] = {'name': accessory_name, 'rental_price': rental_price, 'quantity': 1}
                                    continue
                                # Check in the accessory
                                response = requests.request('POST', '{}api/v1/accessories/{}/checkin'.format(settings.SNIPE_URL, accessory_instances[0]['assigned_pivot_id']), headers={
                                    'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                                    'accept': 'application/json',
                                    'content-type': 'application/json',
                                })
                                if response.status_code == 200:
                                    data = json.loads(response.text)
                                    if data.get('status') == 'error':
                                        # Snipe refused to check in the accessory
                                        messages.add_message(request, messages.ERROR, 'Unable to check in accessory {}. Snipe says: {}'.format(tag, data['messages']))
                                        continue
                                    # The accessory was successfully checked in
                                    success_count_accessories += 1
                                    if tag in receipt_info:
                                        if receipt_info[tag]['name'] != accessory_name \
                                                or receipt_info[tag]['rental_price'] != rental_price:
                                            return HttpResponse(error_message, status=502)
                                        receipt_info[tag]['quantity'] += 1
                                    else:
                                        receipt_info[tag] = {'name': accessory_name, 'rental_price': rental_price, 'quantity': 1}
                                else:
                                    return HttpResponse(error_message, status=502)
                            else:
                                return HttpResponse(error_message, status=502)
                        except ValueError:
                            return HttpResponse(error_message, status=502)
                    else:
                        return HttpResponse(error_message, status=502)
                else:
                    # This tag represents an asset
                    response = requests.request('GET', '{}api/v1/hardware/bytag/{}'.format(settings.SNIPE_URL, tag), headers={
                        'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                        'accept': 'application/json', 'content-type': 'application/json'
                    })
                    if response.status_code == 200:
                        try:
                            data = json.loads(response.text)
                            if data.get('status') == 'error':
                                # The asset tag does not exist in Snipe
                                messages.add_message(request, messages.ERROR, 'No such asset tag {}'.format(tag))
                                continue
                            asset_name = data['name']
                            if 'custom_fields' in data and 'Rental Price' in data['custom_fields'] and \
                                    'value' in data['custom_fields']['Rental Price'] and data['custom_fields']['Rental Price']['value'] is not None:
                                rental_price = float(data['custom_fields']['Rental Price']['value'])
                            else:
                                rental_price = None
                            if ('assigned_to' not in data
                                    or data['assigned_to'] is None
                                    or 'type' not in data['assigned_to']
                                    or data['assigned_to']['type'] != 'user'
                                    or 'id' not in data['assigned_to']
                                    or data['assigned_to']['id'] != form.cleaned_data['checkin_from']):
                                # That asset is not checked out to the specified Snipe user
                                messages.add_message(request, messages.ERROR, 'Asset {} was never checked out to {}'.format(asset_name, checkin_from_name))
                                extra_count_assets += 1
                                if tag in receipt_info:
                                    return HttpResponse(error_message, status=502)
                                receipt_info_extra[tag] = {'name': asset_name, 'rental_price': rental_price, 'quantity': 1}
                                continue
                            # Check in the asset
                            response = requests.request('POST', '{}api/v1/hardware/{}/checkin'.format(settings.SNIPE_URL, data['id']), headers={
                                'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                                'accept': 'application/json',
                                'content-type': 'application/json',
                            })
                            if response.status_code == 200:
                                data = json.loads(response.text)
                                if data.get('status') == 'error':
                                    # Snipe refused to check in the asset
                                    messages.add_message(request, messages.ERROR, 'Unable to check in asset {} - {}. Snipe says: {}'.format(tag, asset_name, data['messages']))
                                    continue
                                # The asset was successfully checked in
                                success_count_assets += 1
                                if tag in receipt_info:
                                    return HttpResponse(error_message, status=502)
                                receipt_info[tag] = {'name': asset_name, 'rental_price': rental_price, 'quantity': 1}
                            else:
                                return HttpResponse(error_message, status=502)
                        except ValueError:
                            return HttpResponse(error_message, status=502)
                    else:
                        return HttpResponse(error_message, status=502)
            if success_count_assets > 0 or success_count_accessories > 0:
                messages.add_message(request, messages.SUCCESS, 'Successfully checked in {} assets and {} accessories'.format(success_count_assets, success_count_accessories))
            rental_prices = [(None if asset_info['rental_price'] is None else asset_info['rental_price'] * asset_info['quantity']) for asset_info in receipt_info.values()]
            extra_prices = [(None if asset_info['rental_price'] is None else asset_info['rental_price'] * asset_info['quantity']) for asset_info in receipt_info_extra.values()]
            total_rental_price = None if None in rental_prices or None in extra_prices else sum(rental_prices) + sum(extra_prices)
            # Before returning the response, email a PDF receipt
            html = render_to_string('pdf_templates/checkin_receipt.html', request=request, context={
                'title': 'Checkin Receipt',
                'receipt_info': receipt_info,
                'receipt_info_extra': receipt_info_extra,
                'num_assets': success_count_assets,
                'num_accessories': success_count_accessories,
                'num_extra_assets': extra_count_assets,
                'num_extra_accessories': extra_count_accessories,
                'total_rental_price': total_rental_price,
                'checkin_from': checkin_from_name,
            })
            pdf_file = BytesIO()
            pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)
            pdf_handle = pdf_file.getvalue()
            filename = 'LNL-checkin-receipt-{}.pdf'.format(timezone.now().isoformat())
            attachments = [{'file_handle': pdf_handle, 'name': filename}]
            email = DefaultLNLEmailGenerator(subject='LNL Inventory Checkin Receipt', to_emails=(request.user.email, settings.EMAIL_TARGET_RENTALS), attachments=attachments,
                body='A receipt for the rental checkin by {} from {} is attached.'.format(request.user, checkin_from_name))
            email.send()
            # Return the response
            return render(request, 'inventory/checkin_summary.html', {
                'receipt_info': receipt_info,
                'receipt_info_extra': receipt_info_extra,
                'num_assets': success_count_assets,
                'num_accessories': success_count_accessories,
                'num_extra_assets': extra_count_assets,
                'num_extra_accessories': extra_count_accessories,
                'total': total_rental_price,
                'checkin_from': form.cleaned_data['checkin_from'],
                'checkin_from_name': checkin_from_name,
            })
        else:
            form = forms.SnipeCheckinForm(checkin_from_choices, initial={'checkin_from': form.cleaned_data['checkin_from']})
    else:
        if 'checkin_from' in request.GET:
            form = forms.SnipeCheckinForm(checkin_from_choices, initial={'checkin_from': request.GET['checkin_from']})
        else:
            form = forms.SnipeCheckinForm(checkin_from_choices)
    return render(request, "form_crispy.html", {
        'msg': 'Inventory checkin',
        'form': form,
    })


@login_required
@permission_required('inventory.view_equipment', raise_exception=True)
def snipe_credentials(request):
    context = {
        'title': 'Snipe Login Credentials',
        'message': '<span style="font-size: 1.3em"><strong>Username:</strong> ' + settings.SNIPE_GENERAL_USER +
                   '<br><strong>Password:</strong> ' + settings.SNIPE_GENERAL_PASS + '</span><br><br>'
                   '<a class="btn btn-primary" href="https://lnl-rt.wpi.edu/snipe" target="_blank">Login Now</a>'
    }
    return render(request, 'default.html', context)


@login_required
def log_access(request, location=None, reason=None):
    """
    Checkin form used by LNL members when accessing a storage location (contact tracing)

    :param location: The name of the location (must match a location that contains equipment)
    :param reason: Should be set to "OUT" if user is checking out of a location (None otherwise)
    """
    context = {'NO_FOOT': True, 'NO_NAV': True, 'NO_API': True, 'LIGHT_THEME': True}

    location = location.replace('-', ' ')
    space = Location.objects.filter(holds_equipment=True, name__icontains=location).first()
    if not space:
        return HttpResponseNotFound("Invalid Location ID")

    if request.method == 'POST':
        form = forms.AccessForm(request.POST, location=space.name, reason=reason, initial={'users': [request.user]})
        if form.is_valid():
            record = form.save(commit=False)
            record.location = space
            record.save()
            form.save_m2m()
            if reason == "OUT":
                messages.success(request, "Thank you! Come again soon!", extra_tags="success")
            else:
                messages.success(request, "Thank you! You are now signed in.", extra_tags="success")
            return HttpResponseRedirect(reverse("home"))
    else:
        form = forms.AccessForm(location=space.name, reason=reason, initial={'users': [request.user]})
    context['form'] = form
    return render(request, 'form_crispy_static.html', context)


@login_required
@permission_required('inventory.view_access_logs', raise_exception=True)
def view_logs(request):
    """ View contact tracing logs for LNL storage spaces """
    headers = ['Timestamp', 'User', 'Location', 'Reason']

    def get_timestamp(data):
        return data.get('timestamp')

    records = []
    for record in models.AccessRecord.objects.all():
        for user in record.users.all():
            obj = {'timestamp': record.timestamp, 'user': user, 'location': record.location, 'reason': record.reason}
            records.append(obj)
    records.sort(key=get_timestamp, reverse=True)

    paginator = Paginator(records, 50)
    page_number = request.GET.get('page', 1)
    current_page = paginator.get_page(page_number)
    context = {'records': current_page, 'title': 'Access Log', 'headers': headers}
    return render(request, 'access_log.html', context)

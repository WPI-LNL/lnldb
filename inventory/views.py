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

from . import forms, models
from emails.generators import DefaultLNLEmailGenerator
from pdfs.views import link_callback

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
        form = forms.EquipmentClassForm(request.POST, request.FILES, instance=e_type)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Equipment type saved.")
            return HttpResponseRedirect(reverse('inventory:type_detail',
                                                kwargs={'type_id': type_id}))
    else:
        form = forms.EquipmentClassForm(instance=e_type)
    return render(request, "form_crispy.html", {
        'msg': "Edit '%s'" % e_type.name,
        "form": form,
    })


@login_required
def type_mk(request):
    if not request.user.has_perm('inventory.add_equipmentclass'):
        raise PermissionDenied

    category = request.GET.get('default_cat')

    if request.method == 'POST':
        form = forms.EquipmentClassForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Equipment type added.")
            return HttpResponseRedirect(reverse('inventory:type_detail',
                                                kwargs={'type_id': obj.pk}))
    else:
        form = forms.EquipmentClassForm(initial={'category': category})
    return render(request, "form_crispy.html", {
        'msg': "Create Equipment Type",
        "form": form,
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
        form = forms.CategoryForm(request.POST, request.FILES, instance=category)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Category saved.")
            return HttpResponseRedirect(reverse('inventory:cat',
                                                kwargs={'category_id': category_id}))
    else:
        form = forms.CategoryForm(instance=category)
    return render(request, "form_crispy.html", {
        'msg': "Edit Category",
        "form": form,
    })


@login_required
def cat_mk(request):
    if not request.user.has_perm('inventory.add_equipmentcategory'):
        raise PermissionDenied

    parent = request.GET.get('parent')

    if request.method == 'POST':
        form = forms.CategoryForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Category added.")
            return HttpResponseRedirect(reverse('inventory:cat',
                                                kwargs={'category_id': obj.pk}))
    else:
        form = forms.CategoryForm(initial={'parent': parent})
    return render(request, "form_crispy.html", {
        'msg': "Create Category",
        "form": form,
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
        form = forms.FastAdd(request.user, request.POST, request.FILES)
        if form.is_valid():
            obj = form.save()
            messages.add_message(request, messages.SUCCESS,
                                 "%d items added and saved. Now editing." % form.cleaned_data['num_to_add'])
            return HttpResponseRedirect(reverse('inventory:bulk_edit',
                                                kwargs={'type_id': obj.pk}))
    else:
        form = forms.FastAdd(request.user, initial={'item_cat': category})
    return render(request, "form_crispy.html", {
        'msg': "Fast Add Item(s)",
        "form": form,
    })


# def add(request):
#     context = {}
#
#     if request.method == 'POST':
#         form = InvForm(request.POST)
#         if form.is_valid():
#             form.save()
#             # return HttpResponseRedirect(reverse("home",
#  kwargs={'msg':slugify(SUCCESS_MSG_INV)}))
#             return HttpResponseRedirect(reverse('inventory:view'))
#
#         else:
#             context['form'] = form
#     else:
#         msg = "New Inventory"
#         form = InvForm()
#
#         context['form'] = form
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
        form = forms.EquipmentItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS,
                                 "Item saved.")
            return HttpResponseRedirect(reverse('inventory:item_detail',
                                                kwargs={'item_id': item_id}))
    else:
        form = forms.EquipmentItemForm(instance=item)
    return render(request, "form_crispy.html", {
        'msg': "Edit '%s'" % str(item),
        "form": form,
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
#         form = EntryForm(request.user, inv, request.POST)
#         if form.is_valid():
#             form.save()
#             return HttpResponseRedirect(reverse('inv-detail', args=(id,)))
#
#         else:
#             context['form'] = form
#     else:
#
#         form = EntryForm(request.user, inv)
#
#         context['form'] = form
#
#     return render(request, 'form_crispy.html', context)

# @login_required
# def user_guides(request):
# 	if not request.user.has_perm('inventory.view_equipment'):
# 		raise PermissionDenied
# 	
# 	context = {}
# 	tmpls = models.EquipmentUserGuide.objects.filter(tmpl=True).order_by('name')
# 	guides = models.EquipmentUserGuide.objects.filter(tmpl=False).filter(datasheet=False).order_by('name')
# 	datasheets = models.EquipmentUserGuide.objects.filter(datasheet=True).order_by('name')
# 
# 	context['tmpls'] = tmpls
# 	context['guides'] = guides
# 	context['datasheets'] = datasheets
# 	return render(request, 'user-docs.html', context)

@login_required
@permission_required('inventory.view_equipment', raise_exception=True)
def snipe_checkout(request):
    if not settings.SNIPE_URL:
        return HttpResponse('This page is unavailable because SNIPE_URL is not set.', status=501)
    if not settings.SNIPE_API_KEY:
        return HttpResponse('This page is unavailable because SNIPE_API_KEY is not set.', status=501)
    # Get the list of users in the rental group from Snipe
    error_message = 'Error communicating with Snipe. Did not check out anything.'
    checkout_to_choices = []
    response = requests.request('GET', '{}api/v1/users'.format(settings.SNIPE_URL), headers={
        'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
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
    error_message = 'Error communicating with Snipe. Some things may have been checked out while some were not. Please go check Snipe.'
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
                    response = requests.request('GET', '{}api/v1/accessories/{}'.format(settings.SNIPE_URL, tag), headers={
                        'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                        'accept': 'application/json',
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
                                    receipt_info[tag] = {'name': accessory_name, 'rental_price': rental_price, 'quantity': 1}
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
                        'accept': 'application/json',
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
            html = render_to_string('pdf_templates/inventory-receipt.html', request=request, context={
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
            email = DefaultLNLEmailGenerator(subject='LNL Inventory Checkout Receipt', to_emails=(request.user.email, settings.DEFAULT_TO_ADDR), attachments=attachments,
                body='A receipt for the rental checkout by {} to {} is attached.'.format(request.user, checkout_to_name))
            email.send()
            # Return the response
            return render(request, 'inventory/checkout_receipt.html', {
                'receipt_info': receipt_info,
                'num_assets': success_count_assets,
                'num_accessories': success_count_accessories,
                'total_rental_price': total_rental_price,
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
def snipe_checkin(request):
    if not settings.SNIPE_URL:
        return HttpResponse('This page is unavailable because SNIPE_URL is not set.', status=501)
    if not settings.SNIPE_API_KEY:
        return HttpResponse('This page is unavailable because SNIPE_API_KEY is not set.', status=501)
    error_message = 'Error communicating with Snipe. Some assets may have been checked in while some were not. Please go check Snipe.'
    if request.method == 'POST':
        form = forms.SnipeCheckinForm(request.POST, request.FILES)
        if form.is_valid():
            success_count = 0
            for tag in [tag for tag in re.split('[^a-zA-Z0-9]', form.cleaned_data['asset_tags']) if tag]:
                response = requests.request('GET', '{}api/v1/hardware/bytag/{}'.format(settings.SNIPE_URL, tag), headers={
                    'authorization': 'Bearer {}'.format(settings.SNIPE_API_KEY),
                })
                if response.status_code == 200:
                    try:
                        data = json.loads(response.text)
                        if data.get('status') == 'error':
                            # The asset tag does not exist in Snipe
                            messages.add_message(request, messages.ERROR, 'No such asset tag {}'.format(tag))
                            continue
                        asset_name = data['name']
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
                            success_count += 1
                        else:
                            return HttpResponse(error_message, status=502)
                    except ValueError:
                        return HttpResponse(error_message, status=502)
                else:
                    return HttpResponse(error_message, status=502)
            if success_count > 0:
                messages.add_message(request, messages.SUCCESS, 'Successfully checked in {} assets'.format(success_count))
    form = forms.SnipeCheckinForm()
    return render(request, "form_crispy.html", {
        'msg': 'Inventory checkin',
        'form': form,
    })

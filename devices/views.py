# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from hashlib import sha256
from itertools import chain
import json

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, render, reverse
from django.template import loader
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Laptop, LaptopPasswordRetrieval, LaptopPasswordRotation
from .forms import EnrollmentForm, RemovalForm, ClientForm


@login_required
@require_GET
@permission_required('devices.view_laptop_details', raise_exception=True)
def laptops_list(request):
    laptops = Laptop.objects.filter(retired=False)
    return render(request, 'laptops/laptops_list.html', {"laptops": laptops})


@login_required
@require_GET
@permission_required('devices.view_laptop_history', raise_exception=True)
def laptop_history(request, id):
    laptop = get_object_or_404(Laptop, retired=False, pk=id)
    password_retrievals = laptop.password_retrievals.all()
    password_rotations = laptop.password_rotations.all()
    events = sorted(
        chain(
            (('retrieval', r) for r in password_retrievals),
            (('rotation', r) for r in password_rotations)
        ), key=lambda event: event[1].timestamp, reverse=True)
    return render(request, 'laptops/laptop_history.html', {'laptop': laptop, 'events': events})


@login_required
@require_GET
def laptop_user_password(request, id):
    laptop = get_object_or_404(Laptop, retired=False, pk=id)
    if not request.user.has_perm('devices.retrieve_user_password', laptop):
        raise PermissionDenied
    LaptopPasswordRetrieval.objects.create(laptop=laptop, user=request.user, admin=False)
    context = {
        'title': 'Password for {}'.format(laptop.name),
        'password': laptop.user_password,
        'now': timezone.now()
    }
    return render(request, 'laptops/password.html', context)


@login_required
@require_GET
def laptop_admin_password(request, id):
    laptop = get_object_or_404(Laptop, retired=False, pk=id)
    if not request.user.has_perm('devices.retrieve_admin_password', laptop):
        raise PermissionDenied
    LaptopPasswordRetrieval.objects.create(laptop=laptop, user=request.user, admin=True)
    context = {
        'title': 'Admin Password for {}'.format(laptop.name),
        'password': laptop.admin_password,
        'now': timezone.now()
    }
    return render(request, 'laptops/password.html', context)


@require_POST
@csrf_exempt
def rotate_passwords(request):
    data = json.loads(request.body)
    laptop = get_object_or_404(Laptop, retired=False, api_key_hash=sha256(data['apiKey']).hexdigest())
    response_data = {"oldUserPassword": laptop.user_password, "oldAdminPassword": laptop.admin_password}
    laptop.user_password = data['userPassword']
    laptop.admin_password = data['adminPassword']
    laptop.save()
    LaptopPasswordRotation.objects.create(laptop=laptop)
    return JsonResponse(response_data)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def mdm_list(request):
    laptops = Laptop.objects.filter(retired=False)
    return render(request, 'mdm/mdm_list.html', {'laptops': laptops})


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def install_client(request):
    context = {}
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            # TODO: Download client
            return render(request, 'default.html', context)
        else:
            context['form'] = form
    else:
        context['form'] = ClientForm()
    return render(request, 'form_crispy.html', context)


@require_POST
@csrf_exempt
def mdm_enroll(request):
    data = json.loads(request.body)
    if data['token'] == settings.MDM_TOKEN:
        try:
            laptop = Laptop.objects.all().get(api_key_hash=sha256(data['APIKey']).hexdigest())
        except Laptop.DoesNotExist:
            laptop = Laptop.objects.all().create(api_key_hash=sha256(data['APIKey']).hexdigest(), name=data['hostname'],
                                                 user_password="None", admin_password="None")
        laptop.serial = data['serial']
        laptop.last_ip = data['networkIP']
        laptop.save()
        response = {'next': reverse("mdm:enroll", args=[laptop.pk])}
    else:
        response = {'next': reverse("mdm:enroll", args=[0])}
    return JsonResponse(response)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def complete_enrollment(request, pk):
    context = {}
    if str(pk) == '0':
        raise PermissionDenied
    try:
        laptop = Laptop.objects.all().get(pk=pk, serial__isnull=False, mdm_enrolled=False)
    except Laptop.DoesNotExist:
        response = render(request, '404.html', {'status': 'Error',
                                                'error_message': 'Unable to enroll device. May already be enrolled.'})
        response.status_code = 404
        return response
    if request.method == 'POST':
        form = EnrollmentForm(request.POST)
        if form.is_valid() and request.POST['asset_tag'] not in [None, '']:
            laptop.name = request.POST['name']
            laptop.asset_tag = request.POST['asset_tag']
            laptop.user_password = request.POST['user_password']
            laptop.admin_password = request.POST['admin_password']
            laptop.mdm_enrolled = True
            laptop.save()
            template = loader.get_template('default.html')
            return HttpResponse(template.render({'title': "Success!",
                                                 'message': "This device is now enrolled in the LNL MDM.",
                                                 'NO_FOOT': True, 'EXIT_BTN': True}, request))
        else:
            context['form'] = EnrollmentForm(request.POST)
    else:
        context['form'] = EnrollmentForm(instance=laptop)
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def remove_device(request, pk):
    device = get_object_or_404(Laptop, pk=pk)
    context = {}
    if request.method == 'POST':
        form = RemovalForm(request.POST)
        if form.is_valid():
            device.mdm_enrolled = False
            device.serial = None
            device.asset_tag = None
            device.last_ip = None
            device.last_checkin = None
            device.save()
            template = loader.get_template('default.html')
            return HttpResponse(template.render({'title': 'Device Removed',
                                                 'message': 'This device is no longer associated with the MDM.',
                                                 'EXIT_BTN': True, 'NO_FOOT': True}, request))
        else:
            context['form'] = RemovalForm(request.POST)
    else:
        if device.serial == 'DISCONNECTED':
            context['form'] = RemovalForm(uninstalled=True)
        else:
            context['form'] = RemovalForm()
    return render(request, 'form_crispy.html', context)

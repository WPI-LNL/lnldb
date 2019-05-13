from hashlib import sha256
from itertools import chain
import json

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Laptop, LaptopPasswordRetrieval, LaptopPasswordRotation

@login_required
@require_GET
@permission_required('laptops.view_laptop', raise_exception=True)
def laptops_list(request):
    laptops = Laptop.objects.filter(retired=False)
    return render(request, 'laptops/laptops_list.html', {"laptops": laptops})

@login_required
@require_GET
@permission_required('laptops.view_laptop_history', raise_exception=True)
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
    if not request.user.has_perm('laptops.retrieve_user_password', laptop):
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
    if not request.user.has_perm('laptops.retrieve_admin_password', laptop):
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

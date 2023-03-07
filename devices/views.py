# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from hashlib import sha256
from itertools import chain
import json, os, datetime, uuid, pytz, plistlib

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.contrib import messages
from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse, HttpResponse, FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, reverse
from django.template import loader
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from .models import Laptop, LaptopPasswordRetrieval, LaptopPasswordRotation, ConfigurationProfile, InstallationRecord, \
    MacOSApp
from .forms import ProfileForm, EnrollmentForm, RemovalForm, ClientForm, AssignmentForm, ProfileRemovalForm, \
    NewAppForm, UpdateAppForm, UninstallAppForm, AppMergeForm
from emails.generators import GenericEmailGenerator


@login_required
@require_GET
@permission_required('devices.view_laptop', raise_exception=True)
def laptops_list(request):
    """View a list of LNL's laptops"""
    laptops = Laptop.objects.filter(retired=False)
    return render(request, 'laptops/laptops_list.html', {"laptops": laptops})


@login_required
@require_GET
@permission_required('devices.view_laptop_history', raise_exception=True)
def laptop_history(request, id):
    """
    View a history of password retrievals and rotations for a given laptop

    :param id: Primary key of laptop
    """
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
    """
    Retrieve the LNL user password for one of the laptops

    :param id: Primary key of laptop
    """
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
    """
    Retrieve the admin password for one of the laptops

    :param id: Primary key of laptop
    """
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
    """
    Endpoint for updating the MacBook passwords once they've been rotated.

    :returns: The old passwords so the MacBooks can complete the rotation
    """
    data = json.loads(request.body)
    laptop = get_object_or_404(Laptop, retired=False, api_key_hash=sha256(data['apiKey'].encode('utf-8')).hexdigest())
    response_data = {"oldUserPassword": laptop.user_password, "oldAdminPassword": laptop.admin_password}
    laptop.user_password = data['userPassword']
    laptop.admin_password = data['adminPassword']
    laptop.save()
    LaptopPasswordRotation.objects.create(laptop=laptop)
    return JsonResponse(response_data)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def mdm_list(request):
    """MDM Console Homepage"""
    laptops = Laptop.objects.filter(retired=False)
    return render(request, 'mdm/mdm_list.html', {'laptops': laptops})


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def install_client(request):
    """Displays an agreement that the user must agree to before they can download the MDM Client installer"""
    context = {}
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            installer = os.path.join(settings.MEDIA_ROOT, "software", "mdm", "client_installer.dmg")
            if os.path.exists(installer):
                with open(installer, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='application/octet-stream')
                    response['Content-Disposition'] = 'attachment; filename=LNL MDM.dmg'
                    return response
            messages.add_message(request, messages.WARNING, "Hmm, we couldn't seem to find the installer. Please try "
                                                            "again later.")
            context['form'] = form
        else:
            context['form'] = form
    else:
        context['form'] = ClientForm()
    context['msg'] = "New Managed Device"
    return render(request, 'form_crispy.html', context)


@require_POST
@csrf_exempt
def mdm_enroll(request):
    """
    Endpoint for starting the enrollment process. Must be contacted directly by the device being enrolled.

    :returns: Relative path to the link to complete the enrollment process (if client token is valid)
    """
    data = json.loads(request.body)
    if data['token'] == settings.MDM_TOKEN:
        try:
            laptop = Laptop.objects.all().get(api_key_hash=sha256(data['APIKey'].encode('utf-8')).hexdigest())
        except Laptop.DoesNotExist:
            laptop = Laptop.objects.all().create(api_key_hash=sha256(data['APIKey'].encode('utf-8')).hexdigest(),
                                                 name=data['hostname'], user_password="None", admin_password="None")
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
    """
    Launched once the installation process is completed on a new device. Prompts the user for additional administrative
    details such as the asset tag number to complete the enrollment process.

    :param pk: Primary key of device
    """
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


@require_POST
@csrf_exempt
def mdm_checkin(request):
    """
    Endpoint for device check-in. Managed devices will check in each time a new user logs onto the device.

    :returns: JSON - If resources are pending install, includes the identifiers needed for the client to fetch and \
    install them. Returns {'status': 200} otherwise.
    """
    data = json.loads(request.body)
    laptop = get_object_or_404(Laptop, api_key_hash=sha256(data['APIKey'].encode('utf-8')).hexdigest(),
                               mdm_enrolled=True)
    system_profiles = []
    user_profiles = []
    system_profiles_remove = []
    user_profiles_remove = []
    password = None

    for record in InstallationRecord.objects.filter(device=laptop, profile__isnull=False, version="RM", active=True):
        profile = record.profile
        if profile.scope == 'System':
            system_profiles_remove.append(profile.pk)
        else:
            user_profiles_remove.append(profile.pk)
            password = settings.MDM_PASS

    for profile in laptop.pending.all():
        if profile.pk not in system_profiles_remove and profile.pk not in user_profiles_remove:
            if profile.scope == 'System':
                system_profiles.append(profile.pk)
            else:
                user_profiles.append(profile.pk)

    if len(system_profiles) > 0 or len(user_profiles) > 0 or len(system_profiles_remove) > 0 or \
            len(user_profiles_remove) > 0:
        response_data = {"status": 100, "system_profiles": system_profiles, "user_profiles": user_profiles,
                         "system_profiles_remove": system_profiles_remove, "user_profiles_remove": user_profiles_remove,
                         "removal_password": password, "password": laptop.admin_password}
    else:
        response_data = {"status": 200}
    laptop.last_checkin = timezone.now()
    laptop.last_ip = data['networkIP']
    laptop.save()
    return JsonResponse(response_data)


@require_POST
@csrf_exempt
def install_confirmation(request):
    """
    Endpoint for accepting receipt of install. Managed devices should contact this endpoint anytime new resources are
    installed.

    :returns: JSON - {'status': 200}
    """
    data = json.loads(request.body)
    device = get_object_or_404(Laptop, api_key_hash=sha256(data['APIKey'].encode('utf-8')).hexdigest(),
                               mdm_enrolled=True)
    profiles_installed = data['installed']
    profiles_removed = data['removed']
    apps = data['apps'].split('#')
    for pk in profiles_installed:
        profile = get_object_or_404(ConfigurationProfile, pk=pk)
        timestamp = datetime.datetime.strptime(data['timestamp'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=pytz.UTC)
        metadata = get_profile_metadata(profile, timestamp)
        expiration_date = metadata['expires']
        version = metadata['version']
        device.pending.remove(profile)
        device.installed.add(profile)
        try:
            record = InstallationRecord.objects.get(profile=profile, device=device, active=True)
            record.version = version
            record.expires = expiration_date
            record.installed_on = timezone.now()
        except InstallationRecord.DoesNotExist:
            record = InstallationRecord.objects.create(profile=profile, device=device, version=version,
                                                       expires=expiration_date, active=True)
        record.save()
    for pk in profiles_removed:
        profile = get_object_or_404(ConfigurationProfile, pk=pk)
        device.pending.remove(profile)
        record = InstallationRecord.objects.get(profile=profile, device=device, active=True)
        record.active = False
        record.expires = timezone.now()
        record.save()

    installed = []
    for item in apps:
        if item in [None, '']:
            continue
        identifier = item.split('=')[0]
        version = item.split('=')[1]
        app = MacOSApp.objects.filter(name__iexact=identifier).first()
        if app:
            if app.merged_into is not None:
                app = app.merged_into
            if version not in [None, ''] and app.version is None:
                app.version = version
                app.save()
            if app in MacOSApp.objects.filter(pending_install=device):
                app.pending_install.remove(device)
            if app not in MacOSApp.objects.filter(installed=device):
                app.installed.add(device)
                if version is None:
                    version = app.version
                InstallationRecord.objects.create(app=app, device=device, version=version)
            elif InstallationRecord.objects.get(app=app, device=device, active=True).version != version:
                record = InstallationRecord.objects.get(app=app, device=device, active=True)
                record.active = False
                record.expires = timezone.now()
                record.save()
                InstallationRecord.objects.create(app=app, device=device, version=version)
        else:
            if version not in [None, '']:
                app = MacOSApp.objects.create(name=identifier, version=version)
            else:
                app = MacOSApp.objects.create(name=identifier)
            app.installed.add(device)
            InstallationRecord.objects.create(app=app, device=device, version=app.version)
        installed.append(app)

    for app in MacOSApp.objects.filter(installed=device):
        if app not in installed:
            app.installed.remove(device)
            record = InstallationRecord.objects.get(app=app, device=device, active=True)
            record.active = False
            record.expires = timezone.now()
            record.save()
    return JsonResponse({'status': 200})


def get_profile_metadata(config, timestamp):
    """
    Retrieve additional metadata from profile data

    :param config: Configuration Profile object
    :param timestamp: Timestamp at time of install
    :returns: Dictionary with profile metadata - {'expires': <datetime>, 'version': <string>}
    """
    with open(config.profile) as profile:
        context = json.load(profile)
        data = {}
        expires_on = None
        expires_after = None
        version = str(context['data']['version'])

        if context['data']['removal_date'] is not None:
            expires_on = timezone.make_aware(datetime.datetime.strptime(
                context['data']['removal_date'], '%Y-%m-%dT%H:%M:%SZ')
            ).astimezone(pytz.UTC)
        if context['data']['removal_period'] is not None:
            expires_after = timestamp + timezone.timedelta(seconds=context['data']['removal_period'])
        if expires_on is not None and expires_after is not None:
            if expires_on < expires_after:
                expiration_date = expires_on
            else:
                expiration_date = expires_after
        elif expires_on is not None:
            expiration_date = expires_on
        else:
            expiration_date = expires_after

        if context['data']['auto_remove'] == 'default':
            expiration_date = None

        data['expires'] = expiration_date
        data['version'] = version
        return data


def dock_app_list(data):
    """
    Used in generating macOS configuration profiles. Generates a dictionary with details about applications that should
    be added to the Dock.

    :param data: Form data (Dictionary)
    :returns: Dictionary - {'name': <string>, 'path': <string>}
    """
    apps = []
    count = data['extra_dock'] + 1
    for i in range(count):
        name = data['app_name_%s' % str(i)]
        path = data['app_path_%s' % str(i)]
        if name not in [None, '']:
            apps.append({'name': name, 'path': path})
    return apps


def fw_app_list(data):
    """
    Used in generating macOS configuration profiles. Generates a dictionary used in configuring Firewall settings.

    :param data: Form data (Dictionary)
    :returns: Dictionary - {'bundle_id': <string>, 'allowed': <boolean>}
    """
    apps = []
    count = data['extra_firewall']
    for i in range(count):
        bundle = data['id_%s' % str(i + 1)]
        allowed = data['permit_%s' % str(i + 1)]
        if bundle not in [None, '']:
            apps.append({'bundle_id': bundle, 'allowed': allowed})
    return apps


def get_payloads(data):
    """
    Generates a dictionary which specifies which payloads are active in a given profile and what their current
    version numbers are.

    :param data: Form data (Dictionary)
    :returns: Dictionary of payload versions
    """
    types = ['store', 'siri', 'desktop', 'dock', 'energy', 'finder', 'filevault', 'firewall', 'itunes', 'login',
             'passcode', 'password', 'restrictions', 'safari', 'screensaver', 'setup', 'software', 'diagnostics',
             'policy', 'preferences', 'time_machine']
    payloads = {}
    for i, payload in enumerate(types):
        if data.get(types[i] + '_version', None) not in [None, '']:
            payloads[payload] = data.get(types[i] + '_version')
    return payloads


def generate_ids():
    """
    Generates UUIDs for each of the profile's payloads.

    :returns: Dictionary of payload identifiers
    """
    payloads = ['info', 'ad_tracking', 'airdrop', 'store', 'siri', 'desktop', 'desktop_services', 'dock', 'energy',
                'filevault', 'finder', 'firewall', 'itunes', 'login', 'passcode', 'password', 'restrictions', 'safari',
                'screensaver', 'setup', 'software', 'diagnostics', 'policy', 'policy_2', 'preferences',
                'preferences_security', 'time_machine']
    ids = {}
    for i, payload in enumerate(payloads):
        identifier = str(uuid.uuid4()).upper()
        ids[payload] = identifier[9:]
    return ids


def load_ids(data):
    """
    Reassembles payload identifiers. This is necessary because the MDM does not store the full payload identifiers
    with the profile data.

    :param data: Dictionary of payload identifiers
    :returns: Dictionary of payload identifiers
    """
    identifiers = {}
    base_id = settings.MDM_UUID
    for payload in data:
        identifiers[payload] = "%s-%s" % (base_id, data[payload])
    return identifiers


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
@never_cache
def list_profiles(request, pk=0):
    """
    When given a `pk` value, this view will list all the configuration profiles for a given device. When `pk` is not
    supplied, the view will list all the profiles in the MDM.

    :param pk: Primary key of device (Optional)
    """
    context = {'items': [], 'resource_type': 'Profile'}
    handle_expired_profiles()
    if pk == 0:
        context['h2'] = "Configuration Profiles"
        context['header_1'] = "Type"
        context['header_2'] = "Last Modified"
        profiles = ConfigurationProfile.objects.all().reverse()
        for profile in profiles:
            assignment_count = profile.pending_install.count()
            install_count = profile.installed.count()
            data = {'filename': str(profile), 'type': "macOS", 'meta': profile, 'assignment_count': assignment_count,
                    'install_count': install_count}
            context['items'].append(data)
    else:
        device = get_object_or_404(Laptop, pk=pk)
        context['h2'] = "Profiles for {}".format(device.name)
        context['header_1'] = "Version"
        context['header_2'] = "Expires"
        context['device_view'] = True
        context['device_id'] = pk
        profiles = ConfigurationProfile.objects.filter(pending_install__in=[device])
        profiles |= ConfigurationProfile.objects.filter(installed__in=[device])
        for profile in profiles:
            status = 'Not assigned'
            for entry in profile.installed.all():
                if entry == device:
                    status = 'Installed'
            for entry in profile.pending_install.all():
                if entry == device:
                    status = 'Assigned'
            record = InstallationRecord.objects.filter(profile=profile, device=device, active=True).first()
            expires_soon = False
            if record is not None and record.expires is not None:
                if timezone.now() < record.expires < timezone.now() + timezone.timedelta(days=30):
                    expires_soon = True
            data = {'filename': str(profile), 'downloadable': False, 'install_record': record, 'meta': profile,
                    'status': status, 'expires_soon': expires_soon}
            context['items'].append(data)

    return render(request, 'mdm/resource_list.html', context)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def link_profiles(request, device=None, profile=None):
    """
    Assign configuration profiles to a device. If a primary key value for `device` is supplied, a list of profiles will
    be displayed. The user can then select which profiles to assign to the respective device. The opposite is true
    when a primary key value is supplied for `profile`.

    :param device: Primary key of device (Optional)
    :param profile: Primary key of configuration profile (Optional)
    """
    context = {}
    if device is not None:
        resource_type = "profiles"
        rel = get_object_or_404(Laptop, pk=device)
        options = ConfigurationProfile.objects.exclude(Q(pending_install__in=[rel]) | Q(installed__in=[rel]))
        # The following message will be displayed if there are no options (doesn't render in the form view)
        context['message'] = "It seems like there are no more profiles that can be assigned to this device."
    else:
        resource_type = "devices"
        rel = get_object_or_404(ConfigurationProfile, pk=profile)
        options = Laptop.objects.filter(mdm_enrolled=True, retired=False)\
            .exclude(Q(pending__in=[rel]) | Q(installed__in=[rel]))
        # The following message will be displayed if there are no options (doesn't render in the form view)
        context['message'] = "It seems like there are no more eligible devices to assign this profile to."
    if request.method == 'POST':
        form = AssignmentForm(request.POST, type=resource_type, options=options)
        if form.is_valid():
            selected = form.cleaned_data.get('options')
            context['NO_FOOT'] = True
            if isinstance(rel, Laptop):
                for option in selected:
                    config = ConfigurationProfile.objects.get(pk=option)
                    rel.pending.add(config)
                if len(selected) == 1:
                    context['message'] = "1 profile was assigned to %s" % rel.name
                else:
                    context['message'] = "%s profiles were assigned to %s" % (len(selected), rel.name)
            elif isinstance(rel, ConfigurationProfile):
                for option in selected:
                    device = Laptop.objects.get(name=option)
                    rel.pending_install.add(device)
                context['message'] = "This profile has been assigned to %s new device(s)" % (len(selected))
            context['title'] = "Success!"
            context['EXIT_BTN'] = True
            context['EXIT_URL'] = reverse("mdm:list")
            return render(request, 'default.html', context)
        else:
            context['form'] = form
    else:
        if options.count() == 0:
            context['title'] = "Hmm..."
            context['NO_FOOT'] = True
            return render(request, 'default.html', context)
        context['form'] = AssignmentForm(type=resource_type, options=options)
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def profile_devices(request, pk):
    """
    List all devices that are linked to a given profile

    :param pk: Primary key of configuration profile
    """
    context = {}
    profile = get_object_or_404(ConfigurationProfile, pk=pk)
    to_remove = InstallationRecord.objects.filter(profile=profile, device__pending__in=[profile], active=True,
                                                  version="RM")
    pending = Laptop.objects.filter(pending__in=[profile]).exclude(install_records__in=to_remove)
    installed = InstallationRecord.objects.filter(profile=profile, device__installed__in=[profile], active=True)\
        .exclude(version="RM")
    pending_removal = []
    for record in to_remove:
        pending_removal.append(record.device)
    context['resource'] = profile
    context['resource_type'] = 'Profile'
    context['pending'] = pending
    context['pending_removal'] = pending_removal
    context['installed'] = installed
    context['today'] = timezone.now()
    context['expiration_warning'] = timezone.now() + timezone.timedelta(days=30)
    return render(request, 'mdm/device_list.html', context)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def generate_profile(request, pk=0):
    """
    Create or edit a macOS configuration profile

    :param pk: Primary key of configuration profile (Optional)
    """
    context = {}
    extra_dock = int(request.POST.get('extra_dock', 0))
    extra_firewall = int(request.POST.get('extra_firewall', 0))
    config = ConfigurationProfile.objects.filter(pk=pk).first()
    edit_mode = False
    if config is not None:
        edit_mode = True
    if request.method == 'POST':
        form = ProfileForm(request.POST, extra_dock=extra_dock, extra_firewall=extra_firewall, edit_mode=edit_mode)
        if form.is_valid() and request.POST['save'] != "+ Add App" and request.POST['save'] != "Add App":
            context['data'] = form.cleaned_data
            context['password'] = 'Nice Try!'
            context['payloads'] = get_payloads(request.POST)
            context['data']['static_apps'] = dock_app_list(context['data'])
            context['data']['firewall_apps'] = fw_app_list(context['data'])

            # If removal date, convert to string
            if context['data']['removal_date'] is not None:
                context['data']['removal_date'] = context['data']['removal_date'].strftime("%Y-%m-%dT%H:%M:%SZ")

            # Generate UUIDs for the payloads
            if not edit_mode:
                context['identifiers'] = generate_ids()
            else:
                profile_data = open(config.profile)
                data = json.load(profile_data)
                profile_data.close()
                context['identifiers'] = data['identifiers']

            # Save to file
            display_name = request.POST.get('display_name')
            filename = request.POST.get('filename')
            path = os.path.join(settings.MEDIA_ROOT, 'profiles', '{}.json'.format(filename))
            with open(path, 'w') as profile:
                profile.write(json.dumps(context))

            new_profile, created = ConfigurationProfile.objects.get_or_create(
                name=display_name,
                profile=os.path.join(settings.MEDIA_ROOT, 'profiles', '{}.json'.format(filename))
            )
            new_profile.scope = context['data']['scope']
            new_profile.save()

            # If 'Save and Redeploy' selected, configure MDM to update all previously installed copies as well
            if request.POST['save'] == 'Save and Redeploy':
                laptops = Laptop.objects.all().filter(mdm_enrolled=True, retired=False, installed__in=[new_profile])
                for laptop in laptops:
                    laptop.installed.remove(new_profile)
                    laptop.pending.add(new_profile)

            template = loader.get_template('default.html')
            return HttpResponse(template.render({
                'title': "Success!",
                'message': "Your new configuration profile has been generated successfully! It is now available for "
                           "download through the MDM.",
                'NO_FOOT': True,
                'EXIT_BTN': True,
                'EXIT_URL': reverse("mdm:list")
            }, request))
        else:
            if request.POST['save'] == "+ Add App":
                extra_dock += 1
            elif request.POST['save'] == "Add App":
                extra_firewall += 1
            context['form'] = ProfileForm(request.POST, extra_dock=extra_dock, extra_firewall=extra_firewall,
                                          edit_mode=edit_mode)
    else:
        if edit_mode:
            profile_data = open(config.profile)
            file_data = json.load(profile_data)
            if file_data['data']['removal_date'] is not None:
                file_data['data']['removal_date'] = timezone.make_aware(
                    datetime.datetime.strptime(file_data['data']['removal_date'], '%Y-%m-%dT%H:%M:%SZ'))
            profile_data.close()
            form = ProfileForm(None, initial=file_data['data'], extra_dock=file_data['data']['extra_dock'],
                               extra_firewall=file_data['data']['extra_firewall'], edit_mode=True)
        else:
            identifier = str(uuid.uuid4())
            filename = "profile-{}".format(identifier[0:8])
            form = ProfileForm(initial={'filename': filename}, extra_dock=extra_dock, extra_firewall=extra_firewall,
                               edit_mode=False)
        context['form'] = form

    # Ensure the automatic profile removal options are hidden if not being utilized
    context['custom_script'] = "$(document).ready(function (){$('#id_auto_remove').change(function (){" \
                               "if (this.value == 'default') {$('#div_id_removal_date').hide();" \
                               "$('#div_id_removal_period').hide();}else{$('#div_id_removal_date').show();" \
                               "$('#div_id_removal_period').show();}});$('#id_auto_remove').change();});"
    context['msg'] = "Manage Configuration Profile"
    return render(request, 'form_crispy.html', context)


@require_GET
def mobile_config(request, profile_id, action='Install'):
    """
    Endpoint for generating and downloading a macOS configuration profile. The request must include the MDM Client
    token for authentication purposes.

    If `action` is set to `Uninstall`, the resulting file will cause existing copies of the profile to be removed from
    the device.

    :param profile_id: Primary key of configuration profile
    :param action: Either 'Install' or 'Uninstall'
    """
    config = get_object_or_404(ConfigurationProfile, pk=profile_id)
    if not request.GET or 'token' not in request.GET:
        raise PermissionDenied
    token = request.GET['token']
    if token != settings.MDM_TOKEN:
        raise PermissionDenied
    with open(config.profile) as profile:
        context = json.load(profile)
        context['UUID'] = "%s-%s" % (settings.MDM_UUID, context['identifiers']['info'])
        context['identifiers'] = load_ids(context['identifiers'])
        context['password'] = settings.MDM_PASS
        if action == 'Uninstall':
            context['data']['auto_remove'] = 'expire'
            context['data']['removal_date'] = None
            context['data']['removal_period'] = 15
        temp = loader.get_template('mdm/laptop_settings.xml')
        response = FileResponse(temp.render(context), content_type='application/force-download')
        response['Content-Disposition'] = 'attachment; filename="profile.mobileconfig"'
        return response


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def remove_device(request, pk):
    """
    Removes a device from the MDM. Presents warnings and instructions for how to complete the operation correctly.

    :param pk: Primary key of device
    """
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
                                                 'EXIT_BTN': True, 'EXIT_URL': reverse("mdm:list"), 'NO_FOOT': True},
                                                request))
        else:
            context['form'] = RemovalForm(request.POST)
    else:
        if device.serial == 'DISCONNECTED':
            context['form'] = RemovalForm(uninstalled=True)
        else:
            context['form'] = RemovalForm()
    return render(request, 'form_crispy.html', context)


def handle_expired_profiles():
    """Checks for expired profiles and updates listings accordingly"""
    expired_profiles = InstallationRecord.objects.filter(expires__lte=timezone.now(), active=True)
    for record in expired_profiles:
        device = record.device
        profile = record.profile
        device.installed.remove(profile)
        record.active = False
        record.save()


@login_required
@permission_required('devices.view_removal_password', raise_exception=True)
def removal_password(request):
    """Displays the password that can be used to manually remove configuration profiles from managed devices"""
    context = {'title': 'Profile Removal Password', 'password': settings.MDM_PASS, 'now': timezone.now()}
    return render(request, 'laptops/password.html', context)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def remove_profile(request, profile, device=0):
    """
    If a primary key value is supplied for both the `device` and `profile`, the user will be able to remove the
    assignment between the profile and that particular device. If only the `profile` is provided, all device assignments
    for the profile will be removed and the profile data will be deleted. In both cases, two options will be presented
    to the user:

        1.) Mark the profile as removed (if the profile had already been removed manually)

        2.) Instruct the MDM to remove the profile automatically at the next checkin

    :param profile: Primary key of configuration profile
    :param device: Primary key of device (Optional)
    """
    context = {}
    config = get_object_or_404(ConfigurationProfile, pk=profile)
    if device == 0:
        # Completely remove Configuration Profile from MDM
        mode = 'delete'
        if config.installed.all().count() == 0:
            config.delete()
            messages.success(request, "Profile was successfully deleted", extra_tags='success')
            return HttpResponseRedirect(reverse("mdm:list"))
        else:
            context['form'] = ProfileRemovalForm(mode=mode)
    else:
        # Unlink profile from device
        laptop = get_object_or_404(Laptop, pk=device)
        if config in laptop.pending.all():
            laptop.pending.remove(config)
            record = InstallationRecord.objects.filter(profile=config, device=laptop, active=True, version="RM").first()
            # If record exists (profile is already installed) reset to installed status
            if record is not None:
                laptop.installed.add(config)
                with open(config.profile) as profile:
                    context = json.load(profile)
                    record.version = str(context['data']['version'])
                    record.save()
                messages.success(request, "Removal request cancelled", extra_tags='success')
            else:
                messages.success(request, "Profile is no longer assigned to {}".format(laptop.name),
                                 extra_tags='success')
            return HttpResponseRedirect(reverse("mdm:list"))
        elif config in laptop.installed.all():
            mode = 'disassociate'
            context['form'] = ProfileRemovalForm(mode=mode)
        else:
            raise Http404

    # If auto-removal option presented, handle form data
    if request.method == 'POST':
        form = ProfileRemovalForm(request.POST, mode=mode)
        if form.is_valid():
            selected = form.cleaned_data['options']
            if selected == 'auto':
                if mode == 'disassociate':
                    record = get_object_or_404(InstallationRecord, profile=config, device=laptop, active=True)
                    record.version = "RM"
                    record.save()
                    laptop.installed.remove(config)
                    laptop.pending.add(config)
                else:
                    # Cancel all pending assignments first
                    for laptop in config.pending_install.all():
                        config.pending_install.remove(laptop)

                    # Prepare MDM to remove profile from device
                    for laptop in config.installed.all():
                        record = get_object_or_404(InstallationRecord, profile=config, device=laptop, active=True)
                        record.version = "RM"
                        record.save()
                        laptop.installed.remove(config)
                        laptop.pending.add(config)
                messages.success(request, "Profiles will be removed automatically at next checkin",
                                 extra_tags='success')
            else:
                if mode == 'disassociate':
                    record = get_object_or_404(InstallationRecord, profile=config, device=laptop, active=True)
                    record.expires = timezone.now()
                    record.active = False
                    record.save()
                    laptop.installed.remove(config)
                    messages.success(request, "Profile successfully removed from {}".format(laptop.name),
                                     extra_tags='success')
                else:
                    for laptop in config.installed.all():
                        record = get_object_or_404(InstallationRecord, profile=config, device=laptop, active=True)
                        record.expires = timezone.now()
                        record.active = False
                        record.save()
                    config.delete()
                    messages.success(request, "Configuration profile deleted successfully")
            return HttpResponseRedirect(reverse("mdm:list"))
        else:
            context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.add_apps', raise_exception=True)
def add_app(request):
    """
    Administrators can use this page to add new managed applications. Non-admin users will have the option
    to request new software. Requests from non-admins will trigger a notification for the Webmaster.
    """
    context = {}
    title = "New Application"
    if not request.user.has_perm('devices.manage_apps'):
        title = "Request Application"

    if request.method == 'POST':
        form = NewAppForm(data=request.POST, title=title, request_user=request.user)
        if form.is_valid():
            form.save()
            if title == "Request Application":
                message = request.user.name + " has requested that you add " + request.POST['name'] + \
                          " to the list of available applications in the MDM Managed Software Library.<br><br>" \
                          "Log into the <a href='https://lnl.wpi.edu" + reverse("mdm:list") + "'>MDM Console</a> to " \
                          "view or deny the request."
                email = GenericEmailGenerator(subject="New MacBook Software Request", to_emails=settings.EMAIL_TARGET_W,
                                              body=message)
                email.send()
                messages.success(request, "Your request has been submitted. The Webmaster will review it shortly.")
                return HttpResponseRedirect(reverse("home"))
            messages.success(request, "Application added successfully!")
            return HttpResponseRedirect(reverse("mdm:apps"))
    else:
        form = NewAppForm(title=title, request_user=request.user)
    context['form'] = form
    context['msg'] = title
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.view_apps', raise_exception=True)
def view_app(request, pk):
    """
    Details page for a specific managed application

    :param pk: Primary key of managed application
    """

    app = get_object_or_404(MacOSApp, pk=pk)

    context = {'app': app}
    return render(request, 'mdm/app_detail.html', context)


@login_required
@permission_required('devices.view_apps', raise_exception=True)
def app_list(request):
    """Lists all the applications available through Homebrew"""
    return render(request, 'mdm/app_list.html', {})


@login_required
@permission_required('devices.manage_apps', raise_exception=True)
def update_app_info(request, pk):
    """
    Update the metadata for a managed application.

    :param pk: Primary key of managed application
    """
    context = {}

    app = get_object_or_404(MacOSApp, pk=pk)

    if request.method == 'POST':
        form = UpdateAppForm(request.POST, instance=app)
        if form.is_valid():
            if request.POST['save'] == "Save Changes":
                form.save()
                messages.success(request, "Application info updated successfully")
            elif request.POST['save'] == "Merge":
                form.save()
                return HttpResponseRedirect(reverse("mdm:merge-app", args=[app.pk]))
            else:
                app = form.instance
                return HttpResponseRedirect(reverse("mdm:remove-app", args=[app.pk]))
            return HttpResponseRedirect(reverse("mdm:apps"))
    else:
        form = UpdateAppForm(instance=app)
    context['form'] = form
    context['msg'] = "Application Info"
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.manage_apps', raise_exception=True)
def merge_app(request, pk):
    """
    Page for merging two app records together. This is helpful when we want to hide duplicates.

    :param pk: Primary key of the managed application to be merged
    """

    context = {}

    app = get_object_or_404(MacOSApp, pk=pk)

    if request.method == 'POST':
        form = AppMergeForm(request.POST, pk=pk)
        if form.is_valid():
            selected = form.cleaned_data.get('options')
            parent = MacOSApp.objects.get(pk=selected)
            app.merged_into = parent
            app.save()
            if parent.description in [None, ''] and app.description not in [None, '']:
                parent.description = app.description
            if parent.version in [None, ''] and app.version not in [None, '']:
                parent.version = app.version
            if parent.developer in [None, ''] and app.developer not in [None, '']:
                parent.developer = app.developer
            if parent.developer_website in [None, ''] and app.developer_website not in [None, '']:
                parent.developer_website = app.developer_website
            parent.save()
            messages.success(request, 'Applications merged successfully')
            return HttpResponseRedirect(reverse('mdm:apps'))
    else:
        form = AppMergeForm(pk=pk)
    context['form'] = form
    app_name = MacOSApp.objects.get(pk=pk).name
    context['msg'] = 'Merge ' + app_name + ' into...'
    return render(request, 'form_crispy.html', context)


def refresh_managed_software_status():
    """ Checks the Munki catalogs to retrieve the latest managed software lists """

    try:
        with open(settings.MEDIA_ROOT + '/software/catalogs/default', 'rb') as catalog:
            data = plistlib.load(catalog)

            apps = []

            # Grab app data from plist
            for app_data in data:
                app_name = app_data.get('display_name', None)
                app_description = app_data.get('description', None)
                app_version = app_data.get('version', None)
                app_developer = app_data.get('developer', None)
                apps.append({"name": app_name, "description": app_description.strip(), "version": app_version,
                             "developer": app_developer})

            # Update database
            managed_apps = []
            for app in apps:
                obj = MacOSApp.objects.filter(name__iexact=app['name']).first()
                if obj:
                    if obj.merged_into is not None:
                        obj = obj.merged_into
                    obj.managed = True
                    managed_apps.append(obj)
                    if app['description'] and not obj.description:
                        obj.description = app['description']
                    if app['developer'] and not obj.developer:
                        obj.developer = app['developer']
                    if app['version'] and not obj.version:
                        obj.version = app['version']
                    obj.save()
                else:
                    obj = MacOSApp.objects.create(name=app['name'], description=app['description'],
                                                  version=app['version'], developer=app['developer'], managed=True)
                    managed_apps.append(obj)

            # Check for old managed apps that are no longer in the catalog
            for app in MacOSApp.objects.filter(managed=True).all():
                if app not in managed_apps:
                    app.managed = False
                    app.save()
    except FileNotFoundError:
        pass


@login_required
@permission_required("devices.manage_apps", raise_exception=True)
def reload_from_munki(request, pk):
    """
    Refresh an application's record with data from the Munki catalog

    :param pk: The primary key of the application to refresh data for
    """

    app = get_object_or_404(MacOSApp, pk=pk)
    description = app.description
    version = app.version
    app.description = None
    app.version = None
    app.save()

    refresh_managed_software_status()

    app.refresh_from_db()

    if app.description in [None, '']:
        app.description = description
    if app.version in [None, '']:
        app.version = version
    app.save()

    return HttpResponseRedirect(reverse("mdm:app-detail", args=[pk]))


@login_required
@permission_required('devices.view_apps', raise_exception=True)
def list_apps(request, pk=0):
    """
    If a value is provided for `pk`, this will list all the managed applications assigned to the respective device.
    Otherwise this will list all the managed apps under the MDM.

    :param pk: Primary key of device (Optional)
    """
    context = {'items': [], 'resource_type': 'App'}

    if pk == 0:
        context['h2'] = "Managed Applications"
        context['header_1'] = "Developer"
        context['header_2'] = "Version"
        refresh_managed_software_status()
        apps = MacOSApp.objects.filter(merged_into__isnull=True).reverse()
        if not request.user.has_perm('devices.manage_apps'):
            apps = apps.filter(managed=True).exclude(installed__isnull=True, pending_install__isnull=True)
        for app in apps:
            assignment_count = app.pending_install.count()
            installed_on = app.installed.all()
            data = {'meta': app, 'assignment_count': assignment_count, 'installed': installed_on}
            context['items'].append(data)
    else:
        if not request.user.has_perm('devices.manage_apps'):
            raise PermissionDenied

        device = get_object_or_404(Laptop, pk=pk)
        context['h2'] = "Applications on {}".format(device.name)
        context['header_1'] = "Developer"
        context['header_2'] = "Version"
        context['device_view'] = True
        context['device_id'] = pk
        apps = MacOSApp.objects.filter(pending_install__in=[device])
        apps |= MacOSApp.objects.filter(installed__in=[device])
        for app in apps:
            status = 'Not assigned'
            for entry in app.installed.all():
                if entry == device:
                    status = 'Installed'
            for entry in app.pending_install.all():
                if entry == device:
                    status = 'Assigned'
            data = {'meta': app, 'status': status}
            context['items'].append(data)

    return render(request, 'mdm/resource_list.html', context)


@login_required
@permission_required('devices.manage_apps', raise_exception=True)
def list_app_devices(request, pk):
    """
    List all devices linked to a specific app

    :param pk: Primary key of managed application
    """
    context = {}
    app = get_object_or_404(MacOSApp, pk=pk)
    pending = Laptop.objects.filter(apps_pending__in=[app])
    installed = InstallationRecord.objects.filter(app=app, device__apps_installed__in=[app], active=True)
    context['resource'] = app
    context['resource_type'] = 'App'
    context['pending'] = pending
    context['installed'] = installed
    return render(request, 'mdm/device_list.html', context)


@login_required
@permission_required('devices.manage_apps', raise_exception=True)
def link_apps(request, device=None, app=None):
    """
    Assign managed apps to a device. If a primary key value for `device` is supplied, a list of managed applications
    will be displayed. The user can then select which applications to assign to the respective device. The opposite is
    true when a primary key value is supplied for `app`.

    :param device: Primary key of device (Optional)
    :param app: Primary key of managed application (Optional)
    """
    context = {}

    if device is not None:
        resource_type = "apps"
        rel = get_object_or_404(Laptop, pk=device)
        options = MacOSApp.objects.exclude(Q(pending_install__in=[rel]) | Q(installed__in=[rel]))\
            .filter(merged_into__isnull=True)
        # The following message will be displayed if there are no options (doesn't render in the form view)
        context['message'] = "It seems like there are no more applications to assign to this device."
    else:
        resource_type = "devices"
        rel = get_object_or_404(MacOSApp, pk=app)
        options = Laptop.objects.filter(mdm_enrolled=True, retired=False) \
            .exclude(Q(apps_pending__in=[rel]) | Q(apps_installed__in=[rel]))
        # The following message will be displayed if there are no options (doesn't render in the form view)
        context['message'] = "It seems like there are no more eligible devices to assign this app to."
    if request.method == 'POST':
        form = AssignmentForm(request.POST, type=resource_type, options=options)
        if form.is_valid():
            selected = form.cleaned_data.get('options')
            context['NO_FOOT'] = True
            if isinstance(rel, Laptop):
                for option in selected:
                    app = MacOSApp.objects.get(pk=option)
                    rel.apps_pending.add(app)
                if len(selected) == 1:
                    context['message'] = "1 app was assigned to %s" % rel.name
                else:
                    context['message'] = "%s apps were assigned to %s" % (len(selected), rel.name)
            elif isinstance(rel, MacOSApp):
                for option in selected:
                    device = Laptop.objects.get(name=option)
                    rel.pending_install.add(device)
                context['message'] = "This application has been assigned to %s new device(s)" % (len(selected))
            context['title'] = "Success!"
            context['EXIT_BTN'] = True
            context['EXIT_URL'] = reverse("mdm:list")
            return render(request, 'default.html', context)
    else:
        if options.count() == 0:
            context['title'] = "Hmm..."
            context['NO_FOOT'] = True
            return render(request, 'default.html', context)
        form = AssignmentForm(type=resource_type, options=options)
    context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.manage_apps', raise_exception=True)
def remove_app(request, app, device=0):
    """
    If a primary key value is supplied for both the `device` and `app`, the user will be able to remove the
    assignment between the managed application and that particular device. If only the `app` is provided, all device
    assignments for the application will be removed and the app will no longer be available to devices under the MDM.

    :param app: Primary key of managed application
    :param device: Primary key of device (Optional)
    """
    context = {}
    app = get_object_or_404(MacOSApp, pk=app)
    if device == 0:
        # Completely remove Application from MDM
        mode = 'delete'
        if app.installed.all().count() == 0:
            app.delete()
            messages.success(request, "Application was successfully deleted", extra_tags='success')
            return HttpResponseRedirect(reverse("mdm:apps"))
        else:
            context['form'] = UninstallAppForm(mode=mode)
    else:
        # Unlink app from device
        laptop = get_object_or_404(Laptop, pk=device)
        if app in laptop.apps_pending.all():
            laptop.apps_pending.remove(app)
            messages.success(request, "Application is no longer assigned to {}".format(laptop.name),
                             extra_tags='success')
            return HttpResponseRedirect(reverse("mdm:apps"))

        # If pending removal reset to installed status
        if app in laptop.apps_remove.all():
            laptop.apps_installed.add(app)
            laptop.apps_remove.remove(app)
            messages.success(request, "Removal request cancelled", extra_tags='success')
            return HttpResponseRedirect(reverse("mdm:apps"))

        if app in laptop.apps_installed.all():
            mode = 'disassociate'
            context['form'] = UninstallAppForm(mode=mode)
        else:
            raise Http404

    # Handle form data
    if request.method == 'POST':
        form = UninstallAppForm(request.POST, mode=mode)
        if form.is_valid():
            if mode == 'disassociate':
                record = get_object_or_404(InstallationRecord, app=app, device=laptop, active=True)
                record.active = False
                record.expires = timezone.now()
                record.save()
                laptop.apps_installed.remove(app)
                messages.success(request, "Application successfully removed from {}".format(laptop.name),
                                 extra_tags='success')
            else:
                app.delete()
                messages.success(request, "Application deleted successfully")
            return HttpResponseRedirect(reverse("mdm:apps"))
        else:
            context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def logs(request):
    """Displays logs detailing what was installed on what devices and when"""
    def get_timestamp(data):
        return data.get('timestamp')

    events = []
    for record in InstallationRecord.objects.all():
        if record.profile:
            resource = record.profile
            resource_type = "(Configuration Profile) "
        else:
            resource = record.app
            if record.version:
                resource_type = "(" + record.version + ") "
            else:
                resource_type = ""
        if record.active:
            obj = {'timestamp': record.installed_on,
                   'details': resource.name + " " + resource_type + "was installed on " + record.device.name}
            events.append(obj)
        else:
            obj = {'timestamp': record.expires,
                   'details': resource.name + " " + resource_type + "was removed from " + record.device.name}
            events.append(obj)
            obj = {'timestamp': record.installed_on,
                   'details': resource.name + " " + resource_type + "was installed on " + record.device.name}
            events.append(obj)
    events.sort(key=get_timestamp, reverse=True)

    paginator = Paginator(events, 50)
    page_number = request.GET.get('page', 1)
    current_page = paginator.get_page(page_number)
    context = {'headers': ['Timestamp', 'Event'], 'title': 'Install Log', 'events': current_page}
    return render(request, 'access_log.html', context)

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from hashlib import sha256
from itertools import chain
import json, os, datetime, uuid, pytz

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
    NewAppForm, UpdateAppForm, UninstallAppForm
from emails.generators import GenericEmailGenerator


@login_required
@require_GET
@permission_required('devices.view_laptop', raise_exception=True)
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
    laptops = Laptop.objects.filter(retired=False)
    return render(request, 'mdm/mdm_list.html', {'laptops': laptops})


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def install_client(request):
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
    return render(request, 'form_crispy.html', context)


@require_POST
@csrf_exempt
def mdm_enroll(request):
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
    data = json.loads(request.body)
    laptop = get_object_or_404(Laptop, api_key_hash=sha256(data['APIKey'].encode('utf-8')).hexdigest(),
                               mdm_enrolled=True)
    system_profiles = []
    user_profiles = []
    system_profiles_remove = []
    user_profiles_remove = []
    password = None
    apps_install = []
    apps_update = False
    apps_remove = []

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

    for app in laptop.apps_pending.all():
        apps_install.append(app.identifier)

    for app in laptop.apps_installed.all():
        if app.update_available:
            apps_update = True

    for app in laptop.apps_remove.all():
        apps_remove.append(app.identifier)

    if len(system_profiles) > 0 or len(user_profiles) > 0 or len(system_profiles_remove) > 0 or \
            len(user_profiles_remove) > 0 or len(apps_install) > 0 or len(apps_remove) > 0 or apps_update:
        response_data = {"status": 100, "system_profiles": system_profiles, "user_profiles": user_profiles,
                         "system_profiles_remove": system_profiles_remove, "user_profiles_remove": user_profiles_remove,
                         "apps_install": apps_install, "apps_update": apps_update, "apps_remove": apps_remove,
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
    data = json.loads(request.body)
    device = get_object_or_404(Laptop, api_key_hash=sha256(data['APIKey'].encode('utf-8')).hexdigest(),
                               mdm_enrolled=True)
    profiles_installed = data['installed']
    profiles_removed = data['removed']
    apps = data['apps'].split('.')
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
    bypass = False
    for identifier in apps:
        if identifier == "BYPASS":
            bypass = True
        else:
            app = MacOSApp.objects.filter(identifier=identifier).first()
            if app:
                installed.append(app)
    failed = []
    for app in MacOSApp.objects.filter(pending_install=device):
        if app in installed:
            app.pending_install.remove(device)
            app.installed.add(device)
            InstallationRecord.objects.create(app=app, device=device, version=app.version)
        else:
            failed.append(app)
    if len(failed) > 0 and not bypass:
        details = ""
        for app in failed:
            details += "<li>" + app.name + " (Version " + app.version + ")</li>"
        message = "One or more managed applications failed to deploy to <strong>" + device.name + "</strong>. Note " \
                  "that a small number of applications are incompatible with this method of deployment. If " \
                  "problems persist, we recommend attempting to deploy this software through Munki instead.<hr><br>" \
                  "<ul>" + details + "</ul>"
        email = GenericEmailGenerator(subject="Application Deployment Failed", to_emails=settings.EMAIL_TARGET_W,
                                      body=message)
        email.send()
    for app in MacOSApp.objects.filter(Q(pending_removal=device) | Q(installed=device)):
        if app not in installed and not bypass:
            app.installed.remove(device)
            app.pending_removal.remove(device)
            record = InstallationRecord.objects.get(app=app, device=device, active=True)
            record.active = False
            record.expires = timezone.now()
            record.save()
    return JsonResponse({'status': 200})


def get_profile_metadata(config, timestamp):
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
    apps = []
    count = data['extra_dock'] + 1
    for i in range(count):
        name = data['app_name_%s' % str(i)]
        path = data['app_path_%s' % str(i)]
        if name not in [None, '']:
            apps.append({'name': name, 'path': path})
    return apps


def fw_app_list(data):
    apps = []
    count = data['extra_firewall']
    for i in range(count):
        bundle = data['id_%s' % str(i + 1)]
        allowed = data['permit_%s' % str(i + 1)]
        if bundle not in [None, '']:
            apps.append({'bundle_id': bundle, 'allowed': allowed})
    return apps


def get_payloads(data):
    types = ['store', 'siri', 'desktop', 'dock', 'energy', 'finder', 'filevault', 'firewall', 'itunes', 'login',
             'passcode', 'password', 'restrictions', 'safari', 'screensaver', 'setup', 'software', 'diagnostics',
             'policy', 'preferences', 'time_machine']
    payloads = {}
    for i, payload in enumerate(types):
        if data.get(types[i] + '_version', None) not in [None, '']:
            payloads[payload] = data.get(types[i] + '_version')
    return payloads


def generate_ids():
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
    identifiers = {}
    base_id = settings.MDM_UUID
    for payload in data:
        identifiers[payload] = "%s-%s" % (base_id, data[payload])
    return identifiers


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
@never_cache
def list_profiles(request, pk=0):
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
    return render(request, 'form_crispy.html', context)


@require_GET
def mobile_config(request, profile_id, action='Install'):
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
    context = {'title': 'Profile Removal Password', 'password': settings.MDM_PASS, 'now': timezone.now()}
    return render(request, 'laptops/password.html', context)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def remove_profile(request, profile, device=0):
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
                          "complete the process or deny the request."
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
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.view_apps', raise_exception=True)
def app_list(request):
    return render(request, 'mdm/app_list.html', {})


@login_required
@permission_required('devices.manage_apps', raise_exception=True)
def update_app_info(request, pk):
    context = {}

    app = get_object_or_404(MacOSApp, pk=pk)

    if request.method == 'POST':
        form = UpdateAppForm(request.POST, instance=app)
        if form.is_valid():
            if request.POST['save'] == "Save Changes":
                form.save()
                messages.success(request, "Application info updated successfully")
            else:
                app = form.instance
                return HttpResponseRedirect(reverse("mdm:remove-app", args=[app.pk]))
            return HttpResponseRedirect(reverse("mdm:apps"))
    else:
        form = UpdateAppForm(instance=app)
    context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.view_apps', raise_exception=True)
def list_apps(request, pk=0):
    context = {'items': [], 'resource_type': 'App'}

    if pk == 0:
        context['h2'] = "Managed Applications"
        context['header_1'] = "Developer"
        context['header_2'] = "Version"
        apps = MacOSApp.objects.all().reverse()
        if not request.user.has_perm('devices.manage_apps'):
            apps = apps.filter(version__isnull=False)
        for app in apps:
            assignment_count = app.pending_install.count()
            install_count = app.installed.count()
            data = {'meta': app, 'assignment_count': assignment_count, 'install_count': install_count}
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
        apps |= MacOSApp.objects.filter(pending_removal__in=[device])
        for app in apps:
            status = 'Not assigned'
            for entry in app.installed.all():
                if entry == device:
                    status = 'Installed'
            for entry in app.pending_install.all():
                if entry == device:
                    status = 'Assigned'
            for entry in app.pending_removal.all():
                if entry == device:
                    status = 'Pending Removal'
            data = {'meta': app, 'status': status}
            context['items'].append(data)

    return render(request, 'mdm/resource_list.html', context)


@login_required
@permission_required('devices.manage_apps', raise_exception=True)
def list_app_devices(request, pk):
    context = {}
    app = get_object_or_404(MacOSApp, pk=pk)
    to_remove = Laptop.objects.filter(apps_remove__in=[app])
    pending = Laptop.objects.filter(apps_pending__in=[app])
    installed = InstallationRecord.objects.filter(app=app, device__apps_installed__in=[app], active=True)
    context['resource'] = app
    context['resource_type'] = 'App'
    context['pending'] = pending
    context['installed'] = installed
    context['pending_removal'] = to_remove
    return render(request, 'mdm/device_list.html', context)


@login_required
@permission_required('devices.manage_apps', raise_exception=True)
def link_apps(request, device=None, app=None):
    context = {}

    if device is not None:
        resource_type = "apps"
        rel = get_object_or_404(Laptop, pk=device)
        options = MacOSApp.objects.exclude(Q(pending_install__in=[rel]) | Q(installed__in=[rel]))\
            .filter(version__isnull=False)
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

    # If auto-removal option presented, handle form data
    if request.method == 'POST':
        form = UninstallAppForm(request.POST, mode=mode)
        if form.is_valid():
            selected = form.cleaned_data['options']
            if selected == 'auto':
                if mode == 'disassociate':
                    laptop.apps_installed.remove(app)
                    laptop.apps_remove.add(app)
                else:
                    # Cancel all pending assignments first
                    for laptop in app.pending_install.all():
                        app.pending_install.remove(laptop)

                    # Prepare MDM to remove apps from device
                    for laptop in app.installed.all():
                        laptop.apps_installed.remove(app)
                        laptop.apps_remove.add(app)
                messages.success(request, "Applications will be removed automatically at next checkin",
                                 extra_tags='success')
            else:
                if mode == 'disassociate':
                    record = get_object_or_404(InstallationRecord, app=app, device=laptop, active=True)
                    record.active = False
                    record.expires = timezone.now()
                    record.save()
                    laptop.apps_installed.remove(app)
                    messages.success(request, "Application successfully removed from {}".format(laptop.name),
                                     extra_tags='success')
                else:
                    for laptop in app.installed.all():
                        record = get_object_or_404(InstallationRecord, app=app, device=laptop, active=True)
                        record.active = False
                        record.expires = timezone.now()
                        record.save()
                    app.delete()
                    messages.success(request, "Application deleted successfully")
            return HttpResponseRedirect(reverse("mdm:apps"))
        else:
            context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('devices.manage_mdm', raise_exception=True)
def logs(request):

    def get_timestamp(data):
        return data.get('timestamp')

    events = []
    for record in InstallationRecord.objects.all():
        if record.profile:
            resource = record.profile
            resource_type = "Configuration Profile"
        else:
            resource = record.app
            resource_type = "Application"
        if record.active:
            obj = {'timestamp': record.installed_on,
                   'details': resource.name + " (" + resource_type + ") was installed on " + record.device.name}
            events.append(obj)
        else:
            obj = {'timestamp': record.expires,
                   'details': resource.name + " (" + resource_type + ") was removed from " + record.device.name}
            events.append(obj)
            obj = {'timestamp': record.installed_on,
                   'details': resource.name + " (" + resource_type + ") was installed on " + record.device.name}
            events.append(obj)
    events.sort(key=get_timestamp, reverse=True)

    paginator = Paginator(events, 50)
    page_number = request.GET.get('page', 1)
    current_page = paginator.page(page_number)  # TODO: Change when switching to py3 (get_page)
    context = {'headers': ['Timestamp', 'Event'], 'title': 'Install Log', 'events': current_page}
    return render(request, 'access_log.html', context)

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from data.tests.util import ViewTestCase
from django.urls.base import reverse
from django.contrib.auth.models import Permission
from django.conf import settings
from django.utils import timezone
import datetime
from . import models, views, forms
import json, os, logging


logging.disable(logging.WARNING)


class LaptopTestCase(ViewTestCase):
    def setup(self):
        self.api_key = "b8f6F0846f8345ca98D011999CcfA6ad"
        laptop = models.Laptop.objects.create(
            name="Test Laptop",
            api_key_hash="e7b0371cdbf48372368a67c188bbce0f57fb8da970a60433a6e2c127da9bea9c",
            user_password="User",
            admin_password="Admin",
            retired=False
        )
        retrieval = models.LaptopPasswordRetrieval.objects.create(laptop=laptop, user=self.user, admin=False)
        rotation = models.LaptopPasswordRotation.objects.create(laptop=laptop)
        laptop.save()
        retrieval.save()
        rotation.save()

    def test_laptops_list(self):
        self.setup()

        # Make sure the user has proper permissions
        self.assertOk(self.client.get(reverse("laptops:list")), 403)

        permission = Permission.objects.get(codename="view_laptop")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("laptops:list")))

    def test_laptop_history(self):
        self.setup()
        self.assertOk(self.client.get(reverse("laptops:history", args=[1])), 403)

        permission = Permission.objects.get(codename="view_laptop_history")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("laptops:history", args=[1])), 200)
        self.assertOk(self.client.get(reverse("laptops:history", args=[2])), 404)

    def test_laptop_user_password(self):
        self.setup()
        self.assertOk(self.client.get(reverse("laptops:user-password", args=[1])), 403)

        permission = Permission.objects.get(codename="retrieve_user_password")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("laptops:user-password", args=[1])))

    def test_laptop_admin_password(self):
        self.setup()
        self.assertOk(self.client.get(reverse("laptops:admin-password", args=[1])), 403)

        permission = Permission.objects.get(codename="retrieve_admin_password")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("laptops:admin-password", args=[1])))

    def test_rotate_passwords(self):
        self.setup()
        data = {
            'apiKey': self.api_key,
            'userPassword': "NewPass",
            'adminPassword': "OtherNewPass"
        }
        response = {'oldUserPassword': 'User', 'oldAdminPassword': 'Admin'}

        resp = self.client.post(reverse("laptops:rotate-passwords"), json.dumps(data), content_type='application/json')
        self.assertEqual(resp.content, json.dumps(response).encode('utf-8'))
        laptop = models.Laptop.objects.get(name="Test Laptop")
        self.assertEqual(laptop.user_password, 'NewPass')
        self.assertEqual(laptop.admin_password, 'OtherNewPass')


def get_full_formdata():
    complete_data = {'filename': "test", 'display_name': 'Test', 'description': 'A profile', 'scope': 'System',
                     'auto_remove': 'expire', 'removal_period': '30', 'version': 1, 'admin_install': True,
                     'store_version': 1, 'siri_enabled': True, 'siri_version': 1, 'locked': True, 'desktop_version': 1,
                     'autohide': True, 'dock_version': 1, 'disable_sleep': True, 'energy_version': 1,
                     'empty_trash': True, 'finder_version': 1, 'filevault': True, 'filevault_version': 1,
                     'firewall_enable': True, 'block_all': True, 'firewall_version': 1, 'itunes_agreement': True,
                     'itunes_version': 1, 'login_full_name': True, 'login_version': 1, 'passcode_simple': True,
                     'passcode_version': 1, 'enable_protection': True, 'password_version': 1, 'disable_assistant': True,
                     'restrictions_version': 1, 'homepage': 'https://lnl.wpi.edu', 'safari_version': 1,
                     'screensaver_password': True, 'screensaver_delay': 10, 'screensaver_version': 1,
                     'skip_cloud': True, 'setup_version': 1, 'disable_beta': True, 'software_version': 1,
                     'diagnostics': True, 'diagnostics_version': 1, 'developers_policy': True, 'policy_version': 1,
                     'enabled_panes': ['com.apple.preference.dock'], 'preferences_version': 1, 'auto_backup': True,
                     'time_machine_version': 1}
    return complete_data


def generate_profile_data():
    data = {
        'data': {
            'auto_remove': 'default',
            'removal_date': '2020-01-01T11:59:00Z',
            'removal_period': 30,
            'extra_dock': 0,
            'extra_firewall': 0,
            'version': 1
        },
        'identifiers': {
            'info': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'ad_tracking': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'airdrop': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'store': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'siri': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'desktop': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'desktop_services': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'dock': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'energy': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'filevault': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'finder': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'firewall': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'itunes': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'login': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'passcode': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'password': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'restrictions': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'safari': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'screensaver': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'setup': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'software': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'diagnostics': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'policy': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'policy_2': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'preferences': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'preferences_security': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'time_machine': 'F3CC-4DE7-8867-F0B40CA83ECE'
        }
    }
    # Create temporary file with required data
    path = os.path.join(settings.MEDIA_ROOT, 'profiles', 'download-test.json')
    with open(path, 'w') as profile:
        profile.write(json.dumps(data))
    config_profile = models.ConfigurationProfile.objects.create(
        name="Download Test",
        profile=os.path.join(settings.MEDIA_ROOT, 'profiles', 'download-test.json'))
    config_profile.save()
    return config_profile.pk


class MDMTestCase(ViewTestCase):
    def setup(self):
        # Note: These API keys are not real
        self.api_key = "b8f6F0846f8345ca98D011999CcfA6ad"
        self.api_key2 = "Bd00881aA9524ec387f597B5d7D594d6"
        self.laptop = models.Laptop.objects.create(
            name="Test Laptop",
            api_key_hash="e7b0371cdbf48372368a67c188bbce0f57fb8da970a60433a6e2c127da9bea9c",
            user_password="User",
            admin_password="Admin",
            retired=False,
            mdm_enrolled=False
        )
        self.laptop2 = models.Laptop.objects.create(
            name="New Laptop",
            api_key_hash="7f838e357d24dad635d1203094bb2b163af8b0cfd424c1d47106f330fd5a171b",
            user_password="User",
            admin_password="Admin",
            serial="123ABC456DEF78",
            retired=False,
            mdm_enrolled=False
        )

        config_profile = models.ConfigurationProfile.objects.create(
            name="Test",
            profile=os.path.join(settings.MEDIA_ROOT, 'profiles', 'Test.json'))
        config_profile_copy = models.ConfigurationProfile.objects.create(
            name="Test-2",
            scope='User',
            profile=os.path.join(settings.MEDIA_ROOT, 'profiles', 'Test-2.json'))

        models.MacOSApp.objects.create(name="Test Application", identifier="test")
        models.MacOSApp.objects.create(name="Another Application", identifier="test-2")

        config_profile.pending_install.add(self.laptop2)
        config_profile_copy.installed.add(self.laptop2)

    def test_config_profile_str(self):
        self.setup()

        profile = models.ConfigurationProfile.objects.get(name="Test-2")
        self.assertEqual(str(profile), "Test-2")

    def test_macos_app_str(self):
        self.setup()

        app = models.MacOSApp.objects.get(name="Test Application")
        self.assertEqual(str(app), "Test Application")

    def test_installation_record_str(self):
        self.setup()

        profile = models.ConfigurationProfile.objects.get(name="Test-2")
        record = models.InstallationRecord(profile=profile, device=self.laptop, version="1")
        self.assertEqual(str(record), "Test-2 (v1) on Test Laptop")

        app = models.MacOSApp.objects.get(name="Test Application")
        record = models.InstallationRecord(app=app, device=self.laptop, version="1.0.0")
        self.assertEqual(str(record), "Test Application (v1.0.0) on Test Laptop")

    def test_mdm_list(self):
        self.setup()
        # User should not have permission by default
        self.assertOk(self.client.get(reverse("mdm:list")), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:list")))

    def test_install_client(self):
        # User should not have permission by default
        self.assertOk(self.client.get(reverse("mdm:install-client")), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:install-client")))

        data = {'save': 'Agree'}

        # Downloads installer
        self.assertOk(self.client.post(reverse("mdm:install-client"), data))

    def test_mdm_enroll(self):
        self.setup()

        # GET request should not be allowed
        self.assertOk(self.client.get(reverse("mdm:start-enrollment")), 405)

        # Example with existing computer
        data = {
            'token': settings.MDM_TOKEN,
            'hostname': 'Test Laptop',
            'APIKey': self.api_key,
            'serial': 'ABCD1234EFG567',
            'networkIP': '192.168.1.2'
        }
        # Test invalid token
        invalid_data = {
            'token': 'invalid token',
            'hostname': 'Test Laptop',
            'APIKey': self.api_key,
            'serial': 'ABCD1234EFG567',
            'networkIP': '192.168.1.2'
        }
        response = {'next': '/mdm/enrollment/1/'}

        # Returns 0 when tokens do not match (attempting to load this url would result in an error)
        invalid_response = {'next': '/mdm/enrollment/0/'}

        resp = self.client.post(reverse("mdm:start-enrollment"), json.dumps(data), content_type="application/json")
        invalid_resp = self.client.post(reverse("mdm:start-enrollment"), json.dumps(invalid_data),
                                        content_type="application/json")
        self.assertEqual(resp.content, json.dumps(response).encode('utf-8'))
        self.assertEqual(invalid_resp.content, json.dumps(invalid_response).encode('utf-8'))
        self.laptop.refresh_from_db()
        self.assertEqual(self.laptop.serial, 'ABCD1234EFG567')
        self.assertEqual(self.laptop.last_ip, '192.168.1.2')

        # Example with new computer
        data = {
            'token': settings.MDM_TOKEN,
            'hostname': 'New-Computer',
            'APIKey': 'Ce11662bB9421fD378e967B4d7E624e6',
            'serial': '987654321CBA',
            'networkIP': '192.168.1.3'
        }
        response = {'next': '/mdm/enrollment/3/'}

        resp = self.client.post(reverse("mdm:start-enrollment"), json.dumps(data), content_type="application/json")
        self.assertEqual(resp.content, json.dumps(response).encode('utf-8'))
        laptop = models.Laptop.objects.all().get(name="New-Computer")
        self.assertEqual(laptop.serial, '987654321CBA')
        self.assertEqual(laptop.last_ip, '192.168.1.3')

    def test_complete_enrollment(self):
        self.setup()
        # User should not have permission by default
        self.assertOk(self.client.get(reverse("mdm:enroll", args=[2])), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:enroll", args=[2])))

        # Passing an argument of 0 should throw permission denied (token was likely invalid on initial contact)
        self.assertOk(self.client.get(reverse("mdm:enroll", args=[0])), 403)

        valid_data = {
            'name': 'Enrolled Computer',
            'asset_tag': 'WPI002',
            'user_password': 'Password',
            'admin_password': 'Password.1'
        }

        invalid_data = {
            'name': 'Enrolled Computer',
            'asset_tag': '',
            'user_password': 'Password',
            'admin_password': 'Password.1'
        }

        form = forms.EnrollmentForm(data=valid_data)
        self.assertTrue(form.is_valid())

        resp = self.client.post(reverse("mdm:enroll", args=[2]), invalid_data)
        self.assertNotContains(resp, "Success!")

        resp = self.client.post(reverse("mdm:enroll", args=[2]), valid_data)
        self.assertContains(resp, "Success!")

        # Link should now be deactivated
        self.assertOk(self.client.get(reverse("mdm:enroll", args=[2])), 404)

    def test_mdm_checkin(self):
        self.setup()

        self.laptop2.mdm_enrolled = True
        self.laptop2.save()

        data = {'APIKey': self.api_key2, 'networkIP': '192.168.1.3'}

        output_without_resources = {'status': 200}
        output_with_profiles = {
            'status': 100,
            'system_profiles': [1],
            'user_profiles': [],
            'system_profiles_remove': [],
            'user_profiles_remove': [],
            'removal_password': None,
            'password': self.laptop2.admin_password
        }
        output_remove_profiles = {
            'status': 100,
            'system_profiles': [],
            'user_profiles': [],
            'system_profiles_remove': [1],
            'user_profiles_remove': [],
            'removal_password': settings.MDM_PASS,
            'password': self.laptop2.admin_password
        }

        # Check that GET request is not allowed
        self.assertOk(self.client.get(reverse("mdm:checkin")), 405)

        resp = self.client.post(reverse("mdm:checkin"), json.dumps(data), content_type="application/json")
        self.assertEqual(resp.content, json.dumps(output_with_profiles).encode('utf-8'))

        # Simulate a confirmed install
        profile = models.ConfigurationProfile.objects.get(name="Test")
        self.laptop2.pending.remove(profile)
        self.laptop2.installed.add(profile)

        # Check that no more profiles are pending for this device on next checkin
        resp = self.client.post(reverse("mdm:checkin"), json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.content, json.dumps(output_without_resources).encode('utf-8'))

        # Prepare for removal
        record = models.InstallationRecord.objects.create(profile=profile, device=self.laptop2, active=True,
                                                          version="RM")
        self.laptop2.pending.add(profile)
        self.laptop2.installed.remove(profile)

        # Check that profile is pending for removal this time
        resp = self.client.post(reverse("mdm:checkin"), json.dumps(data), content_type="application/json")
        self.assertEqual(resp.content, json.dumps(output_remove_profiles).encode('utf-8'))

        record.version = "1"
        record.save()

        self.laptop2.pending.remove(profile)

        app = models.MacOSApp.objects.get(name="Test Application")
        app2 = models.MacOSApp.objects.get(name="Another Application")
        app3 = models.MacOSApp.objects.create(name="Third Application", identifier="num-3")
        app.pending_install.add(self.laptop2)
        app2.pending_removal.add(self.laptop2)
        app3.installed.add(self.laptop2)
        app.save()
        app2.save()

        self.laptop2.refresh_from_db()
        self.assertIsNotNone(self.laptop2.last_checkin)

    def test_install_confirmation(self):
        self.setup()
        pk = generate_profile_data()
        self.laptop2.mdm_enrolled = True
        self.laptop2.save()

        # Check that GET request is not allowed
        self.assertOk(self.client.get(reverse("mdm:confirm-install")), 405)

        data_with_apps = {
            'APIKey': self.api_key2,
            'apps': 'Test App=1.0.1#SecondApp=#Third App=2021.11 (1062)#',
            'installed': [],
            'removed': [],
            'timestamp': '2020-01-01T11:59:00Z'
        }

        data_install_profile = {
            'APIKey': self.api_key2,
            'apps': 'Test App=1.0.1#SecondApp=#Third App=2021.11 (1062)#',
            'installed': ['%s' % pk],
            'removed': [],
            'timestamp': '2020-01-01T11:59:00Z'
        }

        data_remove_profile = {
            'APIKey': self.api_key2,
            'apps': 'Test App=1.0.1#SecondApp=#Third App=2021.11 (1062)#',
            'installed': [],
            'removed': ['%s' % pk],
            'timestamp': '2020-01-01T11:59:00Z'
        }

        # Verify that one of the MacOS apps does not exist at first
        self.assertFalse(models.MacOSApp.objects.filter(name="Test App").exists())

        # Create an app that has been assigned to the device
        app = models.MacOSApp.objects.create(name="SecondApp", managed=True)
        app.pending_install.add(self.laptop2)

        # Create a record for an app that has been removed from the device
        app2 = models.MacOSApp.objects.create(name="AnotherApp")
        models.InstallationRecord.objects.create(app=app2, device=self.laptop2)
        app2.installed.add(self.laptop2)

        # Create an app that has been merged into another
        models.MacOSApp.objects.create(name="Third App", merged_into=app)

        resp = self.client.post(reverse("mdm:confirm-install"), json.dumps(data_with_apps),
                                content_type="application/json")
        self.assertEqual(resp.content, json.dumps({'status': 200}).encode('utf-8'))

        app.refresh_from_db()

        self.assertIn(self.laptop2, app.installed.all())
        self.assertNotIn(self.laptop2, app.pending_install.all())
        self.assertNotIn(self.laptop2, app2.installed.all())
        self.assertTrue(models.InstallationRecord.objects.filter(app=app2, device=self.laptop2, active=False).exists())
        self.assertTrue(models.MacOSApp.objects.filter(name="Test App").exists())
        self.assertEqual(app.version, "2021.11 (1062)")

        # Verify that record does not exist at first
        profile = models.ConfigurationProfile.objects.get(pk=pk)
        self.assertFalse(models.InstallationRecord.objects.filter(profile=profile, device=self.laptop2).exists())

        # Process installed profiles
        resp = self.client.post(reverse("mdm:confirm-install"), json.dumps(data_install_profile),
                                content_type="application/json")
        self.assertEqual(resp.content, json.dumps({'status': 200}).encode('utf-8'))

        self.assertNotIn(profile, self.laptop2.pending.all())
        self.assertIn(profile, self.laptop2.installed.all())
        self.assertTrue(models.InstallationRecord.objects.filter(profile=profile, device=self.laptop2).exists())

        # Check to ensure that a re-installed profile updates the record instead of creating a new one
        self.client.post(reverse("mdm:confirm-install"), json.dumps(data_install_profile),
                         content_type="application/json")
        self.assertEqual(models.InstallationRecord.objects.filter(profile=profile, device=self.laptop2).count(), 1)

        # As part of the removal process, the profile would be moved from installed to pending
        self.laptop2.installed.remove(profile)
        self.laptop2.pending.add(profile)

        # Now test that the profile has been removed correctly
        resp = self.client.post(reverse("mdm:confirm-install"), json.dumps(data_remove_profile),
                                content_type="application/json")
        self.assertEqual(resp.content, json.dumps({'status': 200}).encode('utf-8'))

        self.assertNotIn(profile, self.laptop2.pending.all())
        self.assertNotIn(profile, self.laptop2.installed.all())

        self.assertFalse(models.InstallationRecord.objects.get(profile=profile, device=self.laptop2).active)

    def test_get_profile_metadata(self):
        self.setup()

        default_data = {
            'data': {
                'auto_remove': 'default',
                'removal_date': '2020-01-01T11:59:00Z',
                'removal_period': 30,
                'version': 1
            }
        }

        date_data = {
            'data': {
                'auto_remove': 'expire',
                'removal_date': '2020-01-01T11:59:00Z',
                'removal_period': None,
                'version': 1
            }
        }

        duration_data = {
            'data': {
                'auto_remove': 'expire',
                'removal_date': None,
                'removal_period': 30,
                'version': 1
            }
        }

        full_data = {
            'data': {
                'auto_remove': 'expire',
                'removal_date': '2020-01-01T11:59:00Z',
                'removal_period': 30,
                'version': 1
            }
        }

        # Create temporary files with required data
        path1 = os.path.join(settings.MEDIA_ROOT, 'profiles', 'record-test-1.json')
        path2 = os.path.join(settings.MEDIA_ROOT, 'profiles', 'record-test-2.json')
        path3 = os.path.join(settings.MEDIA_ROOT, 'profiles', 'record-test-3.json')
        path4 = os.path.join(settings.MEDIA_ROOT, 'profiles', 'record-test-4.json')
        with open(path1, 'w') as profile:
            profile.write(json.dumps(default_data))
        with open(path2, 'w') as profile:
            profile.write(json.dumps(full_data))
        with open(path3, 'w') as profile:
            profile.write(json.dumps(date_data))
        with open(path4, 'w') as profile:
            profile.write(json.dumps(duration_data))
        config = models.ConfigurationProfile.objects.create(name="Record-Tests", profile=path1)
        config.save()

        timestamp = timezone.now()

        # Test that expiration date is None if profile is not set to automatically expire (default behavior)
        metadata = views.get_profile_metadata(config, timestamp)
        self.assertIsNone(metadata['expires'])

        # Enable profile expiration (using both types) and remove the last test file
        config.profile = path2
        config.save()
        os.remove(path1)

        # The removal_date should come before the date defined by the duration
        expiration_date = timezone.datetime(2020, 1, 1, 16, 59, 0, 0, datetime.timezone.utc)
        metadata = views.get_profile_metadata(config, timestamp)
        self.assertEqual(metadata['expires'], expiration_date)

        # Ensure that the duration value will come before the expiration date
        timestamp = timezone.datetime(2020, 1, 1, 10, 30, 0, 0, datetime.timezone.utc)
        metadata = views.get_profile_metadata(config, timestamp)
        self.assertEqual(metadata['expires'], timestamp + timezone.timedelta(seconds=30))

        # Remove the duration value from the data and check that profile expires on expiration date
        config.profile = path3
        config.save()
        os.remove(path2)

        metadata = views.get_profile_metadata(config, timestamp)
        self.assertEqual(metadata['expires'], expiration_date)

        # Remove the expiration date from the data and check that expiration date is based on duration
        config.profile = path4
        config.save()
        os.remove(path3)

        metadata = views.get_profile_metadata(config, timestamp)
        self.assertEqual(metadata['expires'], timestamp + timezone.timedelta(seconds=30))

        os.remove(os.path.join(settings.MEDIA_ROOT, 'profiles', 'record-test-4.json'))

    def test_dock_app_list(self):
        # Dock extra apps count = 0
        no_data = {'extra_dock': 0, 'app_name_0': '', 'app_path_0': ''}
        response = []
        apps = views.dock_app_list(no_data)
        self.assertEqual(apps, response)

        # Dock extra apps count = 1
        one_app = {
            'extra_dock': 1,
            'app_name_0': 'TestApp',
            'app_path_0': '/System/TestApp.app',
            'app_name_1': '',
            'app_path_1': ''
        }
        response = [{'name': 'TestApp', 'path': '/System/TestApp.app'}]
        apps = views.dock_app_list(one_app)
        self.assertEqual(apps, response)

        # Dock extra apps count = 2
        two_apps = {
            'extra_dock': 2,
            'app_name_0': 'TestApp',
            'app_path_0': '/System/TestApp.app',
            'app_name_1': 'SuperCoolApp',
            'app_path_1': '/System/SuperCoolApp.app',
            'app_name_2': '',
            'app_path_2': ''
        }
        response = [{'name': 'TestApp', 'path': '/System/TestApp.app'},
                    {'name': 'SuperCoolApp', 'path': '/System/SuperCoolApp.app'}]
        apps = views.dock_app_list(two_apps)
        self.assertEqual(apps, response)

    def test_fw_app_list(self):
        # No firewall apps
        no_apps = {'extra_firewall': 0}
        response = []
        apps = views.fw_app_list(no_apps)
        self.assertEqual(apps, response)

        # 1 firewall app
        one_app = {'extra_firewall': 1, 'id_1': 'com.apple.Safari', 'permit_1': True}
        response = [{'bundle_id': 'com.apple.Safari', 'allowed': True}]
        apps = views.fw_app_list(one_app)
        self.assertEqual(apps, response)

        # 2 firewall apps
        two_apps = {
            'extra_firewall': 2,
            'id_1': 'com.example.BadApp',
            'permit_1': False,
            'id_2': 'com.apple.Safari',
            'permit_2': True
        }
        response = [{'bundle_id': 'com.example.BadApp', 'allowed': False},
                    {'bundle_id': 'com.apple.Safari', 'allowed': True}]
        apps = views.fw_app_list(two_apps)
        self.assertEqual(apps, response)

    def test_get_payloads(self):
        # Confirm that payloads are only activated when they need to be and can be activated correctly
        no_payloads = {}
        all_payloads = {'store_version': 1, 'siri_version': 1, 'desktop_version': 1, 'dock_version': 1,
                        'energy_version': 1, 'filevault_version': 1, 'finder_version': 1, 'firewall_version': 1,
                        'itunes_version': 1, 'login_version': 1, 'passcode_version': 1, 'password_version': 1,
                        'restrictions_version': 1, 'safari_version': 1, 'screensaver_version': 1, 'setup_version': 1,
                        'software_version': 1, 'diagnostics_version': 1, 'policy_version': 1, 'preferences_version': 1,
                        'time_machine_version': 1}
        payloads = {'store': 1, 'siri': 1, 'desktop': 1, 'dock': 1, 'energy': 1, 'filevault': 1, 'finder': 1,
                    'firewall': 1, 'login': 1, 'itunes': 1, 'passcode': 1, 'password': 1, 'restrictions': 1,
                    'safari': 1, 'screensaver': 1, 'setup': 1, 'software': 1, 'diagnostics': 1, 'policy': 1,
                    'preferences': 1, 'time_machine': 1}
        empty = views.get_payloads(no_payloads)
        full = views.get_payloads(all_payloads)
        self.assertEqual(empty, {})
        self.assertEqual(full, payloads)

    def test_list_profiles(self):
        self.setup()
        profile = models.ConfigurationProfile.objects.get(pk=2)
        record = models.InstallationRecord.objects.create(profile=profile, device=self.laptop2,
                                                          expires=timezone.now() + timezone.timedelta(days=1),
                                                          active=True)
        record.save()

        # User should not have permission by default
        self.assertOk(self.client.get(reverse("mdm:profiles")), 403)
        self.assertOk(self.client.get(reverse("mdm:device-profiles", args=[1])), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:profiles")))
        self.assertOk(self.client.get(reverse("mdm:device-profiles", args=[2])))

        # Should 404 when laptop does not exist with that pk
        self.assertOk(self.client.get(reverse("mdm:device-profiles", args=[3])), 404)

    def test_generate_ids(self):
        data = views.generate_ids()
        # There should be 26 payloads
        self.assertEqual(len(data), 27)
        # An identifier should have a length of 27
        self.assertEqual(len(data['info']), 27)

    def test_load_ids(self):
        data = {
            'info': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'ad_tracking': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'airdrop': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'store': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'siri': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'desktop': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'desktop_services': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'dock': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'energy': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'filevault': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'finder': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'firewall': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'itunes': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'login': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'passcode': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'password': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'restrictions': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'safari': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'screensaver': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'setup': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'software': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'diagnostics': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'policy': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'policy_2': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'preferences': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'preferences_security': 'F3CC-4DE7-8867-F0B40CA83ECE',
            'time_machine': 'F3CC-4DE7-8867-F0B40CA83ECE'
        }
        correct_value = "%s-F3CC-4DE7-8867-F0B40CA83ECE" % settings.MDM_UUID
        output = {
            'info': correct_value,
            'ad_tracking': correct_value,
            'airdrop': correct_value,
            'store': correct_value,
            'siri': correct_value,
            'desktop': correct_value,
            'desktop_services': correct_value,
            'dock': correct_value,
            'energy': correct_value,
            'filevault': correct_value,
            'finder': correct_value,
            'firewall': correct_value,
            'itunes': correct_value,
            'login': correct_value,
            'passcode': correct_value,
            'password': correct_value,
            'restrictions': correct_value,
            'safari': correct_value,
            'screensaver': correct_value,
            'setup': correct_value,
            'software': correct_value,
            'diagnostics': correct_value,
            'policy': correct_value,
            'policy_2': correct_value,
            'preferences': correct_value,
            'preferences_security': correct_value,
            'time_machine': correct_value
        }
        self.assertEqual(views.load_ids(data), output)

    def test_link_profiles(self):
        self.setup()
        config_profile = models.ConfigurationProfile.objects.create(
            name="Another Test",
            profile=os.path.join(settings.MEDIA_ROOT, 'profiles', 'Another-Test.json'))
        config_profile.save()
        another_profile = models.ConfigurationProfile.objects.create(
            name="Yet Another",
            profile=os.path.join(settings.MEDIA_ROOT, 'profiles', 'Yet-Another.json'))
        another_profile.save()

        self.laptop2.mdm_enrolled = True
        self.laptop2.save()

        # User should not have permission by default
        self.assertOk(self.client.get(reverse("mdm:add-profiles", args=[1])), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        # One with options and one without
        self.assertOk(self.client.get(reverse("mdm:add-profiles", args=[2])))
        resp = self.client.get(reverse("mdm:profile-add-devices", args=[1]))
        self.assertContains(resp, "Hmm...")

        invalid_data = {}
        profile_data = {'options': ["3"], 'save': 'Assign'}
        device_data = {'options': ["New Laptop"], 'save': 'Assign'}

        # Test that we get form back on invalid data
        self.assertOk(self.client.post(reverse("mdm:profile-add-devices", args=[3]), invalid_data))

        # Test valid data
        resp = self.client.post(reverse("mdm:add-profiles", args=[2]), profile_data)
        self.assertOk(resp)

        resp = self.client.post(reverse("mdm:profile-add-devices", args=[another_profile.pk]), device_data)
        self.assertOk(resp)

        # Test that profiles were actually linked properly
        self.assertIn(self.laptop2, list(config_profile.pending_install.all()))
        self.assertIn(another_profile, list(self.laptop2.pending.all()))

    def test_generate_profile(self):
        self.setup()
        existing = generate_profile_data()
        self.laptop2.mdm_enrolled = True
        self.laptop2.save()
        profile = models.ConfigurationProfile.objects.get(pk=existing)
        self.laptop2.installed.add(profile)

        # User should not have permission by default
        self.assertOk(self.client.get(reverse('mdm:generate')), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse('mdm:generate')))

        # Test that we can get the form to edit profiles as well (essentially the same view)
        self.assertOk(self.client.get(reverse("mdm:edit", args=[existing])))

        invalid_data = {
            'display_name': 'Test',
            'filename': 'test',
            'scope': 'System',
            'version': 1,
            'autohide': True,
            'dock_version': '',
            'extra_dock': 0,
            'extra_firewall': 0,
            'save': 'Save'
        }

        valid_data = {
            'display_name': 'Generate Test',
            'description': 'A Profile',
            'filename': 'generate-test',
            'scope': 'System',
            'auto_remove': 'default',
            'version': 1,
            'autohide': True,
            'dock_version': 1,
            'extra_dock': 0,
            'extra_firewall': 0,
            'save': 'Save'
        }

        edit_data = {
            'display_name': 'Download Test',
            'description': 'Another profile',
            'filename': 'download-test',
            'scope': 'System',
            'auto_remove': 'expire',
            'removal_date': timezone.now(),
            'version': 2,
            'autohide': True,
            'dock_version': 1,
            'extra_dock': 0,
            'extra_firewall': 0,
            'save': 'Save and Redeploy'
        }

        add_dock_app = {
            'display_name': 'Test',
            'description': 'More profiles',
            'filename': 'test',
            'scope': 'System',
            'auto_remove': 'default',
            'version': 1,
            'dock_version': 1,
            'extra_dock': 1,
            'app_name_0': 'Safari',
            'app_path_0': '/System/Safari.app',
            'app_name_1': 'Spotify',
            'app_path_1': '/System/Spotify.app',
            'extra_firewall': 0,
            'save': '+ Add App'
        }

        add_firewall_app = {
            'display_name': 'Test',
            'description': 'More profiles',
            'filename': 'test',
            'scope': 'System',
            'auto_remove': 'default',
            'version': 1,
            'autohide': True,
            'dock_version': 1,
            'extra_dock': 0,
            'extra_firewall': 1,
            'id_1': 'com.apple.Safari',
            'permit_1': True,
            'save': 'Add App'
        }

        # On invalid data, we should get form back
        self.assertOk(self.client.post(reverse("mdm:generate"), invalid_data))

        # When adding an app, the form should not be submitted yet
        self.assertOk(self.client.post(reverse("mdm:generate"), add_dock_app))
        self.assertEqual(models.ConfigurationProfile.objects.all().count(), 3)

        self.assertOk(self.client.post(reverse("mdm:generate"), add_firewall_app))
        self.assertEqual(models.ConfigurationProfile.objects.all().count(), 3)

        # On valid data, save to file
        self.assertOk(self.client.post(reverse("mdm:generate"), valid_data))
        self.assertEqual(models.ConfigurationProfile.objects.all().count(), 4)

        resp = self.client.post(reverse("mdm:edit", args=[existing]), edit_data)
        self.assertOk(resp)
        self.assertContains(resp, "Success!")
        self.assertEqual(models.ConfigurationProfile.objects.all().count(), 4)

        # Check that profile was set for redeployment
        self.assertEqual(self.laptop2.installed.count(), 1)  # Should only be the one from the setup now
        self.assertEqual(self.laptop2.pending.count(), 2)  # Should include the profile we just edited

        # Clean up afterwards :)
        os.remove(os.path.join(settings.MEDIA_ROOT, 'profiles', 'generate-test.json'))
        os.remove(os.path.join(settings.MEDIA_ROOT, 'profiles', 'download-test.json'))

    def test_profile_devices(self):
        self.setup()

        # User should not have permission by default
        self.assertOk(self.client.get(reverse("mdm:assignments", args=[1])), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:assignments", args=[1])))

        # Check to ensure that profiles are linked properly
        profile = models.ConfigurationProfile.objects.get(pk=1)
        self.assertEqual(list(profile.pending_install.all()), [self.laptop2])
        self.assertNotEqual(list(profile.pending_install.all()), [self.laptop])

    def test_mobile_config(self):
        config_profile = generate_profile_data()

        invalid_data = {'token': 'invalid'}
        self.assertOk(self.client.get(reverse("mdm:install", args=[config_profile])), 403)
        self.assertOk(self.client.get(reverse("mdm:install", args=[config_profile]), invalid_data), 403)

        valid_data = {'token': settings.MDM_TOKEN}
        self.assertOk(self.client.get(reverse("mdm:install", args=[config_profile]), valid_data))

        self.assertOk(self.client.get(reverse("mdm:uninstall", args=[config_profile]), valid_data))

        # Clean up afterwards
        os.remove(os.path.join(settings.MEDIA_ROOT, 'profiles', 'download-test.json'))

    def test_profile_form(self):
        valid_data = {
            'display_name': "Test",
            'description': 'Test profile',
            'filename': "test",
            'scope': 'System',
            'auto_remove': 'default',
            'version': 1,
            'extra_dock': 0,
            'extra_firewall': 0
        }
        invalid_data = {
            'display_name': "",
            'description': 'Test profile',
            'filename': "test",
            'scope': 'System',
            'auto_remove': 'default',
            'version': None,
            'extra_dock': 0,
            'extra_firewall': 0
        }
        valid_form = forms.ProfileForm(data=valid_data, extra_dock=0, extra_firewall=0, edit_mode=False)
        invalid_form = forms.ProfileForm(data=invalid_data, extra_dock=0, extra_firewall=0, edit_mode=False)

        self.assertTrue(valid_form.is_valid())
        self.assertFalse(invalid_form.is_valid())

        # Tests implementation with all payloads active
        data = get_full_formdata()
        valid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertTrue(valid_form.is_valid())

    def test_clean_store_version(self):
        data = get_full_formdata()
        data['store_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_siri_version(self):
        data = get_full_formdata()
        data['siri_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_desktop_version(self):
        data = get_full_formdata()
        data['desktop_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['locked'] = False
        data['desktop_path'] = '/some/path'
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_dock_version(self):
        data = get_full_formdata()
        valid_form = forms.ProfileForm(data=data, extra_dock=2, extra_firewall=0, edit_mode=False)
        self.assertTrue(valid_form.is_valid())

        data['dock_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=2, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['app_name_0'] = 'Some App'
        data['autohide'] = False
        invalid_form = forms.ProfileForm(data=data, extra_dock=1, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_energy_version(self):
        data = get_full_formdata()
        # This should be none if sleep is disabled
        data['battery_display_timer'] = 2
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['energy_version'] = None
        data['battery_display_timer'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['disable_sleep'] = False
        data['battery_display_timer'] = 2
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_finder_version(self):
        data = get_full_formdata()
        data['finder_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['empty_trash'] = False
        data['preferred_style'] = 'some-style'
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_filevault_version(self):
        data = get_full_formdata()
        data['filevault_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_firewall_version(self):
        data = get_full_formdata()
        valid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=2, edit_mode=False)
        self.assertTrue(valid_form.is_valid())

        data['firewall_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        # Ensure that firewall must be enabled to use secondary features
        data['firewall_version'] = 1
        data['firewall_enable'] = False
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_itunes_version(self):
        data = get_full_formdata()
        data['itunes_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_login_version(self):
        data = get_full_formdata()
        data['login_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['text'] = 'Words and stuff'
        data['login_full_name'] = False
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_time_reset(self):
        data = get_full_formdata()
        data['time_reset'] = 15
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_passcode_version(self):
        data = get_full_formdata()
        data['passcode_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['passcode_attempts'] = 6
        data['passcode_simple'] = False
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_password_version(self):
        data = get_full_formdata()
        data['password_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_restrictions_version(self):
        data = get_full_formdata()
        data['restrictions_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_safari_version(self):
        data = get_full_formdata()
        data['safari_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['homepage'] = None
        data['safe_downloads'] = True
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_screensaver_version(self):
        data = get_full_formdata()
        data['screensaver_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['screensaver_delay'] = None
        data['screensaver_version'] = 1
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_setup_version(self):
        data = get_full_formdata()
        data['setup_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_software_version(self):
        data = get_full_formdata()
        data['software_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_diagnostics_version(self):
        data = get_full_formdata()
        data['diagnostics_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_policy_version(self):
        data = get_full_formdata()
        data['policy_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_preferences_version(self):
        data = get_full_formdata()
        data['disabled_panes'] = ['com.apple.preference.dock']
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

        data['disabled_panes'] = []
        data['preferences_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_clean_time_machine_version(self):
        data = get_full_formdata()
        data['time_machine_version'] = None
        invalid_form = forms.ProfileForm(data=data, extra_dock=0, extra_firewall=0, edit_mode=False)
        self.assertFalse(invalid_form.is_valid())

    def test_remove_device(self):
        self.setup()
        self.laptop2.serial = 'DISCONNECTED'  # The MDM resets the serial no. when client is uninstalled from the device
        self.laptop2.mdm_enrolled = True
        self.laptop2.save()

        # User should not be allowed to access by default
        self.assertOk(self.client.get(reverse("mdm:remove", args=[self.laptop2.pk])), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:remove", args=[self.laptop2.pk])))

        valid_data = {
            'profiles_removed': True,
            'client_removed': True,
            'password_rotation': True,
            'agree': True,
            'save': 'Confirm'
        }

        invalid_data = {
            'profiles_removed': True,
            'client_removed': True,
            'password_rotation': True,
            'agree': False,
            'save': 'Confirm'
        }

        laptop2 = models.Laptop.objects.get(name="New Laptop")
        self.assertOk(self.client.post(reverse("mdm:remove", args=[laptop2.pk]), invalid_data))
        self.assertTrue(laptop2.mdm_enrolled)

        self.assertOk(self.client.post(reverse("mdm:remove", args=[laptop2.pk]), valid_data))
        laptop2.refresh_from_db()
        self.assertFalse(laptop2.mdm_enrolled)

    def test_handle_expired_profiles(self):
        self.setup()
        self.laptop2.mdm_enrolled = True

        future_date = timezone.now() + timezone.timedelta(days=1)
        past_date = timezone.now() + timezone.timedelta(days=-1)

        profile = models.ConfigurationProfile.objects.get(pk=2)
        record = models.InstallationRecord.objects.create(profile=profile, device=self.laptop2, version="1",
                                                          expires=future_date, active=True)
        record.save()

        # Test that profiles with future expiration date are not affected
        views.handle_expired_profiles()
        record.refresh_from_db()
        self.assertTrue(record.active)

        # Test that profiles expiring at that moment are removed properly
        record.expires = timezone.now()
        record.save()
        views.handle_expired_profiles()
        record.refresh_from_db()

        self.assertFalse(record.active)
        self.assertNotIn(profile, list(self.laptop2.installed.all()))

        # Reset profile to installed status and test that profiles that have already expired are removed properly
        self.laptop2.installed.add(profile)
        record.expires = past_date
        record.active = True
        record.save()
        views.handle_expired_profiles()
        record.refresh_from_db()

        self.assertFalse(record.active)
        self.assertNotIn(profile, list(self.laptop2.installed.all()))

    def test_removal_password(self):
        # Users should not be allowed access by default
        self.assertOk(self.client.get(reverse("mdm:password")), 403)

        permission = Permission.objects.get(codename="view_removal_password")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:password")))

    def test_remove_profile(self):
        self.setup()
        self.laptop2.mdm_enrolled = True
        self.laptop.mdm_enrolled = True

        path = os.path.join(settings.MEDIA_ROOT, 'profiles', 'Test.json')
        with open(path, 'w') as profile:
            profile.write(json.dumps({'data': {'version': 1}}))

        config = models.ConfigurationProfile.objects.get(pk=1)
        config2 = models.ConfigurationProfile.objects.get(pk=2)
        config3 = models.ConfigurationProfile.objects.create(name="Third Test", profile=path)
        config4 = models.ConfigurationProfile.objects.create(name="Fourth Test", profile=path)
        self.laptop.installed.add(config3)
        self.laptop.pending.add(config2)
        self.laptop.pending.add(config4)
        self.laptop2.pending.add(config3)
        self.laptop2.installed.add(config4)

        record1 = models.InstallationRecord.objects.create(profile=config2, device=self.laptop2, version="1",
                                                           active=True)
        record2 = models.InstallationRecord.objects.create(profile=config3, device=self.laptop, version="1",
                                                           active=True)
        record3 = models.InstallationRecord.objects.create(profile=config4, device=self.laptop2, version="1",
                                                           active=True)
        record4 = models.InstallationRecord.objects.create(profile=config4, device=self.laptop, version="RM",
                                                           active=True)

        # Users should not be allowed access by default
        self.assertOk(self.client.get(reverse("mdm:delete", args=[3])), 403)
        self.assertOk(self.client.get(reverse("mdm:disassociate", args=[2, 2])), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:delete", args=[3])))
        self.assertOk(self.client.get(reverse("mdm:disassociate", args=[2, 2])))

        # Check that if profile is pending on any devices and is not installed on any others it is cancelled and deleted
        self.assertRedirects(self.client.get(reverse("mdm:delete", args=[1])), reverse("mdm:list"))
        self.assertNotIn(config, list(self.laptop2.pending.all()))
        self.assertFalse(models.ConfigurationProfile.objects.filter(pk=1).exists())

        # Test that we get the form back on invalid data (must select an option)
        empty_data = {
            'options': '',
            'save': 'Continue'
        }
        self.assertOk(self.client.post(reverse("mdm:delete", args=[2]), empty_data))

        # Test deleting profiles (automatic) - Note: Profile will not be deleted now if this option is selected
        auto_data = {
            'options': "auto",
            'save': 'Continue'
        }
        self.assertRedirects(self.client.post(reverse("mdm:delete", args=[2]), auto_data), reverse("mdm:list"))
        self.assertIn(config2, list(self.laptop2.pending.all()))
        self.assertNotIn(config2, list(self.laptop2.installed.all()))
        record1.refresh_from_db()
        self.assertEqual(record1.version, "RM")

        # Test deleting profile (manual)
        manual_data = {
            'options': "manual",
            'save': 'Continue'
        }
        self.assertRedirects(self.client.post(reverse("mdm:delete", args=[3]), manual_data), reverse("mdm:list"))
        self.assertFalse(models.ConfigurationProfile.objects.filter(pk=config3.pk).exists())
        self.assertFalse(models.InstallationRecord.objects.filter(pk=record2.pk).exists())

        # Test unlinking profile from device (automatic)
        self.laptop2.pending.remove(config2)
        self.laptop2.installed.add(config2)
        record1.version = "1"
        record1.save()

        self.assertRedirects(self.client.post(reverse("mdm:disassociate", args=[2, 2]), auto_data), reverse("mdm:list"))
        self.assertIn(config2, list(self.laptop2.pending.all()))
        self.assertNotIn(config2, list(self.laptop2.installed.all()))
        record1.refresh_from_db()
        self.assertEqual(record1.version, "RM")

        # Test unlinking profile from device (manual)
        self.assertRedirects(self.client.post(reverse("mdm:disassociate", args=[2, 4]), manual_data),
                             reverse("mdm:list"))
        self.assertTrue(models.ConfigurationProfile.objects.filter(pk=config4.pk).exists())
        self.assertNotIn(config4, self.laptop2.installed.all())
        record3.refresh_from_db()
        self.assertFalse(record3.active)

        # Test cancel pending profile
        self.assertRedirects(self.client.get(reverse("mdm:disassociate", args=[1, 4])), reverse("mdm:list"))
        self.assertTrue(models.ConfigurationProfile.objects.filter(pk=config4.pk).exists())
        self.assertNotIn(config4, self.laptop.pending.all())

        # Test cancel pending removal
        self.laptop.pending.add(config4)
        self.assertRedirects(self.client.get(reverse("mdm:disassociate", args=[1, 4])), reverse("mdm:list"))
        self.assertIn(config4, self.laptop.installed.all())
        self.assertNotIn(config4, self.laptop.pending.all())
        record4.refresh_from_db()
        self.assertEqual(record4.version, '1')

        os.remove(path)

        # Test response for profile not linked to device
        self.assertOk(self.client.get(reverse("mdm:disassociate", args=[1, 2])), 404)

    def test_view_app(self):
        self.setup()

        # By default, the user should not have permission to view app details
        self.assertOk(self.client.get(reverse("mdm:app-detail", args=[1])), 403)

        permission = Permission.objects.get(codename="view_apps")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:app-detail", args=[1])))

    def test_app_list(self):
        # By default, user should not have permission to view the app list
        self.assertOk(self.client.get(reverse("mdm:app-list")), 403)

        permission = Permission.objects.get(codename="view_apps")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:app-list")))

    def test_add_app(self):
        # By default, user should not have permission to add an app
        self.assertOk(self.client.get(reverse("mdm:add-app")), 403)

        permission = Permission.objects.get(codename="add_apps")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:add-app")))

        request_data = {
            "name": "New Application",
            "developer": "",
            "version": "",
            "developer_website": "",
            "save": "Submit"
        }

        valid_data = {
            "name": "Another New Application",
            "identifier": "next-app",
            "developer": "",
            "version": "",
            "description": "",
            "developer_website": "",
            "save": "Submit"
        }

        self.assertRedirects(self.client.post(reverse("mdm:add-app"), request_data), reverse("home"))

        self.assertTrue(models.MacOSApp.objects.filter(name="New Application").exists())

        # If user has manage permissions, enable more options and redirect to app list
        permission = Permission.objects.get(codename="manage_apps")
        self.user.user_permissions.add(permission)

        # Will need view_apps permission for redirect
        permission = Permission.objects.get(codename="view_apps")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("mdm:add-app"), valid_data), reverse("mdm:apps"))

        self.assertTrue(models.MacOSApp.objects.filter(name="Another New Application").exists())

    def test_app_info(self):
        self.setup()

        app = models.MacOSApp.objects.get(name="Test Application")

        # By default, user should not have permission to manage the app info
        self.assertOk(self.client.get(reverse("mdm:edit-app", args=[app.pk])), 403)

        permission = Permission.objects.get(codename="manage_apps")
        self.user.user_permissions.add(permission)

        # Will need view_apps for redirect
        permission = Permission.objects.get(codename="view_apps")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:edit-app", args=[app.pk])))

        valid_data = {
            "name": "Updated Application",
            "identifier": "test",
            "version": "2.0.0",
            "developer": "Lifts and Locks Inc.",
            "description": "Updated app description",
            "developer_website": "https://lifts-n-locks.com",
            "requires_license": True,
            "save": "Save Changes"
        }

        self.assertRedirects(self.client.post(reverse("mdm:edit-app", args=[app.pk]), valid_data), reverse("mdm:apps"))
        app.refresh_from_db()
        self.assertEqual(app.name, "Updated Application")

        # Check that the merge button redirects to the proper page
        merge_data = {
            "name": "Updated Application",
            "identifier": "",
            "version": "2.0.0",
            "developer": "Lifts and Locks LLC.",
            "description": "Updated app description",
            "developer_website": "https://lifts-n-locks.com",
            "requires_license": True,
            "save": "Merge"
        }

        self.assertRedirects(self.client.post(reverse("mdm:edit-app", args=[app.pk]), merge_data),
                             reverse("mdm:merge-app", args=[app.pk]))

        # Check that we can request to delete the application
        delete_data = {
            "name": "Updated Application",
            "identifier": "test",
            "version": "2.0.0",
            "developer": "Lifts and Locks LLC.",
            "description": "Updated app description",
            "developer_website": "https://lifts-n-locks.com",
            "requires_license": True,
            "save": "Delete"
        }

        # Prevent redirect on redirect
        self.laptop2.apps_installed.add(app)

        self.assertRedirects(self.client.post(reverse("mdm:edit-app", args=[app.pk]), delete_data),
                             reverse("mdm:remove-app", args=[app.pk]))

    def test_merge_apps(self):
        self.setup()

        # Attempt to merge "Another Application" into "Test Application"
        app = models.MacOSApp.objects.get(name="Test Application")

        app2 = models.MacOSApp.objects.get(name="Another Application")
        app2.version = "1.0.1"
        app2.developer = "Da Webmaster"
        app2.developer_website = "https://wpi.edu"
        app2.description = "It's a computer program"
        app2.save()

        # By default, users should not have permission to merge apps
        self.assertOk(self.client.get(reverse("mdm:merge-app", args=[app2.pk])), 403)

        permission = Permission.objects.get(codename="manage_apps")
        self.user.user_permissions.add(permission)

        # Will need view_apps permission for redirect
        permission = Permission.objects.get(codename="view_apps")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:merge-app", args=[app2.pk])))

        valid_data = {
            "options": str(app.pk),
            "save": "Merge"
        }

        self.assertRedirects(self.client.post(reverse("mdm:merge-app", args=[app2.pk]), valid_data),
                             reverse("mdm:apps"))

        app.refresh_from_db()
        app2.refresh_from_db()

        self.assertEqual(app.version, "1.0.1")
        self.assertEqual(app.developer, "Da Webmaster")
        self.assertEqual(app.developer_website, "https://wpi.edu")
        self.assertEqual(app.description, "It's a computer program")
        self.assertEqual(app2.merged_into, app)

        # Attributes currently aren't changed if they already exist
        app3 = models.MacOSApp.objects.create(name="A third app", description="Test description", version="20.22")

        self.assertRedirects(self.client.post(reverse("mdm:merge-app", args=[app3.pk]), valid_data),
                             reverse("mdm:apps"))

        self.assertEqual(app.description, "It's a computer program")

    def test_list_apps(self):
        self.setup()

        self.laptop2.mdm_enrolled = True
        self.laptop2.save()

        app = models.MacOSApp.objects.get(name="Test Application")
        self.laptop2.apps_installed.add(app)
        self.laptop2.apps_pending.add(app)
        self.laptop2.apps_remove.add(app)

        # By default, should not have permission to see apps
        self.assertOk(self.client.get(reverse("mdm:apps")), 403)

        permission = Permission.objects.get(codename="view_apps")
        self.user.user_permissions.add(permission)

        # List all apps
        self.assertOk(self.client.get(reverse("mdm:apps")))

        # List apps assigned by device (should require manage permissions)
        self.assertOk(self.client.get(reverse("mdm:device-apps", args=[self.laptop2.pk])), 403)

        # List devices using a specific app (should require manage permissions)
        self.assertOk(self.client.get(reverse("mdm:app-devices", args=[app.pk])), 403)

        permission = Permission.objects.get(codename="manage_apps")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:device-apps", args=[self.laptop2.pk])))
        self.assertOk(self.client.get(reverse("mdm:app-devices", args=[app.pk])))

    def test_link_apps(self):
        self.setup()

        self.laptop2.mdm_enrolled = True
        self.laptop2.save()

        app = models.MacOSApp.objects.get(name="Test Application")
        app.installed.add(self.laptop2)

        app2 = models.MacOSApp.objects.get(name="Another Application")
        app2.installed.add(self.laptop2)

        # By default, user should not be allowed to deploy apps
        self.assertOk(self.client.get(reverse("mdm:assign-apps", args=[self.laptop2.pk])), 403)

        permission = Permission.objects.get(codename="manage_apps")
        self.user.user_permissions.add(permission)

        # Check that we get an error message when there are no eligible apps to list
        self.assertContains(self.client.get(reverse("mdm:assign-apps", args=[self.laptop2.pk])), "Hmm...")

        app.installed.remove(self.laptop2)

        self.assertOk(self.client.get(reverse("mdm:assign-apps", args=[self.laptop2.pk])))

        apps = {
            'options': [str(app.pk)],
            'save': 'Assign'
        }

        devices = {
            'options': [str(self.laptop2)],
            'save': 'Assign'
        }

        # Assign app(s) to device
        self.assertContains(self.client.post(reverse("mdm:assign-apps", args=[self.laptop2.pk]), apps), "Success!")
        self.assertIn(app, self.laptop2.apps_pending.all())

        self.laptop2.apps_pending.remove(app)
        self.laptop2.save()

        # Link device(s) with app
        self.assertContains(self.client.post(reverse("mdm:app-link-devices", args=[app.pk]), devices), "Success!")
        self.assertIn(app, self.laptop2.apps_pending.all())

    def test_remove_app(self):
        self.setup()
        self.laptop2.mdm_enrolled = True
        self.laptop2.save()

        app = models.MacOSApp.objects.get(name="Test Application")
        app2 = models.MacOSApp.objects.get(name="Another Application")

        self.laptop2.apps_pending.add(app2)

        # By default, user should not have permission to trigger an uninstall or remove the app altogether
        self.assertOk(self.client.get(reverse("mdm:uninstall-app", args=[self.laptop2.pk, app.pk])), 403)
        self.assertOk(self.client.get(reverse("mdm:remove-app", args=[app.pk])), 403)

        permission = Permission.objects.get(codename="manage_apps")
        self.user.user_permissions.add(permission)

        # Will need view_apps permission for redirects
        permission = Permission.objects.get(codename="view_apps")
        self.user.user_permissions.add(permission)

        # Check that we can cancel pending assignments or removals on get
        self.assertRedirects(self.client.get(reverse("mdm:uninstall-app", args=[self.laptop2.pk, app2.pk])),
                             reverse("mdm:apps"))

        self.assertNotIn(app2, self.laptop2.apps_pending.all())

        self.laptop2.apps_remove.add(app2)

        self.assertRedirects(self.client.get(reverse("mdm:uninstall-app", args=[self.laptop2.pk, app2.pk])),
                             reverse("mdm:apps"))

        self.assertNotIn(app2, self.laptop2.apps_remove.all())

        # Check that we can remove app right away if not installed
        self.assertRedirects(self.client.get(reverse("mdm:remove-app", args=[app.pk])), reverse("mdm:apps"))

        app = models.MacOSApp.objects.create(name="Another New Application", identifier="thing")
        self.laptop2.apps_installed.add(app)
        models.InstallationRecord.objects.create(app=app, device=self.laptop2)

        self.assertOk(self.client.get(reverse("mdm:remove-app", args=[app.pk])))

        # Load form if options need to be presented
        self.assertOk(self.client.get(reverse("mdm:uninstall-app", args=[self.laptop2.pk, app.pk])))

        unlink_app_manual = {
            "save": 'Submit'
        }

        # Remove laptop from app record
        self.assertRedirects(self.client.post(reverse("mdm:uninstall-app", args=[self.laptop2.pk, app.pk]),
                                              unlink_app_manual), reverse("mdm:apps"))
        self.laptop2.refresh_from_db()
        self.assertNotIn(app, self.laptop2.apps_installed.all())
        self.assertFalse(models.InstallationRecord.objects.filter(device=self.laptop2, app=app, active=True).exists())

        # Delete app from library
        self.laptop2.apps_installed.add(app)
        self.laptop.apps_pending.add(app)

        models.InstallationRecord.objects.create(device=self.laptop2, app=app)

        self.assertRedirects(self.client.post(reverse("mdm:remove-app", args=[app.pk]), unlink_app_manual),
                             reverse("mdm:apps"))
        self.assertFalse(models.InstallationRecord.objects.filter(app=app, device=self.laptop2, active=True).exists())
        self.assertFalse(models.MacOSApp.objects.filter(pk=app.pk).exists())

    def test_logs(self):
        self.setup()

        self.laptop2.mdm_enrolled = True
        self.laptop2.save()

        profile = models.ConfigurationProfile.objects.get(name="Test")
        app = models.MacOSApp.objects.get(name="Test Application")

        models.InstallationRecord.objects.create(device=self.laptop2, profile=profile, active=False,
                                                 expires=timezone.now())
        models.InstallationRecord.objects.create(device=self.laptop2, profile=profile)
        models.InstallationRecord.objects.create(device=self.laptop2, app=app)

        # By default, user should not have permission to see the logs
        self.assertOk(self.client.get(reverse("mdm:install-logs")), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:install-logs")))

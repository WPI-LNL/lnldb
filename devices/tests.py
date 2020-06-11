# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from data.tests.util import ViewTestCase
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission
from django.conf import settings
from . import models, forms
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

        permission = Permission.objects.get(codename="view_laptop_details")
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
        response = {
            'oldUserPassword': 'User',
            'oldAdminPassword': 'Admin'
        }
        resp = self.client.post(reverse("laptops:rotate-passwords"), json.dumps(data), content_type='application/json')
        self.assertEqual(resp.content, json.dumps(response))
        laptop = models.Laptop.objects.get(name="Test Laptop")
        self.assertEqual(laptop.user_password, 'NewPass')
        self.assertEqual(laptop.admin_password, 'OtherNewPass')


class MDMTestCase(ViewTestCase):
    def setup(self):
        # Note: These API keys are not real
        self.api_key = "b8f6F0846f8345ca98D011999CcfA6ad"
        self.api_key2 = "Bd00881aA9524ec387f597B5d7D594d6"
        laptop = models.Laptop.objects.create(
            name="Test Laptop",
            api_key_hash="e7b0371cdbf48372368a67c188bbce0f57fb8da970a60433a6e2c127da9bea9c",
            user_password="User",
            admin_password="Admin",
            retired=False,
            mdm_enrolled=False
        )
        laptop2 = models.Laptop.objects.create(
            name="New Laptop",
            api_key_hash="7f838e357d24dad635d1203094bb2b163af8b0cfd424c1d47106f330fd5a171b",
            user_password="User",
            admin_password="Admin",
            serial="123ABC456DEF78",
            retired=False,
            mdm_enrolled=False
        )

        laptop.save()
        laptop2.save()

    def test_mdm_list(self):
        self.setup()
        # User should not have permission by default
        self.assertEqual(self.client.get(reverse("mdm:list")).status_code, 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertEqual(self.client.get(reverse("mdm:list")).status_code, 200)

    def test_install_client(self):
        # User should not have permission by default
        self.assertOk(self.client.get(reverse("mdm:install-client")), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:install-client")))

        data = {
            'save': 'Agree'
        }

        # Downloads installer
        self.assertOk(self.client.post(reverse("mdm:install-client"), data))

    def test_mdm_enroll(self):
        self.setup()

        # GET request should not be allowed
        self.assertEqual(self.client.get(reverse("mdm:start-enrollment")).status_code, 405)

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
        response = {
            'next': '/mdm/enrollment/1/'
        }
        # Returns 0 when tokens do not match (attempting to load this url would result in an error)
        invalid_response = {
            'next': '/mdm/enrollment/0/'
        }
        resp = self.client.post(reverse("mdm:start-enrollment"), json.dumps(data), content_type="application/json")
        invalid_resp = self.client.post(reverse("mdm:start-enrollment"), json.dumps(invalid_data),
                                        content_type="application/json")
        self.assertEqual(resp.content, json.dumps(response))
        self.assertEqual(invalid_resp.content, json.dumps(invalid_response))
        laptop = models.Laptop.objects.all().get(name="Test Laptop")
        self.assertEqual(laptop.serial, 'ABCD1234EFG567')
        self.assertEqual(laptop.last_ip, '192.168.1.2')

        # Example with new computer
        data = {
            'token': settings.MDM_TOKEN,
            'hostname': 'New-Computer',
            'APIKey': 'Ce11662bB9421fD378e967B4d7E624e6',
            'serial': '987654321CBA',
            'networkIP': '192.168.1.3'
        }
        response = {
            'next': '/mdm/enrollment/3/'
        }
        resp = self.client.post(reverse("mdm:start-enrollment"), json.dumps(data), content_type="application/json")
        self.assertEqual(resp.content, json.dumps(response))
        laptop = models.Laptop.objects.all().get(name="New-Computer")
        self.assertEqual(laptop.serial, '987654321CBA')
        self.assertEqual(laptop.last_ip, '192.168.1.3')

    def test_complete_enrollment(self):
        self.setup()
        # User should not have permission by default
        self.assertEqual(self.client.get(reverse("mdm:enroll", args=[2])).status_code, 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertEqual(self.client.get(reverse("mdm:enroll", args=[2])).status_code, 200)

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

    def test_remove_device(self):
        self.setup()
        laptop2 = models.Laptop.objects.get(name="New Laptop")
        laptop2.serial = 'DISCONNECTED'  # The MDM resets the serial no. when the client is uninstalled from the device
        laptop2.mdm_enrolled = True
        laptop2.save()

        # User should not be allowed to access by default
        self.assertOk(self.client.get(reverse("mdm:remove", args=[laptop2.pk])), 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("mdm:remove", args=[laptop2.pk])))

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

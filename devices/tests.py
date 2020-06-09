# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from data.tests.util import ViewTestCase
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission
from . import models
import json, logging


logging.disable(logging.WARNING)


class LaptopTestCase(ViewTestCase):
    def setup(self):
        self.api_key = "b8f6F0846f8345ca98D011999CcfA6ad"
        laptop = models.Laptop.objects.create(name="Test Laptop",
                                              api_key_hash="e7b0371cdbf48372368a67c188bbce0f57fb8da970a60433a6e2c127da9bea9c",
                                              user_password="User", admin_password="Admin", retired=False)
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
        laptop = models.Laptop.objects.create(name="Test Laptop",
                                              api_key_hash="e7b0371cdbf48372368a67c188bbce0f57fb8da970a60433a6e2c127da9bea9c",
                                              user_password="User", admin_password="Admin", retired=False,
                                              mdm_enrolled=False)
        laptop2 = models.Laptop.objects.create(name="New Laptop",
                                               api_key_hash="7f838e357d24dad635d1203094bb2b163af8b0cfd424c1d47106f330fd5a171b",
                                               user_password="User", admin_password="Admin",
                                               serial="123ABC456DEF78", retired=False, mdm_enrolled=False)
        laptop.save()
        laptop2.save()

    def test_mdm_list(self):
        self.setup()
        # User should not have permission by default
        self.assertEqual(self.client.get(reverse("mdm:list")).status_code, 403)

        permission = Permission.objects.get(codename="manage_mdm")
        self.user.user_permissions.add(permission)

        self.assertEqual(self.client.get(reverse("mdm:list")).status_code, 200)

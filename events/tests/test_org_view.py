from django.urls import reverse
from django.test import TestCase
from django.contrib.auth.models import Permission

from .. import models
from .generators import FundFactory, OrgFactory, UserFactory
from data.tests.util import ViewTestCase
import logging


logging.disable(logging.WARNING)


class OrgViewTest(ViewTestCase):
    def setup(self):
        self.o1 = OrgFactory.create(name="ababab")

    def test_list(self):
        self.setup()

        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:list")), 403)

        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        response = self.client.get(reverse("orgs:list"))
        self.assertContains(response, self.o1.name)

    def test_detail(self):
        self.setup()

        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:detail", args=[self.o1.pk])), 403)

        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        response = self.client.get(reverse("orgs:detail", args=[self.o1.pk]))
        self.assertContains(response, self.o1.name)

    def test_add_org(self):
        self.setup()

        user = UserFactory.create(password='123')
        self.client.login(username=user.username, password='123')

        self.assertOk(self.client.get(reverse("orgs:add")))

        self.assertOk(self.client.post(reverse("orgs:add")))
        # ie. with invalid data, it still reports the errors back with a valid page.

        sample_data = {'name': "SAMPLE",
                       "user_in_charge": user.pk,
                       "phone": "(800) 123 4567",
                       'exec_email': 'lnl-w@wpi.edu'}
        self.assertRedirects(self.client.post(reverse("orgs:add"), sample_data), reverse("orgs:detail", args=[2]))
        # ie. it is valid and redirects to the detail page

        self.assertTrue(models.Organization.objects.filter(**sample_data).exists())
        # successfully created it

    def test_edit_org(self):
        self.setup()

        user = UserFactory.create(password='123')
        self.client.login(username=user.username, password='123')

        self.assertOk(self.client.get(reverse("orgs:edit", args=[self.o1.pk])))

        self.assertOk(self.client.post(reverse("orgs:edit", args=[self.o1.pk])))
        # ie. with invalid data, it still reports the errors back with a valid page.

        sample_data = {'name': "SAMPLE",
                       "user_in_charge": user.pk,
                       "phone": "(800) 123 4567",
                       'exec_email': 'lnl-w@wpi.edu'}
        self.assertRedirects(self.client.post(reverse("orgs:edit", args=[self.o1.pk]), sample_data),
                             reverse("orgs:detail", args=[self.o1.pk]))
        # ie. it is valid and redirects to the detail page

        self.assertTrue(models.Organization.objects.filter(pk=self.o1.pk, **sample_data).exists())
        # successfully edited it

    def test_verify(self):
        self.setup()

        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:verify", args=[self.o1.pk])), 403)

        permission = Permission.objects.get(codename="create_verifications")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("orgs:verify", args=[self.o1.pk])))
        # TODO: make a full form test for this.

    def test_org_mkxfer(self):
        self.setup()

        # By default, should not have permission
        self.assertOk(self.client.get(reverse("my:org-transfer", args=[self.o1.pk])), 403)

        permission = Permission.objects.get(codename="transfer_org_ownership")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("my:org-transfer", args=[self.o1.pk])))

        self.o1.associated_users.add(self.user)
        valid_data = {
            "new_user_in_charge": self.user.pk,
            "save": "Submit Transfer"
        }

        self.assertRedirects(self.client.post(reverse("my:org-transfer", args=[self.o1.pk]), valid_data),
                             reverse("orgs:detail", args=[self.o1.pk]))


class FundViewTest(TestCase):
    sample_form = {
        'name': "Foo",
        'fund': "123",
        'organization': "456",
        'account': "789",
    }

    def setUp(self):
        self.user = UserFactory.create(password='123')
        self.o1 = OrgFactory.create(name="ababab")
        self.fund = FundFactory.create()
        self.client.login(username=self.user.username, password='123')

    def test_add_form(self):
        response = self.client.get(reverse("orgs:fundadd", args=(self.o1.pk,)))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("orgs:fundadd", args=(self.o1.pk,)))
        self.assertEqual(response.status_code, 200)  # redisplays form w/ errors

        response = self.client.post(reverse("orgs:fundadd", args=(self.o1.pk,)), data=self.sample_form)
        self.assertEqual(response.status_code, 302)  # redirects to org page

        fund = models.Fund.objects.get(**self.sample_form)
        self.assertTrue(self.o1 in fund.orgfunds.all())

    def test_add_raw_form(self):
        response = self.client.get(reverse("orgs:fundaddraw"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("orgs:fundaddraw"))
        self.assertEqual(response.status_code, 200)  # redisplays form w/ errors

        response = self.client.post(reverse("orgs:fundaddraw"), data=self.sample_form)
        self.assertEqual(response.status_code, 302)  # redirects to success page

        models.Fund.objects.get(**self.sample_form)

    def test_blank_edit_form(self):
        response = self.client.get(reverse("orgs:fundedit", args=(self.fund.pk,)))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("orgs:fundedit", args=(self.fund.pk,)))
        self.assertEqual(response.status_code, 200)  # redisplays form w/ errors

        response = self.client.post(reverse("orgs:fundedit", args=(self.fund.pk,)), data=self.sample_form)
        self.assertEqual(response.status_code, 302)  # redirects to success/another page

        models.Fund.objects.get(**self.sample_form)

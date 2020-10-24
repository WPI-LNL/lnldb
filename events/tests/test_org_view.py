from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import Permission

from .. import models
from .generators import FundFactory, OrgFactory
from data.tests.util import ViewTestCase
import logging


logging.disable(logging.WARNING)


class OrgViewTest(ViewTestCase):
    def setUp(self):
        super(OrgViewTest, self).setUp()
        self.o1 = OrgFactory.create(name="ababab")

    def test_list(self):
        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:list")), 403)

        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        response = self.client.get(reverse("orgs:list"))
        self.assertContains(response, self.o1.name)

    def test_detail(self):
        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:detail", args=[self.o1.pk])), 403)

        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        response = self.client.get(reverse("orgs:detail", args=[self.o1.pk]))
        self.assertContains(response, self.o1.name)

    def test_add_org(self):
        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:add")), 403)

        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        # Will need transfer_org_ownership, list_org_members, and edit_org permissions
        permission = Permission.objects.get(codename="transfer_org_ownership")
        self.user.user_permissions.add(permission)

        permission = Permission.objects.get(codename="list_org_members")
        self.user.user_permissions.add(permission)

        permission = Permission.objects.get(codename="edit_org")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("orgs:add")))

        self.assertOk(self.client.post(reverse("orgs:add")))
        # ie. with invalid data, it still reports the errors back with a valid page.

        sample_data = {'name': "SAMPLE",
                       "user_in_charge": str(self.user.pk),
                       "phone": "(800) 123 4567",
                       'exec_email': 'lnl-w@wpi.edu'}
        self.assertRedirects(self.client.post(reverse("orgs:add"), sample_data), reverse("orgs:detail", args=[2]))
        # ie. it is valid and redirects to the detail page

        self.assertTrue(models.Organization.objects.filter(**sample_data).exists())
        # successfully created it

    def test_edit_org(self):
        # Will not have view_org permission by permission
        self.assertOk(self.client.get(reverse("orgs:edit", args=[self.o1.pk])), 403)

        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        # Will need at least edit_org and transfer_org_ownership
        permission = Permission.objects.get(codename="edit_org")
        self.user.user_permissions.add(permission)

        permission = Permission.objects.get(codename="transfer_org_ownership")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("orgs:edit", args=[self.o1.pk])))

        invalid_data = {
            "name": "",
            "user_in_charge": self.user.pk,
            "phone": "(800) 123 4567",
            "exec_email": "",
        }
        self.assertOk(self.client.post(reverse("orgs:edit", args=[self.o1.pk]), invalid_data))
        # ie. with invalid data, it still reports the errors back with a valid page.

        sample_data = {'name': "SAMPLE",
                       "user_in_charge": str(self.user.pk),
                       "phone": "(800) 123 4567",
                       'exec_email': 'lnl-w@wpi.edu'}
        self.assertRedirects(self.client.post(reverse("orgs:edit", args=[self.o1.pk]), sample_data),
                             reverse("orgs:detail", args=[self.o1.pk]))
        # ie. it is valid and redirects to the detail page

        self.assertEqual(models.Organization.objects.filter(pk=self.o1.pk).first().name, "SAMPLE")
        # successfully edited it

    def test_verify(self):
        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:verify", args=[self.o1.pk])), 403)

        permission = Permission.objects.get(codename="create_verifications")
        self.user.user_permissions.add(permission)

        # Will also need view_org permission for redirect
        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("orgs:verify", args=[self.o1.pk])))

        valid_data = {
            "date": timezone.now().date(),
            "verified_by": str(self.user.pk),
            "note": "",
            "save": "Verify"
        }

        self.assertRedirects(self.client.post(reverse("orgs:verify", args=[self.o1.pk]), valid_data),
                             reverse("orgs:detail", args=[self.o1.pk]))

    def test_org_mkxfer(self):
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


class FundViewTest(ViewTestCase):
    sample_form = {
        'name': "Foo",
        'fund': "123",
        'organization': "456",
        'account': "789",
    }

    def setUp(self):
        super(FundViewTest, self).setUp()
        self.o1 = OrgFactory.create(name="ababab")
        self.fund = FundFactory.create()

    def test_add_form(self):
        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:fundadd", args=(self.o1.pk,))), 403)

        permission = Permission.objects.get(codename="add_fund")
        self.user.user_permissions.add(permission)

        # Will also need view_org permission for redirect
        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("orgs:fundadd", args=(self.o1.pk,))))

        self.assertOk(self.client.post(reverse("orgs:fundadd", args=(self.o1.pk,))))

        self.assertRedirects(self.client.post(reverse("orgs:fundadd", args=(self.o1.pk,)), data=self.sample_form),
                             reverse("orgs:detail", args=(self.o1.pk,)))

        fund = models.Fund.objects.get(**self.sample_form)
        self.assertTrue(self.o1 in fund.orgfunds.all())

    def test_add_raw_form(self):
        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:fundaddraw")), 403)

        permission = Permission.objects.get(codename="add_fund")
        self.user.user_permissions.add(permission)

        # Will also need view_org permissions for redirect
        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("orgs:fundaddraw")))

        self.assertOk(self.client.post(reverse("orgs:fundaddraw")))

        self.assertRedirects(self.client.post(reverse("orgs:fundaddraw"), data=self.sample_form), reverse("orgs:list"))

        models.Fund.objects.get(**self.sample_form)

    def test_blank_edit_form(self):
        # Should not have permission by default
        self.assertOk(self.client.get(reverse("orgs:fundedit", args=(self.fund.pk,))), 403)

        permission = Permission.objects.get(codename="change_fund")
        self.user.user_permissions.add(permission)

        # Will also need view_org permission for redirect
        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("orgs:fundedit", args=(self.fund.pk,))))

        self.assertOk(self.client.post(reverse("orgs:fundedit", args=(self.fund.pk,))))
        # redisplays form w/ errors

        self.assertRedirects(self.client.post(reverse("orgs:fundedit", args=(self.fund.pk,)), data=self.sample_form),
                             reverse("orgs:list"))

        models.Fund.objects.get(**self.sample_form)

    def test_fund_edit_external(self):
        self.fund.orgfunds.add(self.o1)

        # By default should not have permission to edit fund
        self.assertOk(self.client.get(reverse("orgs:fundedit_external", args=(self.fund.pk,))), 403)

        self.o1.user_in_charge = self.user
        self.o1.save()

        self.assertOk(self.client.get(reverse("orgs:fundedit_external", args=(self.fund.pk,))))

        valid_data = {
            "name": "LNL Default",
            "notes": "",
            "save": "Save Changes"
        }

        # Will need view_org permission to redirect
        permission = Permission.objects.get(codename="view_org")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.post(reverse("orgs:fundedit_external", args=(self.fund.pk,)), valid_data),
                             reverse("orgs:list"))

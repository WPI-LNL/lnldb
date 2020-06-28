from django import test
from django.urls.base import reverse
from django.contrib.auth.models import Group, Permission
from django.conf import settings
from django.core import management
from django.core.files.uploadedfile import SimpleUploadedFile
from six import StringIO

from data.tests.util import ViewTestCase
from . import ldap, models
import os, logging


class LdapTestCase(test.TestCase):

    def setUp(self):
        # some user who is guaranteed to be on the ldap server. Like our club account.
        self.some_user = models.User.objects.create(username="lnl")
        Group.objects.create(name='Active').user_set.add(self.some_user)

    def test_search(self):
        # test that we get *some* results
        resp = ldap.search_users("l")
        self.assertGreater(len(resp), 0)

    def test_search_or_create(self):
        # test that we get *some* results, and that they are saved as users
        test_query = "a"
        resp = ldap.search_or_create_users(test_query)
        self.assertGreater(len(resp), 0)
        self.assertIsInstance(resp[0], models.User)

    def test_fill(self):
        # if a user is on the ldap server and lacking a name, it will retrieve it
        u = ldap.fill_in_user(self.some_user)
        self.assertNotEquals(u.first_name, "")

    def test_fill_no_overwrite(self):
        # if the user has a first and/or last name, fetching it won't overwrite it.
        self.some_user.first_name = "foo"  # does not match ldap name
        self.some_user.save()

        u = ldap.fill_in_user(self.some_user)
        self.assertEquals(u.first_name, "foo")

    def test_scrape_cmd(self):
        output = StringIO()
        management.call_command("scrape_ldap", stdout=output)
        output = output.getvalue()

        self.assertTrue(output.lower().startswith("1 user"),
                        msg="Ldap scraper returns '%s', expecting 1 user" % output)
        # assert it detects our sole user needing info

        self.some_user.refresh_from_db()
        self.assertNotEquals(self.some_user.first_name, "")
        # assert that it fill in some info and saves it.


class OfficerImgTestCase(test.TestCase):
    def setup(self):
        self.user = models.User.objects.create(username="tester")
        img = SimpleUploadedFile(name="test.jpg", content=b"file data", content_type="image/jpeg")
        self.img = models.OfficerImg.objects.create(officer=self.user, img=img)
        self.img.save()

    def test_officer_img_cleanup(self):
        self.setup()

        models.OfficerImg.objects.get(officer=self.user).delete()

        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, "officers", "tester.jpg")))

    def test_path_and_rename(self):
        self.setup()

        self.assertEqual(models.path_and_rename(self.img, self.img.img.name), "officers/tester.jpg")

        os.remove(os.path.join(settings.MEDIA_ROOT, "officers", "tester.jpg"))


class OfficerImgViewTestCase(ViewTestCase):
    def test_officer_photos(self):
        # Turn off annoying debug messages when testing permission denied
        logging.disable(logging.WARNING)

        # General members should not have access to these pages
        self.assertOk(self.client.get(reverse("accounts:officer-photo", args=[self.user.pk])), 403)

        permission = Permission.objects.get(codename="change_group", name="Change the group membership of a user")
        self.user.user_permissions.add(permission)

        # Not an officer, should redirect
        self.assertOk(self.client.get(reverse("accounts:officer-photo", args=[self.user.pk])), 302)

        officer_group = Group.objects.create(name="Officer")
        self.user.groups.add(officer_group)

        # The other view (for the current user) - behaves almost exactly the same
        self.assertOk(self.client.get(reverse("accounts:photo")))

        # Test with new file
        img = open('static/img/ms_signin_dark.png', 'rb')
        img2 = open('static/img/pdf-lnl-logo.png', 'rb')
        invalid_data = {
            'img': None,
            'save': 'Save Changes'
        }
        valid_data = {
            'img': img,
            'save': 'Save Changes'
        }

        update = {
            'img': img2,
            'save': 'Save Changes'
        }

        remove = {
            'img': img2,
            'save': 'Remove'
        }

        remove_none = {
            'img': None,
            'save': 'Remove'
        }

        # Returns form on invalid entry
        self.assertOk(self.client.post(reverse("accounts:photo"), invalid_data))

        # Redirects to user detail page if remove is clicked and there is no file in the database
        self.assertRedirects(self.client.post(reverse("accounts:photo"), remove_none),
                             reverse("accounts:detail", args=[self.user.pk]))

        # Test with valid data
        self.assertRedirects(self.client.post(reverse("accounts:photo"), valid_data),
                             reverse("accounts:detail", args=[self.user.pk]))

        # Test replacing previous file
        self.assertRedirects(self.client.post(reverse("accounts:photo"), update),
                             reverse("accounts:detail", args=[self.user.pk]))

        # Test removing the file
        self.assertRedirects(self.client.post(reverse("accounts:photo"), remove),
                             reverse("accounts:detail", args=[self.user.pk]))

        # Ensure file has been deleted from server
        self.assertFalse(os.path.exists(os.path.join(settings.MEDIA_ROOT, "officers", "testuser.png")))

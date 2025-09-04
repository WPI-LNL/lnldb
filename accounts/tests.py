from django import test
from django.test.client import RequestFactory
from django.urls.base import reverse
from django.contrib.auth.models import Group, Permission
from django.conf import settings
from django.core import management
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template import Context, Template
from django.utils import timezone
from six import StringIO

from data.tests.util import ViewTestCase
from events.tests.generators import UserFactory, OrgFactory, Event2019Factory
from events.models import EventCCInstance, Category, Service, Location, Building
from helpers.challenges import is_officer
from .templatetags import at_user_linking
from . import ldap, models, lookups
import os, logging


logging.disable(logging.WARNING)


class TemplateTagsTestCase(test.TestCase):
    def setUp(self):
        self.user = UserFactory.create(password="123", username="tnurse18")
        self.user2 = UserFactory.create(password="456")
        self.org = OrgFactory.create(user_in_charge=self.user, name="LNL")

    def test_userlink(self):
        text_with_link = "This is some example text that was written by @tnurse18 some time ago"
        text_without_link = "This is some more example text that was written by no one in particular"
        self.assertEqual(
            at_user_linking.userlink(text_with_link),
            "This is some example text that was written by <a href=\"" +
            reverse("accounts:detail", args=[self.user.pk]) + "\">@tnurse18</a> some time ago"
        )
        self.assertEqual(at_user_linking.userlink(text_without_link), text_without_link)

    def test_mduserlink(self):
        text_with_link = "This is some example text that was written by @tnurse18 some time ago"
        text_without_link = "This is some more example text that was written by no one in particular"
        self.assertEqual(
            at_user_linking.mduserlink(text_with_link),
            "This is some example text that was written by [@tnurse18](" +
            reverse("accounts:detail", args=[self.user.pk]) + ") some time ago"
        )
        self.assertEqual(at_user_linking.mduserlink(text_without_link), text_without_link)

    def test_linkify_join(self):
        context = Context({'result': {'object': self.user}})
        template = Template(
            '{% load linkify_map %}'
            '{{ result.object.orgowner|linkify_join:"orgs:detail" }}'
        )
        rendered = template.render(context)
        self.assertInHTML('<a href="' + reverse("orgs:detail", args=[self.org.pk]) + '">LNL</a>', rendered)


class AccountsTestCase(ViewTestCase):
    def setup(self):
        self.user2 = UserFactory.create(password="123")
        self.associate = Group.objects.create(name="Associate")
        self.active = Group.objects.create(name="Active")
        self.officer = Group.objects.create(name="Officer")
        self.request_factory = RequestFactory()

    def test_user_add_view(self):
        self.setup()
        # By default, shouldn't have permission
        self.assertOk(self.client.get(reverse("accounts:add")), 403)

        change_user = Permission.objects.get(codename="add_user")
        read_user = Permission.objects.get(codename="view_user")  # Needed to view details on redirect
        self.user.user_permissions.add(change_user)
        self.user.user_permissions.add(read_user)

        self.assertOk(self.client.get(reverse("accounts:add")))

        data = {
            'username': 'chiefsupervisor',
            'email': 'chiefsupervisor@wpi.edu',
            'first_name': 'Chief',
            'last_name': 'Supervisor',
            'password1': 'Password.1',
            'password2': 'Password.1',
            'save': 'Save Changes'
        }

        # Password is optional
        no_pass = {
            'username': 'person',
            'email': 'example@wpi.edu',
            'first_name': 'Peter',
            'last_name': 'Erson',
            'password1': '',
            'password2': '',
            'save': 'Save Changes'
        }

        self.assertRedirects(self.client.post(reverse("accounts:add"), data), reverse("accounts:detail",
                                                                                      args=[3]))
        self.assertRedirects(self.client.post(reverse("accounts:add"), no_pass), reverse("accounts:detail",
                                                                                         args=[4]))

    def test_user_update_view(self):
        self.setup()
        # By default, shouldn't have permission
        self.assertOk(self.client.get(reverse("accounts:update", args=[2])), 403)

        change_user = Permission.objects.get(codename="change_user")
        read_user = Permission.objects.get(codename="view_user")  # Needed to view details on redirect
        self.user.user_permissions.add(change_user)
        self.user.user_permissions.add(read_user)

        self.assertOk(self.client.get(reverse("accounts:update", args=[2])))

        new_user = {
            'username': 'example',
            'email': 'example@wpi.edu',
            'first_name': 'Example',
            'last_name': 'User',
            'nickname': '',
            'groups': [],
            'addr': '',
            'save': 'Update Member and Return'
        }

        self.assertRedirects(self.client.post(reverse("accounts:update", args=[2]), new_user),
                             reverse("accounts:detail", args=[2]))

        # Class year should be required if request user and user being edited are LNL members
        self.associate.user_set.add(self.user)
        self.associate.user_set.add(self.user2)

        member_data = {
            'username': 'example',
            'email': 'example@wpi.edu',
            'first_name': 'Example',
            'last_name': 'User',
            'nickname': '',
            'groups': [self.associate.pk],
            'addr': '',
            'wpibox': 123,
            'mdc': 'CALLSGN',
            'phone': '1234567890',
            'class_year': '',
            'student_id': '123456789',
            'away_exp': '',
            'carrier': '',  # Opt out of SMS communications
            'save': 'Update Member and Return'
        }

        self.assertOk(self.client.get(reverse("accounts:update", args=[2])))
        # Should not redirect as class year is required
        self.assertOk(self.client.post(reverse("accounts:update", args=[2]), member_data))

        member_data['class_year'] = '1962'

        self.assertRedirects(self.client.post(reverse("accounts:update", args=[2]), member_data),
                             reverse("accounts:detail", args=[2]))

        # Test with officer group change (this test should be skipped in production)
        change_group = Permission.objects.get(codename="change_membership")
        self.user.user_permissions.add(change_group)

        self.officer.user_set.add(self.user2)
        models.Officer.objects.create(user=self.user2, title="President")
        self.user2.save()

        if settings.SLACK_TOKEN in [None, '']:
            self.assertRedirects(self.client.post(reverse("accounts:update", args=[2]), member_data),
                                 reverse("accounts:detail", args=[2]))
            self.user2.refresh_from_db()
            self.assertFalse(models.Officer.objects.filter(user=self.user2).exists())

    def test_user_detail_view(self):
        self.setup()
        # Should be allowed to view own profile
        self.assertOk(self.client.get(reverse("accounts:detail", args=[1])))

        # Should not be allowed to view user profile without view_user permission
        self.assertOk(self.client.get(reverse("accounts:detail", args=[self.user2.pk])), 403)

        permission = Permission.objects.get(codename="view_user")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("accounts:detail", args=[self.user2.pk])))

        # Same permissions currently apply for accessing member profiles
        # (To require view_member permissions for this as well, you would need to update the Mixin)
        self.associate.user_set.add(self.user2)

        # Make sure user has missing CC report
        event = Event2019Factory.create(event_name="Test Event")
        event.datetime_end = timezone.now() + timezone.timedelta(days=-1)
        category = Category.objects.create(name="Lighting")
        service = Service.objects.create(shortname="L1", longname="Lights", base_cost=10.00, addtl_cost=5.00,
                                         category=category)
        building = Building.objects.create(name="Some Building", shortname="Building")
        location = Location.objects.create(name="Some Location", building=building)

        EventCCInstance.objects.create(event=event, crew_chief=self.user2, category=category, service=service,
                                       setup_location=location)

        self.assertOk(self.client.get(reverse("accounts:detail", args=[self.user2.pk])))

    def test_user_list(self):
        self.setup()
        # Test one and you've pretty much tested them all
        # Should not have permission by default
        self.assertOk(self.client.get(reverse("accounts:officers")), 403)

        permission = Permission.objects.get(codename="view_member")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("accounts:officers")))

    def test_me_direct_view(self):
        self.setup()

        # Will need view_user permission for redirect
        permission = Permission.objects.get(codename="view_user")
        self.user.user_permissions.add(permission)

        self.assertRedirects(self.client.get(reverse("accounts:me")), reverse("accounts:detail", args=[1]))

    def test_login(self):
        # Start logged in and check that it goes to the home page automatically
        self.assertRedirects(self.client.get(reverse("accounts:login")), reverse("home"))

        # Logout and check that it goes to the login page
        self.client.logout()
        self.assertOk(self.client.get(reverse("accounts:login")))

    def test_mdc(self):
        self.setup()

        # By default should not have permission
        self.assertOk(self.client.get(reverse("accounts:mdc")), 403)

        permission = Permission.objects.get(codename="view_member")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("accounts:mdc")))

    def test_mdc_raw(self):
        self.setup()

        # By default should not have permission
        self.assertOk(self.client.get(reverse("accounts:mdc_raw")), 403)

        permission = Permission.objects.get(codename="view_member")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("accounts:mdc_raw")))

    def test_mdc_xpr_raw(self):
        self.setup()

        # By default should not have permission
        self.assertOk(self.client.get(reverse("accounts:mdc_xpr_raw")), 403)

        permission = Permission.objects.get(codename="view_member")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("accounts:mdc_xpr_raw")))

    def test_secretary_dashboard(self):
        self.setup()

        # By default should not have permission
        self.assertOk(self.client.get(reverse("accounts:secretary_dashboard")), 403)

        permission = Permission.objects.get(codename="change_membership")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("accounts:secretary_dashboard")))

        # test that with 3 active users, quorum is 2
        for _ in range(3):
            active_user = UserFactory.create()
            self.active.user_set.add(active_user)
        self.assertContains(self.client.get(reverse("accounts:secretary_dashboard")), "<td>Quorum</td><td>2</td>", html=True)

        # test that with 4 active users, quorum is 3
        active_user = UserFactory.create()
        self.active.user_set.add(active_user)
        self.assertContains(self.client.get(reverse("accounts:secretary_dashboard")), "<td>Quorum</td><td>3</td>", html=True)

        # test that with 5 active users, quorum is 3
        active_user = UserFactory.create()
        self.active.user_set.add(active_user)
        self.assertContains(self.client.get(reverse("accounts:secretary_dashboard")), "<td>Quorum</td><td>3</td>", html=True)


    def test_shame(self):
        self.setup()

        # By default should not have permission
        self.assertOk(self.client.get(reverse("accounts:shame")), 403)

        permission = Permission.objects.get(codename="view_member")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("accounts:shame")))

    def test_password_set_view(self):
        self.setup()

        # Change own password (superuser)
        self.assertOk(self.client.get(reverse("accounts:password", args=[1])))

        data = {
            'new_password1': 'Password.1',
            'new_password2': 'Password.1',
            'save': 'Set Password'
        }

        # Should send to login page on success (rendered as view - status should be 200)
        self.assertOk(self.client.post(reverse("accounts:password", args=[1]), data))

        # Change own password (non-superuser)
        self.user.is_superuser = False

        self.assertOk(self.client.get(reverse("accounts:password", args=[1])))

        # Set own password (non-superuser)
        self.user.password = None
        self.assertOk(self.client.get(reverse("accounts:password", args=[1])))

        # Non-superuser should not be allowed to set password for someone else
        another_user = UserFactory.create(password="789")
        self.assertOk(self.client.get(reverse("accounts:password", args=[another_user.pk])), 403)

    def test_user_preferences(self):
        self.setup()

        # Check that settings load ok
        self.assertOk(self.client.get(reverse("accounts:preferences")))

        # Check that user preferences object exists (if it didn't already)
        self.assertTrue(models.UserPreferences.objects.filter(user=self.user).exists())

        # Check form submissions (including required subscriptions)
        invalid_user_data = {
            'theme': '',
            'cc_add_subscriptions': ['email', 'slack'],
            'cc_report_reminders': 'slack',
            'event_edited_notification_methods': 'email',
            'event_edited_field_subscriptions': [],
            'ignore_user_action': 'on'
        }

        valid_user_data = {
            'theme': 'default',
            'cc_add_subscriptions': ['email', 'slack'],
            'cc_report_reminders': 'slack',
            'event_edited_notification_methods': 'all',
            'event_edited_field_subscriptions': ['event_name'],
            'ignore_user_action': 'on'
        }

        prefs = models.UserPreferences.objects.get(user=self.user)

        self.associate.user_set.add(self.user)

        # Invalid submission
        self.assertOk(self.client.post(reverse("accounts:preferences"), invalid_user_data))

        # Active user valid submission
        self.assertRedirects(self.client.post(reverse("accounts:preferences"), valid_user_data),
                             reverse("accounts:detail", args=[self.user.pk]))

        # Check that all required event edit fields are included
        prefs.refresh_from_db()
        self.assertEqual(
            prefs.event_edited_field_subscriptions,
            ['event_name', 'location', 'datetime_setup_complete', 'datetime_start', 'datetime_end']
        )

        # # Test delete RT token
        # rt_delete_data = {
        #     'theme': 'default',
        #     'cc_add_subscriptions': ['email', 'slack'],
        #     'cc_report_reminders': 'slack',
        #     'event_edited_notification_methods': 'all',
        #     'event_edited_field_subscriptions': ['event_name'],
        #     'ignore_user_action': 'on',
        #     'submit': 'rt-delete'
        # }

        # self.assertRedirects(self.client.post(reverse("accounts:preferences"), rt_delete_data),
        #                      reverse("accounts:preferences"))

        # self.assertIsNone(models.UserPreferences.objects.get(user=self.user).rt_token)

    def test_user_lookup(self):
        self.setup()
        self.officer.user_set.add(self.user)
        request = self.request_factory.get("/", {'term': 'test'})
        request.user = self.user
        lookup = lookups.UserLookup()
        self.assertTrue(lookup.check_auth(request))

        # Test get_query with bogus query
        self.assertEqual(list(lookup.get_query('1234', request, False)), [])

        # Test get_query with valid query
        self.assertIn(self.user, list(lookup.get_query('test user', request, False)))

        # Test format_match with default user
        self.assertEqual(lookup.format_match(self.user), "&nbsp;<strong>[testuser]</strong> <i>(Officer)</i>")

        self.officer.user_set.remove(self.user)
        # Test format_match with non-associated member
        self.assertEqual(lookup.format_match(self.user), "&nbsp;<strong>[testuser]</strong>")
        
        # Test that active members show up before non-active members in the list
        inactive_user = UserFactory.create(username="alphabetically_first", first_name="Adam", last_name="Adamson")
        self.associate.user_set.add(inactive_user)
        active_user = UserFactory.create(username="last_alphabetically", first_name="Alice", last_name="Anderson")
        self.associate.user_set.add(active_user)
        # Before "active_user" becomes active, they should show up second
        self.assertEqual([inactive_user, active_user], list(lookup.get_query("A", request, False)))
        # After "active_user" becomes active, they should jump to the front
        self.associate.user_set.remove(active_user)
        self.active.user_set.add(active_user)
        self.assertEqual([active_user, inactive_user], list(lookup.get_query("A", request, False)))

    def test_specific_lookups(self):
        self.setup()
        self.officer.user_set.add(self.user)
        request = self.request_factory.get("/", {'term': 'test'})
        request.user = self.user
        officer_lookup = lookups.OfficerLookup()
        member_lookup = lookups.MemberLookup()
        assoc_lookup = lookups.AssocMemberLookup()

        # Check auth
        self.assertTrue(officer_lookup.check_auth(request))
        self.assertTrue(member_lookup.check_auth(request))
        self.assertTrue(assoc_lookup.check_auth(request))

        # Test get_query
        self.assertIn(self.user, list(officer_lookup.get_query('test user', request)))
        self.assertIn(self.user, list(member_lookup.get_query('test user', request)))
        self.assertIn(self.user, list(assoc_lookup.get_query('test user', request)))

        # Test format_match
        self.assertEqual(officer_lookup.format_match(self.user), "&nbsp;<strong>[testuser]</strong>")
        self.assertEqual(member_lookup.format_match(self.user), "&nbsp;<strong>[testuser]</strong>")
        self.assertEqual(assoc_lookup.format_match(self.user), "&nbsp;<strong>[testuser]</strong>")


class UserTestCase(test.TestCase):
    def setUp(self):
        self.user = models.User.objects.create(username="lnl", first_name="Test", last_name="User")
        self.org = OrgFactory.create(name="LNL")
        self.org2 = OrgFactory.create(name="Test Client")
        self.alumni = Group.objects.create(name="Alumni")
        self.officer = Group.objects.create(name="Officer")
        self.active = Group.objects.create(name="Active")
        self.associate = Group.objects.create(name="Associate")
        self.away = Group.objects.create(name="Away")
        self.inactive = Group.objects.create(name="Inactive")

    def test_user_name(self):
        self.assertEqual(self.user.name, "Test User")

    def test_group_str(self):
        self.assertEqual(self.user.group_str, "Unclassified")
        self.alumni.user_set.add(self.user)
        self.officer.user_set.add(self.user)
        self.active.user_set.add(self.user)
        self.associate.user_set.add(self.user)
        self.away.user_set.add(self.user)
        self.inactive.user_set.add(self.user)

        result = self.user.group_str.split()

        self.assertIn("Alum", result)
        self.assertIn("Officer", result)
        self.officer.user_set.remove(self.user)
        result = self.user.group_str.split()
        self.assertIn("Active", result)
        self.active.user_set.remove(self.user)
        result = self.user.group_str.split()
        self.assertIn("Associate", result)
        self.associate.user_set.remove(self.user)
        result = self.user.group_str.split()
        self.assertIn("Away", result)
        self.away.user_set.remove(self.user)
        result = self.user.group_str.split()
        self.assertIn("Inactive", result)

    def test_owns(self):
        self.org.user_in_charge = self.user
        self.org.save()
        self.assertIn(str(self.org), self.user.owns)

    def test_orgs(self):
        self.org.associated_users.add(self.user)
        self.assertIn(str(self.org), self.user.orgs)

    def test_all_orgs(self):
        self.org2.user_in_charge = self.user
        self.org2.save()
        self.org.associated_users.add(self.user)

        self.assertIn(self.org, list(self.user.all_orgs))
        self.assertIn(self.org2, list(self.user.all_orgs))

    def test_mdc_name(self):
        self.user.first_name = "Test"
        self.user.last_name = "User"
        self.assertEqual(self.user.mdc_name, "USER,TEST")

        # Should truncate longer names
        self.user.first_name = "Tester"
        self.user.last_name = "Persons"
        self.assertEqual(self.user.mdc_name, "PERSONS,TEST")


# class LdapTestCase(test.TestCase):

#     def setUp(self):
#         # some user who is guaranteed to be on the ldap server. Like our club account.
#         self.some_user = models.User.objects.create(username="lnl")
#         Group.objects.create(name='Active').user_set.add(self.some_user)

#     def test_search(self):
#         # test that we get *some* results
#         resp = ldap.search_users("l")
#         self.assertGreater(len(resp), 0)

#     def test_search_or_create(self):
#         # test that we get *some* results, and that they are saved as users
#         test_query = "a"
#         resp = ldap.search_or_create_users(test_query)
#         self.assertGreater(len(resp), 0)
#         self.assertIsInstance(resp[0], models.User)

#     def test_fill(self):
#         # if a user is on the ldap server and lacking a name, it will retrieve it
#         u = ldap.fill_in_user(self.some_user)
#         self.assertNotEquals(u.first_name, "")

#     def test_fill_no_overwrite(self):
#         # if the user has a first and/or last name, fetching it won't overwrite it.
#         self.some_user.first_name = "foo"  # does not match ldap name
#         self.some_user.save()

#         u = ldap.fill_in_user(self.some_user)
#         self.assertEquals(u.first_name, "foo")

#     def test_scrape_cmd(self):
#         output = StringIO()
#         management.call_command("scrape_ldap", stdout=output)
#         output = output.getvalue()

#         self.assertTrue(output.lower().startswith("1 user"),
#                         msg="Ldap scraper returns '%s', expecting 1 user" % output)
#         # assert it detects our sole user needing info

#         self.some_user.refresh_from_db()
#         self.assertNotEquals(self.some_user.first_name, "")
#         # assert that it fill in some info and saves it.


class OfficerImgTestCase(test.TestCase):
    def setup(self):
        self.user = models.User.objects.create(username="tester")
        img = SimpleUploadedFile(name="test.jpg", content=b"file data", content_type="image/jpeg")
        self.img = models.ProfilePhoto.objects.create(officer=self.user, img=img)
        self.img.save()

    def test_officer_img_cleanup(self):
        self.setup()

        models.ProfilePhoto.objects.get(officer=self.user).delete()

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

        permission = Permission.objects.get(codename="change_membership")
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
            'img': '',
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
            'img': '',
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


class HelpersTestCase(ViewTestCase):
    def test_is_officer(self):
        # Test that failing to provide a user results in False
        self.assertFalse(is_officer(None))

        # Test with non-officer
        self.assertFalse(is_officer(self.user))

        # Test with officer
        Group.objects.create(name="Officer").user_set.add(self.user)
        self.assertTrue(is_officer(self.user))

class AdminTestCase(ViewTestCase):
    def test_superuser_permissions(self):
        self.user.is_staff = False
        self.user.user_permissions.add(Permission.objects.get(codename="view_user"))
        self.user.save()

        # normal users can't access any admin pages
        self.assertOk(self.client.get(reverse("admin:accounts_user_changelist")), 302)

        # staff can access the "User" admin page
        self.user.is_staff = True
        self.user.save()
        self.assertOk(self.client.get(reverse("admin:accounts_user_changelist")))

        # but not the "Superuser" page
        self.assertOk(self.client.get(reverse("admin:accounts_superuser_changelist")), 403)
        
        # superusers can access the "Superuser" page
        self.user.is_superuser = True
        self.user.save()
        self.assertOk(self.client.get(reverse("admin:accounts_superuser_changelist")))
        
        # superusers can't change their own superuser status
        self.assertOk(self.client.post(reverse("admin:accounts_superuser_change", args=(self.user.pk,)), {}), 403)
        
        # but they can change other people's
        user2 = UserFactory.create()
        self.assertOk(self.client.post(reverse("admin:accounts_superuser_change", args=(user2.pk,)), {}), 302)

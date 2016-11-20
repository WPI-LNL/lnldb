from django import test
from django.core import management
from six import StringIO

from . import ldap, models


class LdapTestCase(test.TestCase):

    def setUp(self):
        self.some_user = models.User.objects.create(username="lnl")
        # some user who is guaranteed to be on the ldap server. Like our club account.

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

from django.core.urlresolvers import reverse
from django.test import TestCase

from .generators import OrgFactory, UserFactory


# from .. import models


class DeprecationTest(TestCase):
    """
        Testing the redirecting of old urls that may still be in people's bookmarks

        The 'reverse' function should never be used for anything but the target here.
    """
    def setUp(self):
        self.user = UserFactory.create(password='123')
        self.o1 = OrgFactory.create(name="ababab")
        self.client.login(username=self.user.username, password='123')

    def assertRedirects(self, url, expected_url, status_code=301, **kwargs):
        response = self.client.get(url)
        return super(DeprecationTest, self).assertRedirects(response, expected_url, status_code, **kwargs)

    def test_org_edit(self):
        self.assertRedirects("/db/clients/edit/%d/" % self.o1.pk,
                             reverse("orgs:edit", args=(self.o1.pk,)))

from django.test import TestCase
from .generators import EventFactory, UserFactory, OrgFactory
from django.core.urlresolvers import reverse


class OrgViewTest(TestCase):
    def setUp(self):
        self.user = UserFactory.create(password='123')
        self.o1 = OrgFactory.create(name="ababab")
        self.client.login(username=self.user.username, password='123')

    def test_list(self):
        response = self.client.get(reverse("orgs:list"))
        self.assertContains(response, self.o1.name)

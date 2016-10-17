
from django.test import TestCase
from .generators import EventFactory, UserFactory, OrgFactory
from django.core.urlresolvers import reverse


class MyViewTest(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')
        self.org = OrgFactory.create(user_in_charge=self.user)
        self.org2 = OrgFactory.create()
        self.org2.associated_users.add(self.user)
        self.client.login(username=self.user.username, password='123')

    def test_my_wo_blank(self):
        response = self.client.get(reverse("my:workorders"))
        self.assertNotContains(response, self.e.event_name)
        # check that it starts with no events
        
    def test_my_wo_owner(self):
        self.e.org.add(self.org)
        self.e.save()

        response = self.client.get(reverse("my:workorders"))
        self.assertContains(response, self.e.event_name)
        # I am an org owner. I see my org's events

    def test_my_wo_assoc(self):
        self.e.org.add(self.org2)
        self.e.save()

        response = self.client.get(reverse("my:workorders"))
        self.assertContains(response, self.e.event_name)
        # I am an org associate member. I see my org's events.
        
    def test_my_wo_submitted(self):
        self.e.submitted_by = self.user
        self.e.save()

        response = self.client.get(reverse("my:workorders"))
        self.assertContains(response, self.e.event_name)
        # I see the events I submitted


    def test_attach(self):
        # I can get to the attachments page of an event I submitted
        self.e.submitted_by = self.user
        self.e.save()

        response = self.client.get(reverse("my:event-attach", args=[self.e.pk]))
        self.assertContains(response, self.e.event_name)

        # TODO: check attachments functionality more thoroughly

    def test_orgs(self):
        # I see both orgs that I own and orgs I am a member of in My Orgs
        response = self.client.get(reverse("my:workorders"))
        self.assertContains(response, self.org.name)
        self.assertContains(response, self.org2.name)

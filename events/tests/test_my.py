
from django.test import TestCase
from django.core.urlresolvers import reverse
from model_mommy import mommy
from .generators import EventFactory, UserFactory, OrgFactory
from ..models import Event, EventCCInstance


class MyViewTest(TestCase):
    def setUp(self):
        #self.e = EventFactory.create(event_name="Test Event")
        self.e = mommy.make(Event, event_name="foobar", _fill_optional=True)
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
        self.assertEqual(response.status_code, 200)

        # TODO: check attachments functionality more thoroughly

    def test_orgs(self):
        # I see both orgs that I own and orgs I am a member of in My Orgs
        response = self.client.get(reverse("my:orgs"))
        self.assertContains(response, self.org.name)
        self.assertContains(response, self.org2.name)
    
    def test_org_req_blank(self):
        # check that the request form shows a valid page
        response = self.client.get(reverse("my:org-request"))
        self.assertEqual(response.status_code, 200)

    def test_cc_report_blank(self):
        cc = mommy.make(EventCCInstance, event=self.e, crew_chief=self.user)
        response = self.client.get(reverse("my-ccreport", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

    def test_cc_report_error_post(self):
        cc = mommy.make(EventCCInstance, event=self.e, crew_chief=self.user)
        response = self.client.post( reverse("my-ccreport", args=[self.e.pk]),)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(self.e.ccreport_set.filter(crew_chief=self.user)), [])

    def test_cc_report_post(self):
        cc = mommy.make(EventCCInstance, event=self.e, crew_chief=self.user)
        response = self.client.post(
                reverse("my-ccreport", args=[self.e.pk]),
                data={
                    'report': "lorem ipsum something or another", 
                    'crew_chief': self.user.pk}
                )
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.e.ccreport_set.get(crew_chief=self.user))
    

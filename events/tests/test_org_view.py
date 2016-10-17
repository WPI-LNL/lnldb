from django.test import TestCase
from .generators import EventFactory, UserFactory, OrgFactory
from .. import models
from django.core.urlresolvers import reverse


class OrgViewTest(TestCase):
    def setUp(self):
        self.user = UserFactory.create(password='123')
        self.o1 = OrgFactory.create(name="ababab")
        self.client.login(username=self.user.username, password='123')

    def test_list(self):
        response = self.client.get(reverse("orgs:list"))
        self.assertContains(response, self.o1.name)
    
    def test_detail(self):
        response = self.client.get(reverse("orgs:detail", args=(self.o1.pk,)))
        self.assertContains(response, self.o1.name)

    def test_blank_form(self):
        response = self.client.get(reverse("orgs:add"))
        self.assertEqual(response.status_code, 200)
    
    def test_add_org(self):
        response = self.client.post(reverse("orgs:add"))
        self.assertEqual(response.status_code, 200)
        # ie. with invalid data, it still reports the errors back with a valid page.

        sample_data = {'name': "SAMPLE",
                       "user_in_charge":self.user.pk,
                       "phone": "(800) 123 4567"}
        response = self.client.post(reverse("orgs:add"), sample_data)
        self.assertEqual(response.status_code, 302)
        # ie. it is valid and redirects to the detail page
        
        self.assertTrue(models.Organization.objects.filter(**sample_data).exists())
        # successfully created it
    
    def test_edit_form(self):
        response = self.client.get(reverse("orgs:edit", args=(self.o1.pk,)))
        self.assertEqual(response.status_code, 200)
    
    def test_edit_org(self):
        response = self.client.post(reverse("orgs:edit", args=(self.o1.pk,)))
        self.assertEqual(response.status_code, 200)
        # ie. with invalid data, it still reports the errors back with a valid page.

        sample_data = {'name': "SAMPLE",
                       "user_in_charge":self.user.pk,
                       "phone": "(800) 123 4567"}
        response = self.client.post(reverse("orgs:edit", args=(self.o1.pk,)),
                                    sample_data)
        self.assertEqual(response.status_code, 302)
        # ie. it is valid and redirects to the detail page
        
        self.assertTrue(models.Organization.objects.filter(pk=self.o1.pk,**sample_data).exists())
        # successfully edited it

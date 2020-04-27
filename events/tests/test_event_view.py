import datetime
from django.core.urlresolvers import reverse
from django.contrib.auth.models import Permission
from django.test import TestCase
from data.tests.util import ViewTestCase

from .generators import CCReportFactory, EventFactory, UserFactory
from .. import models


class EventBasicViewTest(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')
        self.report = CCReportFactory.create(event=self.e)
        self.client.login(username=self.user.username, password='123')

    def test_pay(self):
        b = self.e.billings.create(date_billed=datetime.date(2000, 1, 1),
                                   amount=3.14)

        # random clicks wont work
        response = self.client.get(reverse('events:bills:pay', args=[self.e.pk, b.pk]))
        self.assertEqual(response.status_code, 405)

        # on success, redirects to event page
        response = self.client.post(reverse('events:bills:pay', args=[self.e.pk, b.pk]))
        self.assertEqual(response.status_code, 302)

        # check it is actually paid
        b.refresh_from_db()
        self.assertIsNotNone(b.date_paid)
        self.assertTrue(self.e.paid)

    def test_detail(self):
        response = self.client.get(reverse('events:detail', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

    def test_edit(self):
        response = self.client.get(reverse('events:edit', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse('events:edit', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post

    def test_cancel(self):
        response = self.client.post(reverse("events:cancel", args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_deny(self):
        response = self.client.post(reverse("events:deny", args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_close(self):
        response = self.client.post(reverse("events:close", args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_reopen(self):
        self.test_close()
        response = self.client.post(reverse("events:reopen", args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_approve(self):
        response = self.client.get(reverse("events:approve", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse("events:approve", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post

    def test_review(self):
        response = self.client.get(reverse("events:review", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Default input should be good
        response = self.client.post(reverse("events:review", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

    def test_ccr_add(self):
        response = self.client.get(reverse("events:reports:new", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Empty (bad) input
        response = self.client.post(reverse("events:reports:new", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_ccr_edit(self):
        response = self.client.get(reverse("events:reports:edit", args=[self.e.pk, self.report.pk]))
        self.assertEqual(response.status_code, 200)

        # Empty (bad) input
        response = self.client.post(reverse("events:reports:edit", args=[self.e.pk, self.report.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_myccr_add(self):
        response = self.client.get(reverse("my:report", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad (empty) input
        response = self.client.post(reverse("my:report", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_bill_add(self):
        response = self.client.get(reverse("events:bills:new", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse("events:bills:new", args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post


class EventListBasicViewTest(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')
        self.client.login(username=self.user.username, password='123')

    def test_public(self):
        response = self.client.get(reverse('cal:list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('cal:api-public'))
        self.assertEqual(response.status_code, 200)

    def test_cal(self):
        response = self.client.get(reverse('cal:feed'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('cal:feed-full'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('cal:feed-light'))
        self.assertEqual(response.status_code, 200)

    def test_incoming(self):
        response = self.client.get(reverse('events:incoming'))
        self.assertEqual(response.status_code, 200)

    def test_upcoming(self):
        response = self.client.get(reverse('events:upcoming'))
        self.assertEqual(response.status_code, 200)

    def test_findchief(self):
        response = self.client.get(reverse('events:findchief'))
        self.assertEqual(response.status_code, 200)

    def test_open(self):
        response = self.client.get(reverse('events:open'))
        self.assertEqual(response.status_code, 200)

    def test_unreviewed(self):
        response = self.client.get(reverse('events:unreviewed'))
        self.assertEqual(response.status_code, 200)

    def test_unbilled(self):
        response = self.client.get(reverse('events:unbilled'))
        self.assertEqual(response.status_code, 200)

    def test_unbilled_semester(self):
        response = self.client.get(reverse('events:unbilled-semester'))
        self.assertEqual(response.status_code, 200)

    def test_paid(self):
        response = self.client.get(reverse('events:paid'))
        self.assertEqual(response.status_code, 200)

    def unpaid(self):
        response = self.client.get(reverse('events:unpaid'))
        self.assertEqual(response.status_code, 200)

    def closed(self):
        response = self.client.get(reverse('events:closed'))
        self.assertEqual(response.status_code, 200)


class WorkshopTests(ViewTestCase):
    def test_workshops_list(self):
        self.assertEqual(self.client.get(reverse("events:workshops:list")).status_code, 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:list")))

    def test_edit_workshop(self):
        workshop = models.Workshop.objects.create(name="Test Workshop", instructors="John, Peter, Janice",
                                                  location="Alden Hall",
                                                  description="Human Resources wants us to go over the Acceptable Use "
                                                              "Policy again.", notes="This sounds boring")
        workshop.save()

        self.assertEqual(self.client.get(reverse("events:workshops:edit", args=[workshop.pk])).status_code, 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:edit", args=[workshop.pk])))

        valid_data = {
            'name': 'Test Event',
            'description': 'A test event',
            'instructors': 'John Doe',
            'location': 'Alden',
            'notes': 'None'
        }
        self.assertRedirects(self.client.post(reverse("events:workshops:edit", args=[1]), valid_data),
                             reverse("events:workshops:list"))

    def test_new_workshop(self):
        self.assertEqual(self.client.get(reverse("events:workshops:add")).status_code, 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:add")))

        valid_data = {
            'name': 'Test Event',
            'description': 'A test event',
            'instructors': 'John Doe',
            'location': 'Alden',
            'notes': 'None'
        }
        self.assertRedirects(self.client.post(reverse("events:workshops:add"), valid_data),
                             reverse("events:workshops:list"))
        workshop = models.Workshop.objects.get(name="Test Event")
        self.assertEqual(workshop.description, "A test event")

    def test_workshop_dates(self):
        workshop = models.Workshop.objects.create(name="Test Workshop", instructors="John, Peter, Janice",
                                                  location="Alden Hall",
                                                  description="Human Resources wants us to go over the Acceptable Use "
                                                              "Policy again.", notes="This sounds boring")
        workshop.save()

        self.assertEqual(self.client.get(reverse("events:workshops:dates", args=[workshop.pk])).status_code, 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:dates", args=[workshop.pk])))

    def test_delete_workshop(self):
        workshop = models.Workshop.objects.create(name="Test Workshop", instructors="John, Peter, Janice",
                                                  location="Alden Hall",
                                                  description="Human Resources wants us to go over the Acceptable Use "
                                                              "Policy again.", notes="This sounds boring")
        workshop.save()

        self.assertOk(self.client.get(reverse("events:workshops:delete", args=[workshop.pk])), 403)

        permission = Permission.objects.get(codename="edit_workshops")
        self.user.user_permissions.add(permission)

        self.assertOk(self.client.get(reverse("events:workshops:delete", args=[workshop.pk])))

        self.assertRedirects(self.client.post(reverse("events:workshops:delete", args=[workshop.pk])),
                             reverse("events:workshops:list"))

        self.assertFalse(models.Workshop.objects.all().filter(name="Test Workshop").exists())

from django.core.urlresolvers import reverse
from django.test import TestCase

from .generators import CCReportFactory, EventFactory, UserFactory


class EventBasicViewTest(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')
        self.report = CCReportFactory.create(event=self.e)
        self.client.login(username=self.user.username, password='123')

    def test_detail(self):
        response = self.client.get(reverse('events:detail', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

    def test_edit(self):
        response = self.client.get(reverse('event-edit', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse('event-edit', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post

    def test_cancel(self):
        response = self.client.post(reverse('event-cancel', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_deny(self):
        response = self.client.post(reverse('event-deny', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_close(self):
        response = self.client.post(reverse('event-close', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_reopen(self):
        self.test_close()
        response = self.client.post(reverse('event-reopen', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_approve(self):
        response = self.client.get(reverse('event-approve', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse('event-approve', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post

    def test_review(self):
        response = self.client.get(reverse('event-review', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Default input should be good
        response = self.client.post(reverse('event-review', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_ccr_add(self):
        response = self.client.get(reverse('event-mkccr', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Empty (bad) input
        response = self.client.post(reverse('event-mkccr', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_ccr_edit(self):
        response = self.client.get(reverse('event-updccr', args=[self.e.pk, self.report.pk]))
        self.assertEqual(response.status_code, 200)

        # Empty (bad) input
        response = self.client.post(reverse('event-updccr', args=[self.e.pk, self.report.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_myccr_add(self):
        response = self.client.get(reverse('my-ccreport', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad (empty) input
        response = self.client.post(reverse('my-ccreport', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_bill_add(self):
        response = self.client.get(reverse('event-mkbilling', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse('event-mkbilling', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post


class EventListBasicViewTest(TestCase):
    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')
        self.client.login(username=self.user.username, password='123')

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

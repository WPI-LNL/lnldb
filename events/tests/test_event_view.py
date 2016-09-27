from django.test import TestCase
from .generators import EventFactory, UserFactory, CCReportFactory
from django.core.urlresolvers import reverse_lazy


class EventBasicViewTest(TestCase):

    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')
        self.report = CCReportFactory.create(event = self.e)
        self.client.login(username=self.user.username, password='123')

    def test_detail(self):
        response = self.client.get(reverse_lazy('events-detail', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

    def test_edit(self):
        response = self.client.get(reverse_lazy('event-edit', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse_lazy('event-edit', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post

    def test_pdf(self):
        response = self.client.get(reverse_lazy('events-pdf', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

    # def test_pdf_bill(self):
    #     response = self.client.get(reverse_lazy('events-pdf-bill', args=[self.e.pk]))
    #     self.assertEqual(response.status_code, 200)
    # # Currently requires a collectstatic. Let's not test until that's fixed

    def test_pdf_multi(self):
        response = self.client.get(reverse_lazy('events-pdf-multi', args=["%s,%s" % (self.e.pk, self.e2.pk)]))
        self.assertEqual(response.status_code, 200)

    def test_cancel(self):
        response = self.client.post(reverse_lazy('event-cancel', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_deny(self):
        response = self.client.post(reverse_lazy('event-deny', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_close(self):
        response = self.client.post(reverse_lazy('event-close', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_reopen(self):
        self.test_close()
        response = self.client.post(reverse_lazy('event-reopen', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_approve(self):
        response = self.client.get(reverse_lazy('event-approve', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse_lazy('event-approve', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post

    def test_review(self):
        response = self.client.get(reverse_lazy('event-review', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Default input should be good
        response = self.client.post(reverse_lazy('event-review', args=[self.e.pk]))
        self.assertEqual(response.status_code, 302)

    def test_ccr_add(self):
        response = self.client.get(reverse_lazy('event-mkccr', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Empty (bad) input
        response = self.client.post(reverse_lazy('event-mkccr', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_ccr_edit(self):
        response = self.client.get(reverse_lazy('event-updccr', args=[self.e.pk, self.report.pk]))
        self.assertEqual(response.status_code, 200)

        # Empty (bad) input
        response = self.client.post(reverse_lazy('event-updccr', args=[self.e.pk, self.report.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_myccr_add(self):
        response = self.client.get(reverse_lazy('my-ccreport', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad (empty) input
        response = self.client.post(reverse_lazy('my-ccreport', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post saved

    def test_bill_add(self):
        response = self.client.get(reverse_lazy('event-mkbilling', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # Bad input
        response = self.client.post(reverse_lazy('event-mkbilling', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

        # later: test post

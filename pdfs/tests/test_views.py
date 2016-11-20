from django.core.urlresolvers import reverse
from django.test import TestCase

from events.tests.generators import EventFactory, UserFactory


class PdfViewTest(TestCase):
    """
    The simplest cases. Just measures if the pdf generators return successfully.
    """

    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')
        self.client.login(username=self.user.username, password='123')

    def test_pdf(self):
        response = self.client.get(reverse('events-pdf', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)

    def test_pdf_bill(self):
        response = self.client.get(reverse('events-pdf-bill', args=[self.e.pk]))
        self.assertEqual(response.status_code, 200)
        self.e2.reviewed = True
        self.e2.save()
        response = self.client.get(reverse('events-pdf-bill', args=[self.e2.pk]))
        self.assertEqual(response.status_code, 200)

    def test_pdf_multi(self):
        response = self.client.get(reverse('events-pdf-multi', args=["%s,%s" % (self.e.pk, self.e2.pk)]))
        self.assertEqual(response.status_code, 200)

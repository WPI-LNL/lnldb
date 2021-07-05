# from ..overlay import make_idt
from django.test import TestCase

from events.tests.generators import EventFactory, UserFactory, Event2019Factory

from ..views import generate_pdfs_standalone


class PdfViewTest(TestCase):
    """
    The simplest cases. Just measures if the pdf generators return successfully.
    """

    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.e3 = Event2019Factory.create(event_name="2019 Test Event")
        self.user = UserFactory.create(password='123')

    def test_pdf_workorder(self):
        # Still returns empty pdf if no event ids are passed in
        self.assertIsNotNone(generate_pdfs_standalone())

        # Tests both old and new events
        self.assertIsNotNone(generate_pdfs_standalone([self.e.pk, self.e3.pk]))

        # Ensure that providing ids does not return an empty pdf
        self.assertNotEqual(generate_pdfs_standalone(), generate_pdfs_standalone([self.e.pk]))

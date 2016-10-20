#from ..overlay import make_idt
from django.test import TestCase
from events.tests.generators import EventFactory, UserFactory
from ..views import generate_pdfs_standalone
from ..overlay import make_idt_single, make_idt_bulk


class PdfViewTest(TestCase):
    """
    The simplest cases. Just measures if the pdf generators return successfully.
    """

    def setUp(self):
        self.e = EventFactory.create(event_name="Test Event")
        self.e2 = EventFactory.create(event_name="Other Test Event")
        self.user = UserFactory.create(password='123')

    def test_pdf_workorder(self):
        pdf = generate_pdfs_standalone([self.e.pk, self.e2.pk])
        self.assertIsNotNone(pdf)

    def test_pdf_idt(self):
        pdf = make_idt_single(self.e, self.user)
        self.assertIsNotNone(pdf)
    
    def test_pdf_bulk_idt(self):
        pdf = make_idt_bulk([self.e, self.e2], self.user)
        self.assertIsNotNone(pdf)

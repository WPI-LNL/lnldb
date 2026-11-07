"""
The Funding Request Report Form: the breakdown and receipts SGA asks for
before it pays a request back.

Four layers, tested from the bottom up:

* **What goes on it.** Every purchase charged to the request's lines that has
  reached Workday, line by line, net of refunds; encumbrances and SGA's own
  payments are not purchases. Each purchase's receipt is its entry's own, or
  another entry's on the same Workday line, or its encumbrance's; receipts are
  numbered in the order the breakdown reaches them.
* **The report**, which warns about everything SGA would refuse or that would
  be missing from the form.
* **The PDF**: the breakdown, then each receipt on its own labelled pages, and
  a page in place of any receipt that cannot be read.
* **The pages**: the report with its request picker, the PDF's permission, and
  the link from a request's own page.
"""
import csv
import datetime
import io
import shutil
import tempfile
from decimal import Decimal

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from pypdf import PdfReader, PdfWriter

from finance.frrf import gather, report_form_pdf
from finance.models import (Encumbrance, FRLineItem, FundingRequest, ParsedTransaction,
                            TransactionStatus)
from finance.reports import as_csv, fr_report_form
from finance.tests.test_revenue_sources import (CacheResetMixin, reimburse, sga_line,
                                                supplier_line)
from finance.tests.test_views import FinanceViewTestCase
from finance.tests.util import category, fund


def jpeg(size=(300, 500)):
    out = io.BytesIO()
    Image.new('RGB', size, 'white').save(out, 'JPEG')
    return out.getvalue()


def png_with_transparency():
    out = io.BytesIO()
    Image.new('RGBA', (400, 200), (0, 0, 0, 0)).save(out, 'PNG')
    return out.getvalue()


def pdf(pages=1, password=None):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if password:
        writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def attach(owner, name, data):
    """ Upload ``data`` as ``owner``'s receipt. """
    owner.receipt_file.save(name, ContentFile(data), save=True)


class FormMixin(object):
    """
    F.27.16, with two lines: Posters, then Concessions. Receipts are stored
    in a folder of their own for each test.
    """

    def setUp(self):
        super(FormMixin, self).setUp()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        storage = override_settings(MEDIA_ROOT=media)
        storage.enable()
        self.addCleanup(storage.disable)
        self.fr = FundingRequest.objects.create(
            name='Film Posters and Concessions', reference='F.27.16', fiscal_year=2027,
            date_approved=datetime.date(2026, 9, 3))
        self.posters = FRLineItem.objects.create(funding_request=self.fr, name='Posters',
                                                 amount_awarded=Decimal('300.00'), sort_order=1)
        self.food = FRLineItem.objects.create(funding_request=self.fr, name='Concessions',
                                              amount_awarded=Decimal('200.00'), sort_order=2)

    def buy(self, line, amount, day, memo=None, receipt=None, txn=None):
        """ A purchase on its own Workday line, charged to ``line``, with an optional receipt. """
        date = datetime.date(2026, 9, day)
        memo = memo or '%s %s (F.27.16)' % (line.name, amount)
        txn = txn or supplier_line(memo, '-%s' % amount, date=date)
        entry = ParsedTransaction.objects.create(
            parent_transaction=txn, amount=-Decimal(amount), effective_date=date,
            status=TransactionStatus.SETTLED, fund_source=fund('sga_fr'), fr_line_target=line,
            lnl_spend_category=category('consumables'), description=memo)
        if receipt is not None:
            attach(entry, *receipt)
        return entry

    def refund(self, purchase, amount):
        txn = supplier_line('Return of %s' % purchase.description, amount,
                            date=datetime.date(2026, 9, 20))
        return ParsedTransaction.objects.create(
            parent_transaction=txn, amount=Decimal(amount), effective_date=txn.accounting_date,
            status=TransactionStatus.SETTLED, refund_of=purchase, fund_source=fund('sga_fr'),
            fr_line_target=purchase.fr_line_target, lnl_spend_category=category('consumables'),
            description='Return')

    def encumber(self, line, amount):
        encumbrance = Encumbrance.objects.create(description='Poster order')
        ParsedTransaction.objects.create(
            amount=-Decimal(amount), fund_source=fund('sga_fr'), fr_line_target=line,
            lnl_spend_category=category('consumables'), encumbrance=encumbrance)
        return encumbrance


# ---------------------------------------------------------------------------
# What goes on the form
# ---------------------------------------------------------------------------

class GatherTests(FormMixin, CacheResetMixin, TestCase):

    def test_each_line_lists_what_was_spent_on_it_by_date(self):
        later = self.buy(self.posters, '120.00', 10)
        sooner = self.buy(self.posters, '30.00', 5)
        snacks = self.buy(self.food, '45.50', 1)
        form = gather(self.fr)
        self.assertEqual([line for line, _, _ in form.lines], [self.posters, self.food])
        self.assertEqual([[p.entry for p in purchases] for _, purchases, _ in form.lines],
                         [[sooner, later], [snacks]])
        self.assertEqual([spent for _, _, spent in form.lines],
                         [Decimal('150.00'), Decimal('45.50')])
        self.assertEqual(form.total_spent, Decimal('195.50'))

    def test_what_a_purchase_says(self):
        self.buy(self.posters, '120.00', 10, memo='Posters, posters, (F.27.16)')
        purchase = gather(self.fr).purchases[0]
        self.assertEqual(purchase.amount, Decimal('120.00'))
        self.assertEqual(purchase.payee, 'Amazon Capital Services, Inc.')
        self.assertEqual(purchase.description, 'Posters, posters, (F.27.16)')
        self.assertEqual(purchase.workday, '26080001-SIN--120.00')
        self.assertEqual(purchase.date, datetime.date(2026, 9, 10))

    def test_a_line_nothing_was_spent_on_is_still_listed(self):
        self.buy(self.posters, '120.00', 10)
        form = gather(self.fr)
        self.assertEqual(form.lines[1], (self.food, [], Decimal('0.00')))

    def test_encumbrances_are_not_purchases_but_are_counted(self):
        self.encumber(self.posters, '80.00')
        form = gather(self.fr)
        self.assertEqual(form.purchases, [])
        self.assertEqual(form.encumbered, Decimal('80.00'))

    def test_a_refund_comes_off_what_was_spent(self):
        bought = self.buy(self.posters, '100.00', 10)
        self.refund(bought, '20.00')
        form = gather(self.fr)
        refund = form.purchases[1]
        self.assertTrue(refund.is_refund)
        self.assertEqual(refund.amount, Decimal('-20.00'))
        self.assertEqual(form.total_spent, Decimal('80.00'))

    def test_sga_paying_the_request_back_is_not_a_purchase(self):
        reimburse(self.fr, '50.00')
        self.assertEqual(gather(self.fr).purchases, [])

    def test_receipts_are_numbered_in_the_order_the_breakdown_reaches_them(self):
        # Concessions were bought first, but Posters is the request's first line.
        snacks = self.buy(self.food, '45.00', 1, receipt=('snacks.jpg', jpeg()))
        posters = self.buy(self.posters, '120.00', 10, receipt=('posters.pdf', pdf()))
        form = gather(self.fr)
        self.assertEqual([receipt.purchases[0].entry for receipt in form.receipts],
                         [posters, snacks])
        self.assertEqual([receipt.number for receipt in form.receipts], [1, 2])

    def test_one_receipt_backs_every_entry_on_its_workday_line(self):
        txn = supplier_line('Posters and popcorn (F.27.16)', '-150.00',
                            date=datetime.date(2026, 9, 10))
        self.buy(self.posters, '100.00', 10, txn=txn, receipt=('order.pdf', pdf()))
        self.buy(self.food, '50.00', 10, txn=txn)
        form = gather(self.fr)
        self.assertEqual(len(form.receipts), 1)
        self.assertEqual([p.receipt.number for p in form.purchases], [1, 1])
        self.assertEqual(form.receipts[0].amount, Decimal('150.00'))
        self.assertEqual(form.missing, [])

    def test_a_receipt_on_the_encumbrance_is_used_when_the_entry_has_none(self):
        encumbrance = Encumbrance.objects.create(description='Poster order')
        attach(encumbrance, 'quote.pdf', pdf())
        entry = self.buy(self.posters, '120.00', 10)
        entry.encumbrance = encumbrance
        entry.save()
        receipt = gather(self.fr).purchases[0].receipt
        self.assertTrue(receipt.from_encumbrance)
        self.assertEqual(receipt.name, 'quote.pdf')

    def test_the_entry_own_receipt_comes_before_the_encumbrance(self):
        encumbrance = Encumbrance.objects.create(description='Poster order')
        attach(encumbrance, 'quote.pdf', pdf())
        entry = self.buy(self.posters, '120.00', 10, receipt=('receipt.pdf', pdf()))
        entry.encumbrance = encumbrance
        entry.save()
        receipt = gather(self.fr).purchases[0].receipt
        self.assertFalse(receipt.from_encumbrance)
        self.assertEqual(receipt.name, 'receipt.pdf')

    def test_a_purchase_without_a_receipt_is_missing_and_a_refund_is_not(self):
        bought = self.buy(self.posters, '100.00', 10)
        self.refund(bought, '20.00')
        missing = gather(self.fr).missing
        self.assertEqual([purchase.entry for purchase in missing], [bought])

    def test_what_the_pdf_can_take_is_read_from_the_name(self):
        self.buy(self.posters, '1.00', 1, receipt=('a.PDF', pdf()))
        self.buy(self.posters, '2.00', 2, receipt=('b.jpeg', jpeg()))
        self.buy(self.posters, '3.00', 3, receipt=('c.HEIC', b'not a jpeg'))
        self.assertEqual([receipt.kind for receipt in gather(self.fr).receipts],
                         ['pdf', 'image', ''])

    def test_spending_in_the_queue_that_quotes_the_request(self):
        velcro = supplier_line('Velcro, consumables, (F.27.16)', '-25.00')
        supplier_line('Tape, consumables, (F.27.161)', '-10.00')
        sga_line('F.27.16 Film Posters and Concessions', '120.00')
        self.assertEqual(gather(self.fr).unsettled, [velcro])

    def test_the_file_name(self):
        self.assertEqual(gather(self.fr).filename, 'lnl-frrf-f-27-16.pdf')


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

class ReportTests(FormMixin, CacheResetMixin, TestCase):

    def warnings(self):
        return ' '.join(fr_report_form(self.fr).warnings)

    def test_one_table_per_line_with_its_total(self):
        self.buy(self.posters, '120.00', 10, receipt=('posters.pdf', pdf()))
        report = fr_report_form(self.fr)
        self.assertEqual(report.title, 'Funding Request Report Form')
        self.assertEqual(report.period, 'FY27 · F.27.16 Film Posters and Concessions')
        self.assertEqual([section.title for section in report.sections], ['Posters', 'Concessions'])
        posters = report.sections[0]
        self.assertEqual(posters.rows[0].cells['receipt'], 1)
        self.assertEqual(posters.rows[0].cells['amount'], Decimal('120.00'))
        self.assertEqual(posters.total.cells['amount'], Decimal('120.00'))
        self.assertEqual(posters.total.cells['description'], 'Spent, of $300.00 approved')
        self.assertEqual(report.sections[1].rows, [])
        self.assertEqual(report.warnings, [])

    def test_the_headline_figures(self):
        self.buy(self.posters, '120.00', 10, receipt=('posters.pdf', pdf()))
        self.buy(self.food, '30.00', 11)
        stats = {stat.label: stat for stat in fr_report_form(self.fr).stats}
        self.assertEqual(stats['Request ID'].value, 'F.27.16')
        self.assertEqual(stats['Request ID'].sub, 'Financial Board')
        self.assertEqual(stats['Date approved'].value, 'Sep 3, 2026')
        self.assertEqual(stats['Amount approved'].value, Decimal('500.00'))
        self.assertEqual(stats['Total spent'].value, Decimal('150.00'))
        self.assertEqual(stats['Receipts'].value, 1)
        self.assertEqual(stats['Receipts'].sub, '1 of 2 purchases with one')

    def test_a_purchase_without_a_receipt_is_marked_and_warned_about(self):
        self.buy(self.posters, '120.00', 10)
        report = fr_report_form(self.fr)
        row = report.sections[0].rows[0]
        self.assertEqual((row.tone, row.note), ('danger', 'No receipt'))
        self.assertIn("1 purchase has no receipt, $120.00 in all", ' '.join(report.warnings))

    def test_the_request_has_what_sga_form_asks_for(self):
        self.fr.reference = ''
        self.fr.date_approved = None
        self.fr.save()
        warnings = self.warnings()
        self.assertIn('no SGA reference number', warnings)
        self.assertIn('no approval date', warnings)

    def test_a_receipt_the_pdf_cannot_take(self):
        self.buy(self.posters, '120.00', 10, receipt=('IMG_1234.HEIC', b'not a jpeg'))
        self.assertIn("Receipt 1 (IMG_1234.HEIC) can't go into the PDF", self.warnings())

    def test_a_receipt_from_the_encumbrance_may_be_a_quote(self):
        encumbrance = Encumbrance.objects.create(description='Poster order')
        attach(encumbrance, 'quote.pdf', pdf())
        entry = self.buy(self.posters, '120.00', 10)
        entry.encumbrance = encumbrance
        entry.save()
        report = fr_report_form(self.fr)
        self.assertIn("Check it is a receipt", ' '.join(report.warnings))
        self.assertIn("encumbrance", report.sections[0].rows[0].note)

    def test_spending_left_off_the_form(self):
        self.encumber(self.posters, '80.00')
        supplier_line('Velcro, consumables, (F.27.16)', '-25.00')
        warnings = self.warnings()
        self.assertIn('$80.00 is still encumbered', warnings)
        self.assertIn('1 Workday line quoting F.27.16 is still in the queue, $25.00 in all',
                      warnings)

    def test_a_line_over_its_award(self):
        self.buy(self.food, '229.00', 10, receipt=('food.pdf', pdf()))
        self.assertIn('Spending on Concessions is $29.00 over', self.warnings())

    def test_the_csv_names_each_line(self):
        self.buy(self.posters, '120.00', 10, receipt=('posters.pdf', pdf()))
        rows = list(csv.reader(io.StringIO(as_csv(fr_report_form(self.fr))[1:])))
        self.assertEqual(rows[0], ['Section', 'Receipt', 'Date', 'Paid to', 'Description',
                                   'Workday', 'Amount'])
        self.assertEqual(rows[1][0], 'Posters')
        self.assertEqual(rows[1][-1], '120.00')


# ---------------------------------------------------------------------------
# The PDF
# ---------------------------------------------------------------------------

class PDFTests(FormMixin, CacheResetMixin, TestCase):

    def pages(self):
        return PdfReader(io.BytesIO(report_form_pdf(gather(self.fr)))).pages

    def test_the_breakdown_then_each_receipt_in_number_order(self):
        self.buy(self.posters, '120.00', 10, receipt=('posters.jpg', jpeg()))
        self.buy(self.posters, '30.00', 11, receipt=('logo.png', png_with_transparency()))
        self.buy(self.food, '45.00', 1, receipt=('snacks.pdf', pdf(pages=2)))
        pages = self.pages()
        receipts = [page.extract_text() for page in pages[-4:]]
        self.assertTrue(receipts[0].startswith('Receipt 1 of 3'), receipts[0])
        self.assertTrue(receipts[1].startswith('Receipt 2 of 3'), receipts[1])
        self.assertTrue(receipts[2].startswith('Receipt 3 of 3'), receipts[2])
        self.assertIn('page 1 of 2', receipts[2])
        self.assertIn('page 2 of 2', receipts[3])
        breakdown = ' '.join(page.extract_text() for page in pages[:-4])
        for words in ('F.27.16', 'Film Posters and Concessions', 'Posters', 'Concessions',
                      '$195.00'):
            self.assertIn(words, breakdown)

    def test_every_receipt_page_is_letter_sized(self):
        self.buy(self.posters, '120.00', 10, receipt=('wide.jpg', jpeg(size=(2400, 300))))
        self.buy(self.food, '45.00', 1, receipt=('a4.pdf', pdf()))
        for page in self.pages()[-2:]:
            self.assertEqual((float(page.mediabox.width), float(page.mediabox.height)),
                             (612.0, 792.0))

    def test_a_receipt_that_cannot_be_read_says_so_in_its_place(self):
        self.buy(self.posters, '1.00', 1, receipt=('IMG_1234.HEIC', b'not a jpeg'))
        self.buy(self.posters, '2.00', 2, receipt=('locked.pdf', pdf(password='secret')))
        gone = self.buy(self.posters, '3.00', 3)
        gone.receipt_file.name = 'finance/receipts/2026/09/gone.pdf'
        gone.save()
        texts = [page.extract_text() for page in self.pages()[-3:]]
        self.assertIn('its file type cannot be shown in a PDF', texts[0])
        self.assertIn('IMG_1234.HEIC', texts[0])
        self.assertIn('protected by a password', texts[1])
        self.assertIn('the file could not be read', texts[2])

    def test_a_request_with_no_receipts_is_the_breakdown_alone(self):
        self.buy(self.posters, '120.00', 10)
        self.assertIn('$120.00', ' '.join(page.extract_text() for page in self.pages()))


# ---------------------------------------------------------------------------
# The pages
# ---------------------------------------------------------------------------

class ReportFormPageTests(FormMixin, CacheResetMixin, FinanceViewTestCase):

    def setUp(self):
        super(ReportFormPageTests, self).setUp()
        self.grant('view_subledger')
        self.url = reverse('finance:report', args=['fr-report-form'])

    def test_the_report_picks_a_request_sga_still_owes_on(self):
        # Listed first by name, but nothing has been spent on it.
        FundingRequest.objects.create(name='Absent', reference='A.27.1', fiscal_year=2027)
        self.buy(self.posters, '120.00', 10)
        response = self.client.get(self.url, {'fy': '2027'})
        self.assertOk(response)
        self.assertEqual(response.context['fr'], self.fr)
        self.assertEqual([fr.name for fr in response.context['fr_choices']],
                         ['Absent', 'Film Posters and Concessions'])
        self.assertContains(response, 'Spent, of $300.00 approved')

    def test_a_request_from_another_year_is_offered_when_asked_for(self):
        older = FundingRequest.objects.create(name='Old Films', reference='F.26.3',
                                              fiscal_year=2026)
        response = self.client.get(self.url, {'fy': '2027', 'request': older.pk})
        self.assertEqual(response.context['fr'], older)
        self.assertIn(older, response.context['fr_choices'])

    def test_an_unknown_request_is_not_found(self):
        self.assertEqual(self.client.get(self.url, {'request': '99999'}).status_code, 404)
        self.assertEqual(self.client.get(self.url, {'request': 'abc'}).status_code, 404)

    def test_a_year_with_no_requests_says_so(self):
        response = self.client.get(self.url, {'fy': '2030'})
        self.assertContains(response, 'There are no funding requests for FY30.')

    def test_the_pdf_needs_permission_to_view_receipts(self):
        self.buy(self.posters, '120.00', 10, receipt=('posters.pdf', pdf()))
        params = {'fy': '2027', 'request': self.fr.pk}
        response = self.client.get(self.url, params)
        self.assertNotContains(response, 'format=pdf')
        self.assertContains(response, 'it needs permission to view receipts')
        self.assertEqual(self.client.get(self.url, dict(params, format='pdf')).status_code, 403)

        self.grant('view_subledger', 'view_subledger_receipts')
        self.assertContains(self.client.get(self.url, params), 'format=pdf')
        response = self.client.get(self.url, dict(params, format='pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('filename="lnl-frrf-f-27-16.pdf"', response['Content-Disposition'])

    def test_the_csv(self):
        response = self.client.get(self.url, {'request': self.fr.pk, 'format': 'csv'})
        self.assertIn('filename="lnl-fr-report-form-f-27-16.csv"',
                      response['Content-Disposition'])

    def test_the_reports_tab_lists_it_without_a_download(self):
        # The download is the chosen request's, so it is offered on the report.
        response = self.client.get(reverse('finance:reports'))
        self.assertContains(response, 'Funding Request Report Form')
        self.assertNotRegex(response.content.decode(), r'fr-report-form/\?[^"]*format=csv')

    def test_a_request_page_links_to_it(self):
        self.grant('view_subledger', 'view_fundingrequest')
        response = self.client.get(reverse('finance:fr-detail', args=[self.fr.pk]))
        self.assertContains(response, '%s?request=%s' % (self.url, self.fr.pk))

"""
The Funding Request Report Form: what SGA asks for before it pays a request
back.

SGA reimburses a funding request for what was actually spent, and only once it
has seen the proof: a breakdown of every purchase, and a copy of the receipt,
invoice or ISD behind each one. An item without proof of purchase is not
funded. Everything the form needs is already in the ledger -- the request's
lines, every entry charged to them and the receipt attached to each entry --
so it is put together here rather than by hand.

:func:`gather` works out what goes on the form: the purchases on each line of
the request, and which receipt backs each one, numbered in the order the
breakdown first mentions it. :func:`finance.reports.fr_report_form` lays that
out as a report to check on screen, and :func:`report_form_pdf` as the PDF to
hand SGA: the breakdown first, then every receipt in number order, each page
labelled with its number so a reviewer can match the two.

The PDF is drawn with xhtml2pdf and ReportLab rather than WeasyPrint, which the
invoices use, so that it can be made on any machine the app runs on.
"""
import os
from io import BytesIO

from django.db.models import Q, Sum
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.text import slugify
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from xhtml2pdf import pisa

from finance.models import ZERO, ParsedTransaction, WorkdayTransaction, money
from finance.suggestions import funding_request_references
from pdfs.views import link_callback

#: Receipts the PDF can take, by the file's extension. Anything else -- an
#: iPhone's HEIC photo, a Word document -- is listed for the Treasurer to
#: attach to SGA's form by hand.
PDF_EXTENSIONS = ('.pdf',)
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp')


class Receipt(object):
    """
    One file of proof, numbered as the breakdown first mentions it.

    One receipt can back several purchases: an order split across two lines of
    the request is still one receipt, and goes into the PDF once.
    ``from_encumbrance`` is a file taken from the encumbrance the purchase was
    logged as, which asks for "a receipt or a quote" -- and a quote is not
    proof of purchase.
    """

    def __init__(self, number, file, from_encumbrance=False):
        self.number = number
        self.file = file
        self.from_encumbrance = from_encumbrance
        self.purchases = []

    @property
    def name(self):
        """ The file's own name, without the folders it is stored under. """
        return os.path.basename(self.file.name)

    @property
    def kind(self):
        """ ``'pdf'``, ``'image'``, or ``''`` for a file the PDF cannot take. """
        extension = os.path.splitext(self.file.name)[1].lower()
        if extension in PDF_EXTENSIONS:
            return 'pdf'
        if extension in IMAGE_EXTENSIONS:
            return 'image'
        return ''

    @property
    def payee(self):
        """ Who the first purchase it backs was paid to. """
        return self.purchases[0].payee if self.purchases else ''

    @property
    def date(self):
        return self.purchases[0].date if self.purchases else None

    @property
    def amount(self):
        """ What the purchases it backs come to. """
        return sum((purchase.amount for purchase in self.purchases), ZERO)


class Purchase(object):
    """
    One entry charged to a line of the request: a row of the breakdown.

    ``amount`` is what was spent, so positive; a refund is negative, because
    it takes money off what SGA is asked to pay.
    """

    def __init__(self, entry, receipt=None):
        self.entry = entry
        self.receipt = receipt
        txn = entry.parent_transaction
        self.line = entry.fr_line_target
        self.date = entry.effective_date
        self.payee = entry.payee_label
        self.description = entry.description or (txn.memo or '')[:80]
        # The document's number without its type, "26080001-SIN": the suffix
        # already says it is an invoice, an ISD or an expense report.
        self.workday = txn.reference.split(':', 1)[-1].strip()
        self.amount = -money(entry.amount)
        self.is_refund = entry.refund_of_id is not None


class ReportForm(object):
    """
    Everything the form says about one request.

    ``lines`` is ``[(line, purchases, spent)]`` for every line of the request,
    in its own order, including lines nothing has been charged to: SGA reads
    the breakdown against the request it approved.
    """

    def __init__(self, fr, lines, receipts, encumbered, unsettled):
        self.fr = fr
        self.lines = lines
        self.receipts = receipts
        self.encumbered = encumbered
        self.unsettled = unsettled

    @property
    def purchases(self):
        return [purchase for _, purchases, _ in self.lines for purchase in purchases]

    @property
    def total_spent(self):
        """ What was spent on the request, net of refunds: what SGA is asked to pay. """
        return sum((spent for _, _, spent in self.lines), ZERO)

    @property
    def missing(self):
        """
        Purchases with no receipt. A refund without one is left out: it takes
        money off the claim, so there is nothing for SGA to refuse.
        """
        return [purchase for purchase in self.purchases
                if purchase.receipt is None and not purchase.is_refund]

    @property
    def file_part(self):
        """ The request as it goes into a file name: ``f-27-16``. """
        label = (self.fr.reference or self.fr.name).replace('.', '-')
        return slugify(label) or str(self.fr.pk)

    @property
    def filename(self):
        """ ``lnl-frrf-f-27-16.pdf``. """
        return 'lnl-frrf-%s.pdf' % self.file_part


def unsettled_lines(fr):
    """
    Spending in the queue that quotes the request's number and is not settled
    yet: purchases that will be missing from the form until it is.

    Money coming in is left out -- SGA's reimbursement quotes the number too.
    """
    if not fr.reference:
        return []
    lines = (WorkdayTransaction.objects.unreconciled()
             .filter(net_amount__lt=0, memo__icontains=fr.reference)
             .order_by('accounting_date', 'pk'))
    return [txn for txn in lines if fr.reference in funding_request_references(txn.memo)]


def gather(fr):
    """
    The request's purchases, line by line, with the receipt behind each.

    A purchase is any entry charged to one of the request's lines that has
    reached Workday, settled or not; an encumbrance has not been spent, and
    SGA pays back only what has. Its receipt is the entry's own, or failing
    that one attached to another entry on the same Workday line -- an order
    split across lines is one purchase with one receipt -- or failing that the
    encumbrance it was logged as. Receipts are numbered in the order the
    breakdown first reaches them.
    """
    entries = list(ParsedTransaction.objects
                   .filter(fr_line_target__funding_request=fr, parent_transaction__isnull=False)
                   .select_related('parent_transaction', 'encumbrance', 'fr_line_target')
                   .order_by('effective_date', 'pk'))
    shared = {}
    for sibling in (ParsedTransaction.objects
                    .filter(parent_transaction__in={entry.parent_transaction_id
                                                    for entry in entries})
                    .exclude(Q(receipt_file='') | Q(receipt_file__isnull=True))
                    .order_by('pk')):
        shared.setdefault(sibling.parent_transaction_id, sibling.receipt_file)

    receipts = {}
    by_line = {}
    for entry in entries:
        file, from_encumbrance = entry.receipt_file, False
        if not file:
            file = shared.get(entry.parent_transaction_id)
        if not file and entry.encumbrance is not None and entry.encumbrance.receipt_file:
            file, from_encumbrance = entry.encumbrance.receipt_file, True
        receipt = None
        if file:
            receipt = receipts.get(file.name)
            if receipt is None:
                receipt = receipts[file.name] = Receipt(None, file, from_encumbrance)
        purchase = Purchase(entry, receipt)
        if receipt is not None:
            receipt.purchases.append(purchase)
        by_line.setdefault(entry.fr_line_target_id, []).append(purchase)

    lines, ordered = [], []
    for line in fr.line_items.order_by('sort_order', 'pk'):
        purchases = by_line.get(line.pk, [])
        for purchase in purchases:
            if purchase.receipt is not None and purchase.receipt.number is None:
                ordered.append(purchase.receipt)
                purchase.receipt.number = len(ordered)
        lines.append((line, purchases, sum((p.amount for p in purchases), ZERO)))

    encumbered = -money(ParsedTransaction.objects
                        .filter(fr_line_target__funding_request=fr,
                                parent_transaction__isnull=True)
                        .aggregate(t=Sum('amount'))['t'])
    return ReportForm(fr, lines, ordered, encumbered, unsettled_lines(fr))


# ---------------------------------------------------------------------------
# The PDF
# ---------------------------------------------------------------------------

PAGE_WIDTH, PAGE_HEIGHT = letter
#: Half an inch round the edge of a receipt page.
MARGIN = 36
#: The band at the top of a receipt page that says which receipt it is.
CAPTION = 42
#: The space a receipt is fitted into, below its caption.
BODY_WIDTH = PAGE_WIDTH - 2 * MARGIN
BODY_HEIGHT = PAGE_HEIGHT - 2 * MARGIN - CAPTION
#: The longest side a photo is kept at: plenty to read a till receipt by, and a
#: phone's twelve-megapixel original would make the PDF too big to email.
IMAGE_PIXELS = 2000


class Unreadable(Exception):
    """ A receipt the PDF cannot take, and why, in words for the page standing in for it. """


def _dollars(amount):
    """ ``$1,234.50``, or ``-$50.00`` for a refund, as the breakdown writes them. """
    return '%s$%s' % ('-' if amount < 0 else '', '{:,.2f}'.format(abs(amount)))


def _fit(text, font, size, width):
    """ ``text`` cut short with an ellipsis if it would run off the page. """
    if stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth(text + '…', font, size) > width:
        text = text[:-1]
    return text + '…'


def _caption_lines(receipt, count, page, pages):
    """ The two lines at the top of each of a receipt's pages. """
    head = "Receipt %s of %s" % (receipt.number, count)
    if pages > 1:
        head += "  ·  page %s of %s" % (page + 1, pages)
    detail = [receipt.payee]
    if receipt.date:
        detail.append(date_format(receipt.date, 'M j, Y'))
    detail.append(_dollars(receipt.amount))
    detail.append(', '.join(sorted({purchase.line.name for purchase in receipt.purchases})))
    return head, '  ·  '.join(part for part in detail if part)


def _captioned_pages(receipt, count, pages, draw=None):
    """
    ``pages`` letter pages with the receipt's caption at the top of each,
    and whatever ``draw(canvas)`` puts below it.
    """
    buffer = BytesIO()
    sheet = canvas.Canvas(buffer, pagesize=letter)
    for page in range(pages):
        head, detail = _caption_lines(receipt, count, page, pages)
        top = PAGE_HEIGHT - MARGIN
        sheet.setFont('Helvetica-Bold', 12)
        sheet.drawString(MARGIN, top - 12, head)
        sheet.setFont('Helvetica', 9)
        sheet.drawString(MARGIN, top - 26, _fit(detail, 'Helvetica', 9, BODY_WIDTH))
        sheet.setLineWidth(0.5)
        sheet.line(MARGIN, top - CAPTION + 8, PAGE_WIDTH - MARGIN, top - CAPTION + 8)
        if draw is not None:
            draw(sheet)
        sheet.showPage()
    sheet.save()
    return list(PdfReader(buffer).pages)


def _read(file):
    """ The file's bytes, from wherever the storage keeps them. """
    file.open('rb')
    try:
        return file.read()
    finally:
        file.close()


def _pdf_pages(receipt, count, data):
    """ Each page of a PDF receipt, fitted below its caption on a letter page. """
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(''):
        raise Unreadable("it is protected by a password")
    sources = list(reader.pages)
    if not sources:
        raise Unreadable("it has no pages")
    pages = _captioned_pages(receipt, count, len(sources))
    for base, page in zip(pages, sources):
        page.transfer_rotation_to_content()
        box = page.cropbox
        width, height = float(box.width), float(box.height)
        # Shrunk to fit, never enlarged: a till receipt scanned at its own size
        # reads best at that size.
        scale = min(BODY_WIDTH / width, BODY_HEIGHT / height, 1)
        x = MARGIN + (BODY_WIDTH - width * scale) / 2
        y = MARGIN + BODY_HEIGHT - height * scale
        base.merge_transformed_page(page, Transformation()
                                    .translate(-float(box.left), -float(box.bottom))
                                    .scale(scale, scale).translate(x, y))
    return pages


def _image_pages(receipt, count, data):
    """ A photo or scan of a receipt, the right way up and fitted below its caption. """
    image = ImageOps.exif_transpose(Image.open(BytesIO(data)))
    if image.mode in ('RGBA', 'LA', 'P'):
        # A transparent background comes out black unless it is painted white.
        image = image.convert('RGBA')
        flat = Image.new('RGB', image.size, 'white')
        flat.paste(image, mask=image.split()[3])
        image = flat
    image = image.convert('RGB')
    image.thumbnail((IMAGE_PIXELS, IMAGE_PIXELS))
    jpeg = BytesIO()
    image.save(jpeg, 'JPEG', quality=85)
    jpeg.seek(0)
    picture = ImageReader(jpeg)
    width, height = image.size

    def draw(sheet):
        scale = min(BODY_WIDTH / width, BODY_HEIGHT / height)
        sheet.drawImage(picture, MARGIN + (BODY_WIDTH - width * scale) / 2,
                        MARGIN + BODY_HEIGHT - height * scale, width * scale, height * scale)

    return _captioned_pages(receipt, count, 1, draw)


def _stand_in_pages(receipt, count, reason):
    """
    A page in place of a receipt the PDF could not take, saying so, so the
    numbering stays whole and SGA knows to look for it separately.
    """
    def draw(sheet):
        sheet.setFont('Helvetica', 11)
        top = PAGE_HEIGHT - MARGIN - CAPTION - 20
        sheet.drawString(MARGIN, top, "This receipt could not be included in this PDF: %s." % reason)
        sheet.drawString(MARGIN, top - 16, _fit("It is submitted with the form as a separate file, %s."
                                                % receipt.name, 'Helvetica', 11, BODY_WIDTH))

    return _captioned_pages(receipt, count, 1, draw)


def receipt_pages(receipt, count):
    """
    The pages one receipt takes up in the PDF.

    What a file is is read from its bytes, not its name, so a PDF saved as
    ``.jpg`` still goes in. A receipt is somebody's upload and anything can be
    wrong with it -- gone from storage, damaged, a format nothing here opens --
    so whatever goes wrong becomes a page saying so, rather than stopping the
    whole form. The report page has already warned about the file types it
    knows the PDF cannot take.
    """
    try:
        data = _read(receipt.file)
    except Exception:
        return _stand_in_pages(receipt, count, "the file could not be read")
    try:
        if b'%PDF' in data[:1024]:
            return _pdf_pages(receipt, count, data)
        return _image_pages(receipt, count, data)
    except Unreadable as error:
        return _stand_in_pages(receipt, count, str(error))
    except Exception:
        return _stand_in_pages(receipt, count, "its file type cannot be shown in a PDF")


def report_form_pdf(form, request=None):
    """
    The form as PDF bytes: the breakdown, then each receipt in number order.
    """
    html = render_to_string('finance/frrf_pdf.html', {
        'form': form,
        'fr': form.fr,
        'generated_on': timezone.localdate(),
    }, request=request)
    breakdown = BytesIO()
    pisa.CreatePDF(html, dest=breakdown, link_callback=link_callback)
    writer = PdfWriter()
    writer.append(breakdown)
    for receipt in form.receipts:
        for page in receipt_pages(receipt, len(form.receipts)):
            writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()

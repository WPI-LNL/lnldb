import os.path
from io import BytesIO

from PyPDF2 import PdfFileReader, PdfFileWriter


def get_base(name):
    return os.path.abspath(os.path.join(os.path.dirname(__file__), 'overlay_bases', name))


def merge_pdf_overlay(orig, overlay, outfile=None):
    """
    Makes an overlay using the first pages of the
     pdfs specified. Takes 2 file like objects,
     output into either a third or a tempfile

    """
    if outfile is None:
        outfile = BytesIO()

    orig = PdfFileReader(orig).getPage(0)
    overlay = PdfFileReader(overlay).getPage(0)

    orig.mergePage(overlay)

    writer = PdfFileWriter()
    writer.addPage(orig)
    writer.write(outfile)
    outfile.flush()
    return outfile


def to_cash(amt):
    return "$%0.2f" % amt

from io import BytesIO
import os.path
from datetime import date
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from PyPDF2 import PdfFileReader, PdfFileWriter, PdfFileMerger

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

def make_idt_overlay(dep_name, fund, amount, proj_amt=0, person_name=None, description=None):
    outfile = BytesIO()
    c = Canvas(outfile, pagesize=landscape(letter))
    c.rotate(90)
    c.translate(0,-letter[0])

    to_cash = lambda amt: "$%0.2f" % amt
    amount = float(amount)
    proj_amt = float(proj_amt)

    c.drawString(2.15*inch,6.25*inch,"Lens and Lights")
    c.drawString(7.5*inch,6.25*inch, str(date.today()))
    if dep_name:
        c.drawString(2.15*inch,6.75*inch,str(dep_name))

    if person_name:
        c.drawString(7.5*inch,6.75*inch,str(person_name))

    if description:
        c.drawString(0.6*inch,2.15*inch, str(description))

    # amounts on their side
    c.drawCentredString(4.3*inch,5.15*inch,to_cash(amount + proj_amt))
    c.drawCentredString(4.3*inch,3.45*inch,to_cash(amount + proj_amt))

    # their fund
    if fund and len(fund) == 3:
        # yes, it is actually spelled like that. Pip, pip, cherrio
        c.drawCentredString(0.9*inch,5.15*inch,str(fund[0]))
        c.drawCentredString(1.75*inch,5.15*inch,str(fund[1]))
        c.drawCentredString(2.6*inch,5.15*inch,str(fund[2]))
    

    # amounts on our side 
    if proj_amt:
        c.drawCentredString(8.65*inch,4.8*inch,to_cash(proj_amt))
    c.drawCentredString(8.65*inch,5.15*inch,to_cash(amount))
    c.drawCentredString(8.65*inch,3.45*inch,to_cash(proj_amt+amount))

    # our fund
    c.drawCentredString(5.25*inch,5.15*inch,str(81720))
    c.drawCentredString(6.1*inch,5.15*inch,str(72810))
    c.drawCentredString(6.95*inch,5.15*inch,str(7649))

    if proj_amt:
        c.drawCentredString(5.25*inch,4.8*inch,str(83100))
        c.drawCentredString(6.1*inch,4.8*inch,str(72800))
        c.drawCentredString(6.95*inch,4.8*inch,str(7649))

    c.save()
    outfile.flush()
    return outfile

def make_idt_single(event, user=None):
    # possible penny-off bug if the projection cost is odd. 
    overlay = make_idt_overlay(
            dep_name=event.billing_org or event.org.first(),
            fund=event.billing_fund.as_tuple() if event.billing_fund else None, 
            amount=event.cost_total - event.cost_projection_total/2, 
            proj_amt= event.cost_projection_total/2, 
            person_name=str(user) if user else None, 
            description="LNL Services for %s" % str(event)
    )
    with open(get_base("idt.pdf"), "rb") as base:
        output = merge_pdf_overlay(base, overlay)
    return output

def make_idt_bulk(events, user=None, org_for=None, fund_for=None):
    total = sum([e.cost_total for e in events])
    proj_total = sum([e.cost_projection_total for e in events])/2
    total -= proj_total

    event_names = [str(e) for e in events]
    description = "LNL Services for %s" % ", ".join(event_names)

    # try to find a single org to bill, if one is provided
    if org_for is None:
        orgs = set([e.billing_org or e.org.first() for e in events])
        if len(orgs) == 1:
            org_for = orgs.pop()
   
    # likewise with funds 
    if fund_for is None:
        funds = set([e.billing_fund for e in events])
        if len(funds) == 1:
            fund_for = funds.pop()

    overlay = make_idt_overlay(
            dep_name=org_for,
            fund=fund_for.as_tuple() if fund_for else None, 
            amount=total,
            proj_amt=proj_total,
            person_name=str(user) if user else None, 
            description=description
    )
    with open(get_base("idt.pdf"), "rb") as base:
        output = merge_pdf_overlay(base, overlay)
    return output


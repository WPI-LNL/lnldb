import datetime

import os
from django.utils.text import slugify
from io import BytesIO
from xhtml2pdf import pisa
from django.template.loader import get_template
from django.template import Context
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from events.models import Event, Category, ExtraInstance
from projection.models import Projectionist, PITLevel
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import intcomma
from django.contrib.staticfiles import finders
from .overlay import make_idt_single
from .utils import concat_pdf

# Convert HTML URIs to absolute system paths so xhtml2pdf can access those resources
def link_callback(uri, rel):
    # use short variable names
    surl = settings.STATIC_URL  # Typically /static/
    sroot = settings.STATIC_ROOT  # Typically /home/userX/project_static/
    murl = settings.MEDIA_URL  # Typically /static/media/
    mroot = settings.MEDIA_ROOT  # Typically /home/userX/project_static/media/

    # convert URIs to absolute system paths
    if uri.startswith(murl):
        path = os.path.join(mroot, uri.replace(murl, ""))
    elif uri.startswith(surl):
        search_url = uri.replace(surl, "")
        path = finders.find(search_url) or os.path.join(sroot, search_url) 
    else:
        path = ""

    # make sure that file exists
    if not os.path.isfile(path):
        raise Exception('media URI must start with %s or %s' % (surl, murl))
    return path


def generate_projection_pdf(request):
    data = {}
    # prepare data
    levels = PITLevel.objects.exclude(name_short__in=['PP', 'L']).order_by('ordering')
    unlicensed_users = Projectionist.objects.exclude(pitinstances__pit_level__name_short__in=['PP', 'L'])
    licensed_users = Projectionist.objects.filter(pitinstances__pit_level__name_short__in=['PP', 'L']).exclude(
        user__groups__name="Alumni")
    alumni_users = Projectionist.objects.filter(pitinstances__pit_level__name_short__in=['PP', 'L']).filter(
        user__groups__name="Alumni")
    now = datetime.datetime.now(timezone.get_current_timezone())

    data['now'] = now
    data['unlicensed_users'] = unlicensed_users
    data['licensed_users'] = licensed_users
    data['alumni_users'] = alumni_users
    data['levels'] = levels

    # Render html content through html template with context
    template = get_template('pdf_templates/projection.html')
    html = template.render(data)
    if 'raw' in request.GET and bool(request.GET['raw']):
        return HttpResponse(html)
    # write file
    pdf_file = BytesIO()
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    # return doc
    return HttpResponse(pdf_file.getvalue(), content_type='application/pdf')


@login_required
def generate_event_pdf(request, id):
    # Prepare context
    data = {}
    event = get_object_or_404(Event, pk=id)
    data['events'] = [event]

    # Render html content through html template with context
    template = get_template('pdf_templates/events.html')
    html = template.render(data)

    if 'raw' in request.GET and bool(request.GET['raw']):
        return HttpResponse(html)

    # Write PDF to file
    pdf_file = BytesIO()
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    # Return PDF document through a Django HTTP response
    resp = HttpResponse(pdf_file.getvalue(), content_type='application/pdf')
    resp['Content-Disposition'] = 'inline; filename="%s.pdf"' % slugify(event.event_name)
    return resp


def currency(dollars):
    dollars = round(float(dollars), 2)
    return "$%s%s" % (intcomma(int(dollars)), ("%0.2f" % dollars)[-3:])


@login_required
def generate_event_bill_pdf(request, id):
    # Prepare context
    data = {}
    event = get_object_or_404(Event, pk=id)
    data['event'] = event
    cats = Category.objects.all()
    extras = {}
    for cat in cats:
        e_for_cat = ExtraInstance.objects.filter(event=event).filter(extra__category=cat)
        if len(e_for_cat) > 0:
            extras[cat] = e_for_cat
    data['extras'] = extras
    # Render html content through html template with context
    template = get_template('pdf_templates/bill-itemized.html')
    html = template.render(data)

    if 'raw' in request.GET and bool(request.GET['raw']):
        return HttpResponse(html)

    # Write PDF to file
    pdf_file = BytesIO()
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)
    
    # if it's actually an invoice, attach an idt, eh?
    if event.reviewed:
        idt = make_idt_single(event, request.user)
        pdf_file = concat_pdf(pdf_file, idt)

    # Return PDF document through a Django HTTP response
    resp = HttpResponse(pdf_file.getvalue(), content_type='application/pdf')
    resp['Content-Disposition'] = 'inline; filename="%s-bill.pdf"' % slugify(event.event_name)
    return resp


def generate_pdfs_standalone(ids=None):
    if ids is None:
        ids = []
    # returns a standalone pdf, for sending via email
    timezone.activate(timezone.get_current_timezone())

    data = {}
    events = Event.objects.filter(pk__in=ids)
    data['events'] = events

    template = get_template('pdf_templates/events.html')
    html = template.render(data)

    pdf_file = BytesIO()
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    return pdf_file.get_value()


def generate_event_pdf_multi(request, ids=None):
    # this shoud fix UTC showing up in PDFs
    timezone.activate(timezone.get_current_timezone())

    if not ids:
        return HttpResponse("Should probably give some ids to return pdfs for..")
    # Prepare IDs
    idlist = ids.split(',')
    # Prepare context
    data = {}
    events = Event.objects.filter(pk__in=idlist)
    data['events'] = events

    # Render html content through html template with context
    template = get_template('pdf_templates/events.html')
    html = template.render(data)

    if 'raw' in request.GET and bool(request.GET['raw']):
        return HttpResponse(html)

    # Write PDF to file
    pdf_file = BytesIO()
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    # Return PDF document through a Django HTTP response
    resp = HttpResponse(pdf_file, content_type='application/pdf')
    resp['Content-Disposition'] = 'inline; filename="events.pdf"'
    return resp

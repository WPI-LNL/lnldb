import datetime

import os
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
        path = os.path.join(sroot, uri.replace(surl, ""))
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
    html = template.render(Context(data))

    # write file
    pdf_pdf_file = open(os.path.join(settings.MEDIA_ROOT, 'projection-%s.pdf' % now.date()), "w+b")
    pisastatus = pisa.CreatePDF(html, dest=pdf_pdf_file, link_callback=link_callback)

    # return doc
    pdf_pdf_file.seek(0)
    pdf = pdf_pdf_file.read()
    pdf_pdf_file.close()  # Don't forget to close the file handle
    return HttpResponse(pdf, content_type='application/pdf')


@login_required
def generate_event_pdf(request, id):
    # Prepare context
    data = {}
    event = get_object_or_404(Event, pk=id)
    data['events'] = [event]

    # Render html content through html template with context
    template = get_template('pdf_templates/events.html')
    html = template.render(Context(data))

    # Write PDF to file
    pdf_file = open(os.path.join(settings.MEDIA_ROOT, 'event-%s.pdf' % event.id), "w+b")
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    # Return PDF document through a Django HTTP response
    pdf_file.seek(0)
    pdf = pdf_file.read()
    pdf_file.close()  # Don't forget to close the file handle
    return HttpResponse(pdf, content_type='application/pdf')


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
    print extras
    # Render html content through html template with context
    template = get_template('pdf_templates/bill-itemized.html')
    html = template.render(Context(data))

    # Write PDF to file
    pdf_file = open(os.path.join(settings.MEDIA_ROOT, 'pay-%s.pdf' % event.id), "w+b")
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    # Return PDF document through a Django HTTP response
    pdf_file.seek(0)
    pdf = pdf_file.read()
    pdf_file.close()  # Don't forget to close the file handle
    return HttpResponse(pdf, content_type='application/pdf')
    # return HttpResponse(html)


def generate_pdfs_standalone(ids=None):
    if ids is None:
        ids = []
    # returns a standalone pdf, for sending via email
    timezone.activate(timezone.get_current_timezone())

    data = {}
    events = Event.objects.filter(pk__in=ids)
    data['events'] = events

    template = get_template('pdf_templates/events.html')
    html = template.render(Context(data))

    pdf_file = open(os.path.join(settings.MEDIA_ROOT, 'event-multi.pdf'), "w+b")
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    pdf_file.seek(0)
    pdf = pdf_file.read()
    pdf_file.close()

    return pdf


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
    html = template.render(Context(data))

    # Write PDF to file
    pdf_file = open(os.path.join(settings.MEDIA_ROOT, 'event-multi.pdf'), "w+b")
    pisastatus = pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    # Return PDF document through a Django HTTP response
    pdf_file.seek(0)
    pdf = pdf_file.read()
    pdf_file.close()  # Don't forget to close the file handle
    return HttpResponse(pdf, content_type='application/pdf')
import os
import cStringIO as StringIO
import ho.pisa as pisa

from django.template.loader import get_template
from django.template import Context
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render_to_response, get_object_or_404
from cgi import escape
from reportlab.pdfgen import canvas

from events.models import Event

from projection.models import Projectionist,PITLevel

from django.utils import timezone
import datetime

# Convert HTML URIs to absolute system paths so xhtml2pdf can access those resources
def link_callback(uri, rel):
    # use short variable names
    sUrl = settings.STATIC_URL      # Typically /static/
    sRoot = settings.STATIC_ROOT    # Typically /home/userX/project_static/
    mUrl = settings.MEDIA_URL       # Typically /static/media/
    mRoot = settings.MEDIA_ROOT     # Typically /home/userX/project_static/media/

    # convert URIs to absolute system paths
    if uri.startswith(mUrl):
        path = os.path.join(mRoot, uri.replace(mUrl, ""))
    elif uri.startswith(sUrl):
        path = os.path.join(sRoot, uri.replace(sUrl, ""))

    # make sure that file exists
    if not os.path.isfile(path):
        raise Exception('media URI must start with %s or %s' %  (sUrl, mUrl))
    return path

def generate_projection_pdf(request):
    data = {}
    # prepare data
    levels = PITLevel.objects.exclude(name_short__in=['PP','L']).order_by('ordering')
    unlicensed_users = Projectionist.objects.exclude(pitinstances__pit_level__name_short__in=['PP','L'])
    licensed_users = Projectionist.objects.filter(pitinstances__pit_level__name_short__in=['PP','L']).exclude(user__groups__name="Alumni")
    alumni_users = Projectionist.objects.filter(pitinstances__pit_level__name_short__in=['PP','L']).filter(user__groups__name="Alumni")
    now = datetime.datetime.now(timezone.get_current_timezone())
    
    data['now'] = now
    data['unlicensed_users'] = unlicensed_users
    data['licensed_users'] = licensed_users
    data['alumni_users'] = alumni_users
    data['levels'] = levels
    
    # Render html content through html template with context
    template = get_template('pdf_templates/projection.html')
    html  = template.render(Context(data))
    
    # write file
    file = open(os.path.join(settings.MEDIA_ROOT, 'projection-%s.pdf' % now.date()), "w+b")
    pisaStatus = pisa.CreatePDF(html, dest=file, link_callback = link_callback)
    
    # return doc
    file.seek(0)
    pdf = file.read()
    file.close()            # Don't forget to close the file handle
    return HttpResponse(pdf, mimetype='application/pdf')
    
def generate_event_pdf(request, id):
    # Prepare context
    data = {}
    event = get_object_or_404(Event,pk=id)
    data['events'] = [event]

    # Render html content through html template with context
    template = get_template('pdf_templates/events.html')
    html  = template.render(Context(data))

    # Write PDF to file
    file = open(os.path.join(settings.MEDIA_ROOT, 'event-%s.pdf' % event.id), "w+b")
    pisaStatus = pisa.CreatePDF(html, dest=file, link_callback = link_callback)

    # Return PDF document through a Django HTTP response
    file.seek(0)
    pdf = file.read()
    file.close()            # Don't forget to close the file handle
    return HttpResponse(pdf, mimetype='application/pdf')


def generate_event_pdf_multi(request, ids=None):
    #this shoud fix UTC showing up in PDFs
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
    html  = template.render(Context(data))

    # Write PDF to file
    file = open(os.path.join(settings.MEDIA_ROOT, 'event-multi.pdf'), "w+b")
    pisaStatus = pisa.CreatePDF(html, dest=file, link_callback = link_callback)

    # Return PDF document through a Django HTTP response
    file.seek(0)
    pdf = file.read()
    file.close()            # Don't forget to close the file handle
    return HttpResponse(pdf, mimetype='application/pdf')
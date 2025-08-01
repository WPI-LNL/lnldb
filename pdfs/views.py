import datetime
import os
from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.humanize.templatetags.humanize import intcomma
from django.contrib.staticfiles import finders
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from xhtml2pdf import pisa

from events.models import Category, BaseEvent, Event2019, ExtraInstance, MultiBilling
from projection.models import PITLevel, Projectionist


def link_callback(uri, rel):
    """ Convert HTML URIs to absolute system paths so xhtml2pdf can access those resources """
    # use short variable names
    surl = settings.STATIC_URL  # Typically /static/
    sroot = settings.STATIC_ROOT  # Typically /home/userX/project_static/
    murl = settings.MEDIA_URL  # Typically /static/media/
    mroot = settings.MEDIA_ROOT  # Typically /home/userX/project_static/media/

    # convert URIs to absolute system paths
    if murl and uri.startswith(murl):
        path = os.path.join(mroot, uri.replace(murl, ""))
    elif surl and uri.startswith(surl):
        search_url = uri.replace(surl, "")
        path = finders.find(search_url) or os.path.join(sroot, search_url)
    else:
        path = ""

    # make sure that file exists
    if not os.path.isfile(path):
        raise Exception('media URI must start with %s or %s' % (surl, murl))
    return path


def generate_pdf(context, template, request):
    # Render html content through html template with context
    html = render_to_string(template, context=context, request=request)

    if 'raw' in request.GET and bool(request.GET['raw']):
        return HttpResponse(html)

    # Write PDF to file
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    # Return PDF document through a Django HTTP response
    return HttpResponse(pdf_file.getvalue(), content_type='application/pdf')


def get_category_data(event):
    """
    Parse event for service category information

    :param event: The event to parse
    :returns: A dictionary
    """
    is_event2019 = isinstance(event, Event2019)
    event_data = {
        'event': event,
        'is_event2019': is_event2019
    }
    if is_event2019:
        categories_data = []
        for category in Category.objects.filter(service__serviceinstance__event=event).distinct():
            o = {'category': category, 'serviceinstances_data': []}
            for serviceinstance in event.serviceinstance_set.filter(service__category=category):
                o['serviceinstances_data'].append({
                    'serviceinstance': serviceinstance,
                    'attachment': event.attachments.filter(for_service=serviceinstance.service).exists()
                })
            categories_data.append(o)
        event_data['categories_data'] = categories_data
    return event_data


def get_multibill_data(multibilling):
    data = {'multibilling': multibilling}
    orgsets = map(lambda event: event.org.all(), multibilling.events.all())
    orgs = next(iter(orgsets))
    for orgset in orgsets:
        orgs |= orgset
    orgs = orgs.distinct()
    data['orgs'] = orgs
    billing_org = multibilling.org
    data['billing_org'] = billing_org
    events = multibilling.events.order_by('datetime_start')
    data['events'] = events
    data['total_cost'] = sum(map(lambda event: event.cost_total, multibilling.events.all()))
    return data


def get_extras(event):
    event_data = {
        'event': event,
        'extras': {}
    }
    for cat in Category.objects.all():
        e_for_cat = ExtraInstance.objects.filter(event=event).filter(extra__category=cat)
        if len(e_for_cat) > 0:
            event_data['extras'][cat] = e_for_cat
    return event_data


@login_required
@permission_required("projection.view_pits", raise_exception=True)
def generate_projection_pdf(request):
    data = {}
    # prepare data
    levels = PITLevel.objects.exclude(name_short__in=['PP', 'L']).order_by('ordering')
    unlicensed_users = Projectionist.objects.exclude(pitinstances__pit_level__name_short__in=['L'])
    licensed_users = Projectionist.objects.filter(pitinstances__pit_level__name_short__in=['L']).exclude(
        user__groups__name="Alumni")
    alumni_users = Projectionist.objects.filter(pitinstances__pit_level__name_short__in=['PP', 'L']).filter(
        user__groups__name="Alumni").distinct()
    now = datetime.datetime.now(timezone.get_current_timezone())

    data['now'] = now
    data['unlicensed_users'] = unlicensed_users
    data['licensed_users'] = licensed_users
    data['alumni_users'] = alumni_users
    data['levels'] = levels

    # Render html content through html template with context
    html = render_to_string('pdf_templates/projection.html', context=data, request=request)
    if 'raw' in request.GET and bool(request.GET['raw']):
        return HttpResponse(html)
    # write file
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    # return doc
    return HttpResponse(pdf_file.getvalue(), content_type='application/pdf')


@login_required
def generate_event_pdf(request, id):
    event = get_object_or_404(BaseEvent, pk=id)
    if not request.user.has_perm('events.view_event_reports', event):
        raise PermissionDenied
    # Prepare context
    data = {}
    event_data = get_category_data(event)
    data['events_data'] = [event_data]

    resp = generate_pdf(data, 'pdf_templates/events.html', request)
    resp['Content-Disposition'] = 'inline; filename="%s.pdf"' % slugify(event.event_name)
    return resp


def currency(dollars):
    dollars = round(float(dollars), 2)
    return "$%s%s" % (intcomma(int(dollars)), ("%0.2f" % dollars)[-3:])


@login_required
def generate_event_bill_pdf(request, event):
    # Prepare context
    event = get_object_or_404(BaseEvent, pk=event)
    if not request.user.has_perm('events.view_event_billing', event):
        raise PermissionDenied
    if not event.approved and not request.user.has_perm('events.bill_event', event):
        raise PermissionDenied
    data = {}
    event_data = get_extras(event)
    data['events_data'] = [event_data]

    resp = generate_pdf(data, 'pdf_templates/bill-itemized.html', request)
    if event.reviewed:
        resp['Content-Disposition'] = 'inline; filename="%s-bill.pdf"' % slugify(event.event_name)
    else:
        resp['Content-Disposition'] = 'inline; filename="%s-quote.pdf"' % slugify(event.event_name)
    return resp


def generate_event_bill_pdf_standalone(event, request=None):
    """
    Generate event bill PDF without HttpResponse

    :returns: PDF file
    """
    data = {}
    event_data = get_extras(event)
    data['events_data'] = [event_data]
    # Render html content through html template with context
    html = render_to_string('pdf_templates/bill-itemized.html', context=data, request=request)

    # Write PDF to file
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    return pdf_file.getvalue()


@login_required
def generate_multibill_pdf(request, multibilling):
    if not request.user.has_perm('events.view_event_billing'):
        raise PermissionDenied
    # Prepare context
    multibilling = get_object_or_404(MultiBilling.objects.annotate(num_events=Count('events')), pk=multibilling)
    data = get_multibill_data(multibilling)

    # Render html content through html template with context
    resp = generate_pdf(data, 'pdf_templates/bill-multi.html', request)

    resp['Content-Disposition'] = 'inline; filename="bill.pdf"'
    return resp


def generate_multibill_pdf_standalone(multibilling, request=None):
    """
    Generate multibill PDF without HttpResponse

    :returns: PDF file
    """
    # Prepare context
    multibilling = MultiBilling.objects.annotate(num_events=Count('events')).get(id=multibilling.id)
    data = get_multibill_data(multibilling)

    # Render html content through html template with context
    html = render_to_string('pdf_templates/bill-multi.html', context=data, request=request)

    # Write PDF to file
    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    return pdf_file.getvalue()


def generate_pdfs_standalone(ids=None):
    """
    Generate PDF file without HttpResponse

    :returns: PDF file
    """
    if ids is None:
        ids = []
    # returns a standalone pdf, for sending via email
    timezone.activate(timezone.get_current_timezone())

    data = {}
    events = BaseEvent.objects.filter(pk__in=ids)
    data['events_data'] = []
    for event in events:
        event_data = get_category_data(event)
        data['events_data'].append(event_data)

    html = render_to_string('pdf_templates/events.html', context=data)

    pdf_file = BytesIO()
    pisa.CreatePDF(html, dest=pdf_file, link_callback=link_callback)

    return pdf_file.getvalue()


def generate_event_pdf_multi(request, ids=None):
    """ Generate workorder PDF for multiple events (combine into one document) """
    if not request.user.has_perm('events.view_event'):
        raise PermissionDenied
    # this should fix UTC showing up in PDFs
    timezone.activate(timezone.get_current_timezone())

    if not ids:
        return HttpResponse("Should probably give some ids to return pdfs for.")
    # Prepare IDs
    idlist = ids.split(',')
    # Prepare context
    data = {}
    events = BaseEvent.objects.filter(pk__in=idlist)
    data['events_data'] = []
    for event in events:
        event_data = get_category_data(event)
        data['events_data'].append(event_data)

    resp = generate_pdf(data, 'pdf_templates/events.html', request)
    resp['Content-Disposition'] = 'inline; filename="events.pdf"'
    return resp


@login_required
def generate_event_bill_pdf_multi(request, ids=None):
    """ Generate event bill PDF for multiple events (combine into one document) """
    if not request.user.has_perm('events.view_event_billing'):
        raise PermissionDenied
    if not ids:
        return HttpResponse("Should probably give some ids to return pdfs for.")
    # Prepare IDs
    idlist = ids.split(',')
    # Prepare context
    data = {'events_data': []}
    events = BaseEvent.objects.filter(pk__in=idlist)
    for event in events:
        event_data = get_extras(event)
        data['events_data'].append(event_data)

    resp = generate_pdf(data, 'pdf_templates/bill-itemized.html', request)
    resp['Content-Disposition'] = 'inline; filename="%s-bill.pdf"' % slugify(event.event_name)
    return resp

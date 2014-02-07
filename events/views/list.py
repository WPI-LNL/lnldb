# Create your views here.

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.models import Event,Organization

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_officer

import datetime,time
import pytz

DEFAULT_ENTRY_COUNT = 40

#generic date filtering
def datefilter(eventqs,context,start=None,end=None):
    today = datetime.date.today()
    weekfromnow = today + datetime.timedelta(days=7)
    
    if start:
        context['start'] = start
        try:
            startdate = datetime.datetime.strptime(start, '%Y-%m-%d')
            eventqs = eventqs.filter(datetime_start__gte=startdate)
            
        except:
            raise
    else:
        eventqs = eventqs.filter(datetime_start__gte=today)
        
    if end:
        context['end'] = end
        try:
            enddate = datetime.datetime.strptime(end, '%Y-%m-%d')
            eventqs = eventqs.filter(datetime_start__lte=enddate)
            
        except:
            raise
    else:
        eventqs = eventqs.filter(datetime_end__lte=weekfromnow)
    
    return eventqs,context

#paginator helper

def paginate_helper(queryset,page,count=DEFAULT_ENTRY_COUNT):
    paginator = Paginator(queryset,count)
    try:
        pag_qs = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        pag_qs = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        pag_qs = paginator.page(paginator.num_pages)
        
    return pag_qs


# helper function to return start and end for open/closed/unpaid (goes back 180 days by default)
def get_farback_date_range_plus_next_week(delta=180):
    today = datetime.date.today()
    end = today + datetime.timedelta(days=7)
    end = end.strftime('%Y-%m-%d')
    start = today - datetime.timedelta(days=delta)
    start = start.strftime('%Y-%m-%d')
    
    return start,end

### EVENT VIEWS
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def upcoming(request,start=None,end=None):
    """
    Lists Upcoming Events
    if limit = False, then it'll show all upcoming events that are more than a week away.
    """
    context = RequestContext(request)
    if not start and not end:
        today = datetime.date.today()
        start = today.strftime('%Y-%m-%d')
        
        wd = today.weekday()
        if wd == 2: # if today is weds
            end = today + datetime.timedelta(days=7)
            end = end.strftime('%Y-%m-%d')
        elif wd < 2:
            delta = 2 - wd + 1
            end = today + datetime.timedelta(days=delta)
            end = end.strftime('%Y-%m-%d')
        else:
            # fex
            # thurs == 3
            # 7 - 3 + 2 = 6 days = weds
            delta = 7 - wd + 2 
            end = today + datetime.timedelta(days=delta)
            end = end.strftime('%Y-%m-%d')
    
    #events = Event.objects.filter(approved=True).filter(closed=False).filter(paid=False).filter(datetime_start__gte=today)
    events = Event.objects.filter(approved=True).filter(Q(closed=False)|Q(cancelled=False))#.filter(paid=False)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = events.order_by('datetime_start')
    events = paginate_helper(events,page)
    
    context['h2'] = "Upcoming Events"
    context['events'] = events
    context['baseurl'] = reverse("upcoming")
    context['pdfurl'] = reverse('events-pdf-multi-empty')
    
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def incoming(request,start=None,end=None):
    context = RequestContext(request)
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=365.25)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=365.25)
        end = end.strftime('%Y-%m-%d')
    
    events = Event.objects.filter(approved=False).exclude(Q(closed=True)|Q(cancelled=True))
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Incoming Events"
    context['events'] = events
    context['baseurl'] = reverse("incoming")
    context['pdfurl'] = reverse('events-pdf-multi-empty')
    
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def openworkorders(request,start=None,end=None):
    
    if not start and not end:
        start,end = get_farback_date_range_plus_next_week()
    context = RequestContext(request)
    
    events = Event.objects.filter(Q(closed=False)|Q(cancelled=False))
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Open Events"
    context['events'] = events
    context['baseurl'] = reverse("open")
    context['pdfurl'] = reverse('events-pdf-multi-empty')
    
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def unreviewed(request,start=None,end=None):
    context = RequestContext(request)
    
    now = datetime.datetime.now(pytz.utc)
    #events = Event.objects.filter(approved=True).filter(paid=True)
    events = Event.objects.filter(Q(closed=False)|Q(cancelled=False)).filter(reviewed=False).filter(datetime_end__lte=now)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Events Pending Billing Review"
    context['events'] = events
    context['baseurl'] = reverse("unreviewed")
    context['pdfurl'] = reverse('events-pdf-multi-empty')
    
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def unbilled(request,start=None,end=None):
    context = RequestContext(request)
    
    #events = Event.objects.filter(approved=True).filter(paid=True)
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=3652.5)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=3652.5)
        end = end.strftime('%Y-%m-%d')
    events = Event.objects.filter(billings__isnull=True).filter(Q(closed=False)|Q(cancelled=False)).filter(reviewed=True).order_by('datetime_start')
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Events to be Billed"
    context['events'] = events
    context['baseurl'] = reverse("unbilled")
    context['pdfurl'] = reverse('events-pdf-multi-empty')
    
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def paid(request,start=None,end=None):
    context = RequestContext(request)
    
    #events = Event.objects.filter(approved=True).filter(paid=True)
    events = Event.objects.filter(billings__date_paid__isnull=False).filter(Q(closed=False)|Q(cancelled=False)).filter(reviewed=True)
    events,context = datefilter(events,context,start,end)
    
    #if events:
    #    events = events.latest('billings__date_paid') #limit further
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Paid Events"
    context['events'] = events
    context['baseurl'] = reverse("paid")
    context['pdfurl'] = reverse('events-pdf-multi-empty')
    
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def unpaid(request,start=None,end=None):
    context = RequestContext(request)
    
    if not start and not end:
        start,end = get_farback_date_range_plus_next_week()
    
    today = datetime.date.today()
    now = time.time()
    #events = Event.objects.filter(approved=True).filter(time_setup_start__lte=datetime.datetime.now()).filter(date_setup_start__lte=today)
    events = Event.objects.filter(billings__date_paid__isnull=True,billings__date_billed__isnull=False).filter(Q(closed=False)|Q(cancelled=False)).filter(reviewed=True)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Pending Payments"
    context['events'] = events
    context['baseurl'] = reverse("unpaid")
    context['pdfurl'] = reverse('events-pdf-multi-empty')
    
    return render_to_response('events.html', context)    


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def closed(request,start=None,end=None):
    context = RequestContext(request)
    
    if not start and not end:
        start,end = get_farback_date_range_plus_next_week()
     
    events = Event.objects.filter(closed=True)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)
    
    
    context['h2'] = "Closed Events"
    context['events'] = events
    context['baseurl'] = reverse("closed")
    context['pdfurl'] = reverse('events-pdf-multi-empty')
    
    return render_to_response('events.html', context)       


    
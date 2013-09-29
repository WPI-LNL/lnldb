# Create your views here.

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.models import Event,Organization

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_officer

import datetime,time

DEFAULT_ENTRY_COUNT = 15

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
            eventqs = eventqs.filter(datetime_end__lte=enddate)
            
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

### EVENT VIEWS
# these more or less do what they say on the tin. Might need some work and refinement
@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def upcoming(request,start=None,end=None):
    """
    Lists Upcoming Events
    if limit = False, then it'll show all upcoming events that are more than a week away.
    """
    context = RequestContext(request)
    
    #events = Event.objects.filter(approved=True).filter(closed=False).filter(paid=False).filter(datetime_start__gte=today)
    events = Event.objects.filter(approved=True).filter(closed=False)#.filter(paid=False)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)
    
    context['h2'] = "Upcoming Workorders"
    context['events'] = events
    context['baseurl'] = reverse("upcoming")
    
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def incoming(request,start=None,end=None):
    context = RequestContext(request)
    
    events = Event.objects.filter(approved=False).filter(closed=False)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Incoming Workorders"
    context['events'] = events
    context['baseurl'] = reverse("incoming")
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def openworkorders(request,start=None,end=None):
    context = RequestContext(request)
    
    events = Event.objects.filter(closed=False)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Open Workorders"
    context['events'] = events
    context['baseurl'] = reverse("open")
    return render_to_response('events.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def unbilled(request,start=None,end=None):
    context = RequestContext(request)
    
    #events = Event.objects.filter(approved=True).filter(paid=True)
    events = Event.objects.filter(billings__isnull=True).filter(closed=False)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Paid Workorders"
    context['events'] = events
    context['baseurl'] = reverse("paid")
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def paid(request,start=None,end=None):
    context = RequestContext(request)
    
    #events = Event.objects.filter(approved=True).filter(paid=True)
    events = Event.objects.filter(billings__date_paid__isnull=False).filter(closed=False)
    events,context = datefilter(events,context,start,end)
    
    #if events:
    #    events = events.latest('billings__date_paid') #limit further
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "Paid Workorders"
    context['events'] = events
    context['baseurl'] = reverse("paid")
    return render_to_response('events.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def unpaid(request,start=None,end=None):
    context = RequestContext(request)
    
    today = datetime.date.today()
    now = time.time()
    #events = Event.objects.filter(approved=True).filter(time_setup_start__lte=datetime.datetime.now()).filter(date_setup_start__lte=today)
    events = Event.objects.filter(billings__date_paid__isnull=True,billings__date_billed__isnull=False).filter(closed=False)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)

    
    context['h2'] = "UnPaid Workorders"
    context['events'] = events
    context['baseurl'] = reverse("unpaid")
    return render_to_response('events.html', context)    


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def closed(request,start=None,end=None):
    context = RequestContext(request)
     
    events = Event.objects.filter(closed=True)
    events,context = datefilter(events,context,start,end)
    
    page = request.GET.get('page')
    events = paginate_helper(events,page)
    
    
    context['h2'] = "Closed Workorders"
    context['events'] = events
    context['baseurl'] = reverse("closed")
    return render_to_response('events.html', context)       


    
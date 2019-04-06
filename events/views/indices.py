import datetime
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from events.models import Event
from helpers.challenges import is_officer


# FRONT 3 PAGES
def index(request):
    """Landing Page"""
    context = {}

    is_off = is_officer(request.user)
    context['is_officer'] = is_off
    return render(request, 'index.html', context)


@login_required
def admin(request, msg=None):
    """ admin landing page """

    context = {}
    context['msg'] = msg

    if settings.LANDING_TIMEDELTA:
        delta = settings.LANDING_TIMEDELTA
    else:
        delta = 48

    # fuzzy delta
    today = timezone.now()
    today_min = timezone.make_aware(datetime.datetime.combine(today.date(), datetime.time.min))

    end = today + datetime.timedelta(hours=delta)
    end_max = timezone.make_aware(datetime.datetime.combine(end.date(), datetime.time.max))

    # get upcoming and ongoing events
    events = Event.objects.filter(
        Q(datetime_start__range=(today_min, end_max)) | Q(datetime_end__range=(today_min, end_max))).order_by(
        'datetime_start').filter(approved=True).exclude(Q(closed=True) | Q(cancelled=True))
    context['events'] = events

    context['tznow'] = today

    return render(request, 'admin.html', context)


@login_required
@permission_required('events.event_view_granular', raise_exception=True)
def dbg_land(request):
    context = {}
    context['env'] = os.environ
    context['meta'] = request.META
    return HttpResponse("<pre>-%s</pre>" % request.META.items())


@login_required
@permission_required('events.view_event', raise_exception=True)
def event_search(request):
    context = {}
    if request.GET:
        q = request.GET['q']
        context['q'] = q
        if len(q) < 3:
            context['msg'] = "Search Query Too Short, please try something longer"
        else:
            e = Event.objects.filter(Q(event_name__icontains=q) | Q(description__icontains=q))
            if not request.user.has_perm('events.view_hidden_event'):
                e = e.exclude(sensitive=True)
            context['events'] = e
        return render(request, 'events_search_results.html', context)
    return render(request, 'events_search_results.html', context)

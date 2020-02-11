import datetime
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from events.charts import SurveyVpChart, SurveyCrewChart, SurveyPricelistChart, SurveyLnlChart
from events.models import BaseEvent
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
    now = timezone.now()
    today_min = timezone.make_aware(datetime.datetime.combine(now.date(), datetime.time.min))

    end = now + datetime.timedelta(hours=delta)
    end_max = timezone.make_aware(datetime.datetime.combine(end.date(), datetime.time.max))

    # get upcoming and ongoing events
    events = BaseEvent.objects.filter(
        Q(datetime_start__range=(today_min, end_max)) | Q(datetime_end__range=(today_min, end_max))).order_by(
        'datetime_start').filter(approved=True).exclude(Q(closed=True) | Q(cancelled=True))
    context['events'] = events

    context['tznow'] = now

    # get ongoing events for self-crew feature
    selfcrew_events = BaseEvent.objects.filter(ccinstances__setup_start__lte=now,
        datetime_end__gte=(now - datetime.timedelta(hours=3))).exclude(hours__user=request.user).distinct()
    context['selfcrew_events'] = selfcrew_events

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
            e = BaseEvent.objects.filter(Q(event_name__icontains=q) | Q(description__icontains=q))
            if not request.user.has_perm('events.view_hidden_event'):
                e = e.exclude(sensitive=True)
            context['events'] = e
        return render(request, 'events_search_results.html', context)
    return render(request, 'events_search_results.html', context)


@login_required
@permission_required('events.view_posteventsurvey', raise_exception=True)
def survey_dashboard(request):
    now = timezone.now()
    year_ago = now - datetime.timedelta(days=365)

    context = {'chart_vp': SurveyVpChart(), 'chart_crew': SurveyCrewChart(), 'chart_pricelist': SurveyPricelistChart(), 'chart_lnl': SurveyLnlChart()}
    context['survey_composites'] = []
    context['wma'] = {
        'vp': 0,
        'crew': 0,
        'pricelist': 0,
        'overall': 0,
    }
    context['num_eligible_events'] = BaseEvent.objects \
        .filter(approved=True, datetime_start__gte=year_ago, datetime_end__lt=now) \
        .distinct().count()
    events = BaseEvent.objects \
        .filter(approved=True, datetime_start__gte=year_ago, datetime_end__lt=now) \
        .filter(surveys__isnull=False) \
        .distinct()
    context['num_events'] = events.count()
    context['response_rate'] = 0 if context['num_eligible_events'] == 0 else context['num_events'] / float(context['num_eligible_events']) * 100
    if context['num_events'] > 0:
        vp_denominator = 0
        crew_denominator = 0
        pricelist_denominator = 0
        overall_denominator = 0
        i = context['num_events']
        for event in events:
            survey_results = {}
            survey_results.update(event.surveys.filter(services_quality__gte=0).aggregate(
                Avg('services_quality'),
                Count('services_quality'),
            ))
            survey_results.update(event.surveys.filter(lighting_quality__gte=0).aggregate(
                Avg('lighting_quality'),
                Count('lighting_quality'),
            ))
            survey_results.update(event.surveys.filter(sound_quality__gte=0).aggregate(
                Avg('sound_quality'),
                Count('sound_quality'),
            ))
            survey_results.update(event.surveys.filter(work_order_experience__gte=0).aggregate(
                Avg('work_order_experience'),
                Count('work_order_experience'),
            ))
            survey_results.update(event.surveys.filter(communication_responsiveness__gte=0).aggregate(
                Avg('communication_responsiveness'),
                Count('communication_responsiveness'),
            ))
            survey_results.update(event.surveys.filter(pricelist_ux__gte=0).aggregate(
                Avg('pricelist_ux'),
                Count('pricelist_ux'),
            ))
            survey_results.update(event.surveys.filter(setup_on_time__gte=0).aggregate(
                Avg('setup_on_time'),
                Count('setup_on_time'),
            ))
            survey_results.update(event.surveys.filter(crew_respectfulness__gte=0).aggregate(
                Avg('crew_respectfulness'),
                Count('crew_respectfulness'),
            ))
            survey_results.update(event.surveys.filter(crew_preparedness__gte=0).aggregate(
                Avg('crew_preparedness'),
                Count('crew_preparedness'),
            ))
            survey_results.update(event.surveys.filter(crew_knowledgeability__gte=0).aggregate(
                Avg('crew_knowledgeability'),
                Count('crew_knowledgeability'),
            ))
            survey_results.update(event.surveys.filter(quote_as_expected__gte=0).aggregate(
                Avg('quote_as_expected'),
                Count('quote_as_expected'),
            ))
            survey_results.update(event.surveys.filter(price_appropriate__gte=0).aggregate(
                Avg('price_appropriate'),
                Count('price_appropriate'),
            ))
            survey_results.update(event.surveys.filter(customer_would_return__gte=0).aggregate(
                Avg('customer_would_return'),
                Count('customer_would_return'),
            ))
            try:
                vp = survey_results['communication_responsiveness__avg']
            except TypeError:
                vp = None
            try:
                crew = max(min(((
                    survey_results['setup_on_time__avg'] +
                    survey_results['crew_respectfulness__avg'] +
                    survey_results['crew_preparedness__avg'] +
                    survey_results['crew_knowledgeability__avg'] +
                    survey_results['lighting_quality__avg'] +
                    survey_results['sound_quality__avg']
                ) - 9) / 3, 4), 0)
            except TypeError:
                crew = None
            try:
                pricelist = max(min(((
                    survey_results['pricelist_ux__avg'] +
                    survey_results['quote_as_expected__avg'] +
                    survey_results['price_appropriate__avg']
                ) - 4.5 ) / 1.5, 4), 0)
            except TypeError:
                pricelist = None
            try:
                overall = max(min((
                    survey_results['services_quality__avg'] +
                    survey_results['customer_would_return__avg']
                ) - 3, 4), 0)
            except TypeError:
                overall = None
            context['survey_composites'].append((event, {
                'vp': vp,
                'crew': crew,
                'pricelist': pricelist,
                'overall': overall,
            }))
            if vp is not None:
                context['wma']['vp'] += i * min((vp - 1.5) * 2, 4)
                vp_denominator += i
            if crew is not None:
                context['wma']['crew'] += i * min((crew - 1.5) * 2, 4)
                crew_denominator += i
            if pricelist is not None:
                context['wma']['pricelist'] += i * min((pricelist - 1.5) * 2, 4)
                pricelist_denominator += i
            if overall is not None:
                context['wma']['overall'] += i * min((overall - 1.5) * 2, 4)
                overall_denominator += i
            i -= 1
        if vp_denominator != 0:
        	context['wma']['vp'] /= vp_denominator
        else:
        	context['wma']['vp'] = None
        
        if crew_denominator != 0:
        	context['wma']['crew'] /= crew_denominator
        else:
        	context['wma']['crew'] = None
        
        if pricelist_denominator != 0:
        	context['wma']['pricelist'] /= pricelist_denominator
        else:
        	context['wma']['pricelist'] = None
        
        if overall_denominator != 0:
        	context['wma']['overall'] /= overall_denominator
        else:
        	context['wma']['overall'] = None
    return render(request, 'survey_dashboard.html', context)
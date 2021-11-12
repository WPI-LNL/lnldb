import datetime
import os

from django.conf import settings
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render, reverse
from django.utils import timezone

from events.charts import SurveyVpChart, SurveyCrewChart, SurveyPricelistChart, SurveyLnlChart
from events.models import BaseEvent, Workshop, CrewAttendanceRecord
from helpers.challenges import is_officer
from pages.models import OnboardingScreen, OnboardingRecord
from positions.models import Position


# FRONT 3 PAGES
def index(request):
    """Landing Page"""
    context = {}

    is_off = is_officer(request.user)
    context['is_officer'] = is_off
    return render(request, 'index.html', context)


@login_required
def admin(request, msg=None):
    """ Member landing page """
    context = {'msg': msg}

    if settings.LANDING_TIMEDELTA:
        delta = settings.LANDING_TIMEDELTA
    else:
        delta = 48

    # Check for onboarding pages (if coming from an onboarding page, mark as viewed)
    referer = request.META.get('HTTP_REFERER', '')
    if not request.user.last_login:
        request.user.last_login = timezone.now()
        request.user.save()
    if request.user.is_lnl and not request.user.onboarded and \
            request.user.last_login > timezone.now() + timezone.timedelta(minutes=-1):
        request.user.last_login = timezone.now() + timezone.timedelta(minutes=-1)
        request.user.save()
        return HttpResponseRedirect(reverse("pages:new-member"))
    visited, created = OnboardingRecord.objects.get_or_create(user=request.user)
    prev_page = referer.replace('/', '').split('onboarding')
    try:
        prev_screen = OnboardingScreen.objects.filter(slug=prev_page[1]).first()
        if prev_screen:
            visited.screens.add(prev_screen)
    except IndexError:
        pass
    screens = OnboardingScreen.objects.filter(Q(users__in=[request.user]) | Q(groups__in=request.user.groups.all()))\
        .exclude(id__in=visited.screens.all())
    next_screen = screens.first()
    if next_screen:
        return HttpResponseRedirect(reverse('pages:onboarding-screen', args=[next_screen.slug]))

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
    selfcrew_events = BaseEvent.objects.filter(
        Q(closed=False) & Q(cancelled=False), ccinstances__setup_start__lte=now,
        datetime_end__gte=(now - datetime.timedelta(hours=3))).distinct()
    context['selfcrew_events'] = selfcrew_events

    open_positions = Position.objects.filter(closes__gte=datetime.datetime.now()).count()
    context['open_positions'] = open_positions

    return render(request, 'admin.html', context)


@login_required
@permission_required('events.event_view_granular', raise_exception=True)
def dbg_land(request):
    context = {}
    context['env'] = os.environ
    context['meta'] = request.META
    return HttpResponse("<pre>-%s</pre>" % request.META.items())


@login_required
@permission_required('events.view_events', raise_exception=True)
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
@permission_required('events.view_posteventsurveyresults', raise_exception=True)
def survey_dashboard(request):
    """ Dashboard for post-event survey results """
    now = timezone.now()
    year_ago = now - datetime.timedelta(days=365)

    context = {'chart_vp': SurveyVpChart(), 'chart_crew': SurveyCrewChart(), 'chart_pricelist': SurveyPricelistChart(),
               'chart_lnl': SurveyLnlChart(), 'survey_composites': [], 'wma': {'vp': 0, 'crew': 0, 'pricelist': 0,
                                                                               'overall': 0},
               'num_eligible_events': BaseEvent.objects.filter(approved=True, datetime_start__gte=year_ago,
                                                               datetime_end__lt=now).distinct().count()}
    events = BaseEvent.objects \
        .filter(approved=True, datetime_start__gte=year_ago, datetime_end__lt=now) \
        .filter(surveys__isnull=False) \
        .distinct()
    context['num_events'] = events.count()
    context['response_rate'] = 0 if context['num_eligible_events'] == 0 else \
        context['num_events'] / float(context['num_eligible_events']) * 100
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
            survey_results.update(event.surveys.filter(work_order_ease__gte=0).aggregate(
                Avg('work_order_ease'),
                Count('work_order_ease'),
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

            crew_avg = 0
            crew_count = 4
            try:
                crew_avg += survey_results['setup_on_time__avg']
            except TypeError:
                crew_count -= 1
            try:
                crew_avg += survey_results['crew_respectfulness__avg']
            except TypeError:
                crew_count -= 1
            try:
                crew_avg += survey_results['lighting_quality__avg']
            except TypeError:
                crew_count -= 1
            try:
                crew_avg += survey_results['sound_quality__avg']
            except TypeError:
                crew_count -= 1
            if crew_count == 0:
                crew = None
            else:
                crew = crew_avg/crew_count

            price_avg = 0
            price_count = 2
            try:
                price_avg += survey_results['pricelist_ux__avg']
            except TypeError:
                price_count -= 1
            try:
                price_avg += survey_results['price_appropriate__avg']
            except TypeError:
                price_count -= 1
            if price_count == 0:
                pricelist = None
            else:
                pricelist = price_avg/price_count

            overall_avg = 0
            overall_count = 2
            try:
                overall_avg += survey_results['services_quality__avg']
            except TypeError:
                overall_count -= 1
            try:
                overall_avg += survey_results['customer_would_return__avg']
            except TypeError:
                overall_count -= 1
            if overall_count == 0:
                overall = None
            else:
                overall = overall_avg/overall_count
            context['survey_composites'].append((event, {
                'vp': vp,
                'crew': crew,
                'pricelist': pricelist,
                'overall': overall,
            }))
            if vp is not None:
                context['wma']['vp'] += vp
                vp_denominator += 1
            if crew is not None:
                context['wma']['crew'] += crew
                crew_denominator += 1
            if pricelist is not None:
                context['wma']['pricelist'] += pricelist
                pricelist_denominator += 1
            if overall is not None:
                context['wma']['overall'] += overall
                overall_denominator += 1
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


def workshops(request):
    """ Public workshops page """
    context = {
        'workshops': Workshop.objects.all(),
        'title': "Workshops",
        'description': "Learn more about out our upcoming sound and lighting workshops.",
        'styles': "strong {\n\tcolor: orange;\n}\npre {\n\tfont-size: 1rem;\n\tcolor: white;\n\tfont-family: "
                  "Helvetica Neue, Helvetica, Arial, sans-serif;\n} "
    }
    return render(request, 'workshops.html', context)


@login_required
@permission_required('events.view_attendance_records', raise_exception=True)
def attendance_logs(request):
    """ View crew attendance logs (events) """

    headers = ['User', 'Event', 'Location', 'Checkin', 'Checkout']

    def get_checkin_time(data):
        return data.get('checkin')

    records = []
    for record in CrewAttendanceRecord.objects.all():
        obj = {'user': record.user, 'event': record.event, 'checkin': record.checkin, 'checkout': record.checkout}
        if not record.active and not record.checkout:
            obj['checkout'] = "UNKNOWN"
        records.append(obj)
    records.sort(key=get_checkin_time, reverse=True)

    paginator = Paginator(records, 50)
    page_number = request.GET.get('page', 1)
    current_page = paginator.get_page(page_number)
    context = {'records': current_page, 'title': 'Crew Logs', 'headers': headers}
    return render(request, 'access_log.html', context)

import datetime
import re

import pytz
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.core.urlresolvers import reverse
from django.db.models import Count, F, Q
from django.shortcuts import render
from django.utils.timezone import make_aware

from events.models import Event

DEFAULT_ENTRY_COUNT = 40


class FakeField(object):
    """
    Means that there is some check for it in the template end or that the thing is a property instead of a field
    """

    def __init__(self, name, verbose_name=None, favicon=None, sortable=False):
        self.name = name
        if verbose_name is None:
            self.verbose_name = " ".join(re.split("[-_ ]", name)).capitalize()
        else:
            self.verbose_name = verbose_name
        self.sortable = sortable
        self.favicon = favicon


class FakeExtendedField(object):
    """
    Just a shim to make things clear, using getattr magic to make python think it's the original field
    Use it if you want to change something about a field
    """

    def __getattr__(self, item):
        return getattr(self.fieldref, item)

    def __init__(self, name, favicon=None, verbose_name=None, sortable=True):
        self.fieldref = Event._meta.get_field(name)
        self.name = name
        if verbose_name:
            self.verbose_name = verbose_name
        self.sortable = sortable
        self.favicon = favicon


def map_fields(cols):
    """ Puts field names into actual fields (even if they don't exist) """

    out_cols = []
    all_names = map(lambda f: f.name, Event._meta.get_fields())

    for col in cols:
        if isinstance(col, FakeField):
            out_cols.append(col)
        elif isinstance(col, FakeExtendedField):
            out_cols.append(col)
        elif col in all_names:
            out_cols.append(FakeExtendedField(col))
        elif isinstance(col, tuple) and col[0] in all_names:
            out_cols.append(FakeExtendedField(*col))
        elif isinstance(col, tuple):
            out_cols.append(FakeField(*col))  # expand entries in col
        else:
            out_cols.append(FakeField(str(col)))
    return out_cols


# generic date filtering
def datefilter(eventqs, context, start=None, end=None):
    today = datetime.date.today()
    weekfromnow = today + datetime.timedelta(days=7)

    if start:
        context['start'] = start
        try:
            startdate = make_aware(datetime.datetime.strptime(start, '%Y-%m-%d'))
            eventqs = eventqs.filter(datetime_start__gte=startdate)

        except:
            raise
    else:
        eventqs = eventqs.filter(datetime_start__gte=today)

    if end:
        context['end'] = end
        try:
            enddate = make_aware(datetime.datetime.strptime(end, '%Y-%m-%d'))
            eventqs = eventqs.filter(datetime_end__lte=enddate)

        except:
            raise
    else:
        eventqs = eventqs.filter(datetime_end__lte=weekfromnow)

    return eventqs, context


# paginator helper

def paginate_helper(queryset, page, sort=None, count=DEFAULT_ENTRY_COUNT):
    names = map(lambda f: f.name, queryset.model._meta.get_fields())
    if sort and ((sort in names) or (sort[0] == '-' and sort[1:] in names)):
        post_sort = queryset.order_by(sort)
    elif sort:
        try:
            if sort[0] == '-':
                post_sort = sorted(queryset.all(), key=lambda m: getattr(m, sort[1:]), reverse=True)
            else:
                post_sort = sorted(queryset.all(), key=lambda m: getattr(m, sort))
        except Exception:
            # print "Won't sort.", e
            post_sort = queryset
    else:
        post_sort = queryset

    paginator = Paginator(post_sort, count)
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

    return start, end


# ## EVENT VIEWS
@login_required()
@permission_required('events.view_event', raise_exception=True)
def upcoming(request, start=None, end=None):
    """
    Lists Upcoming Events
    if limit = False, then it'll show all upcoming events that are more than a week away.
    """
    context = {}
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=1)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=15)
        end = end.strftime('%Y-%m-%d')

        # KEEPING THIS JUST IN CASE
        # today = datetime.date.today()
        # start = today.strftime('%Y-%m-%d')

        # wd = today.weekday()
        # if wd == 2: # if today is weds
        # end = today + datetime.timedelta(days=7)
        # end = end.strftime('%Y-%m-%d')
        # elif wd < 2:
        # delta = 2 - wd + 1
        # end = today + datetime.timedelta(days=delta)
        # end = end.strftime('%Y-%m-%d')
        # else:
        # # fex
        # # thurs == 3
        # # 7 - 3 + 2 = 6 days = weds
        # delta = 7 - wd + 2
        # end = today + datetime.timedelta(days=delta)
        # end = end.strftime('%Y-%m-%d')

    # events = Event.objects.filter(approved=True).filter(closed=False).filter(paid=False)
    # .filter(datetime_start__gte=today)
    events = Event.objects.filter(approved=True).exclude(
        Q(closed=True) | Q(cancelled=True)).distinct()  # .filter(paid=False)
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief')
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort') or 'datetime_start'
    events = paginate_helper(events, page, sort)

    context['h2'] = "Upcoming Events"
    context['events'] = events
    context['baseurl'] = reverse("events:upcoming")
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       'crew_chief',
                       FakeExtendedField('datetime_start', verbose_name="Starts At"),
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)


@login_required
@permission_required('events.approve_event', raise_exception=True)
def incoming(request, start=None, end=None):
    context = {}
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=365.25)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=365.25)
        end = end.strftime('%Y-%m-%d')

    events = Event.objects.filter(approved=False).exclude(Q(closed=True) | Q(cancelled=True)) \
        .distinct()
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices')
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort') or 'datetime_start'
    events = paginate_helper(events, page, sort)

    context['h2'] = "Incoming Events"
    context['events'] = events
    context['baseurl'] = reverse("events:incoming")
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       'submitted_on',
                       FakeExtendedField('datetime_start', verbose_name="Starts At"),
                       FakeField('short_services', verbose_name="Services", sortable=False)]

    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)


@login_required
@permission_required('events.view_event', raise_exception=True)
def openworkorders(request, start=None, end=None):
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=3652.5)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=3652.5)
        end = end.strftime('%Y-%m-%d')
    context = {}

    events = Event.objects.filter(approved=True).exclude(Q(closed=True) | Q(cancelled=True)).distinct()
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('billings') \
        .prefetch_related('crew_chief')
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort')
    events = paginate_helper(events, page, sort)

    context['h2'] = "Open Events"
    context['events'] = events
    context['baseurl'] = reverse("events:open")
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       'crew_chief',
                       FakeExtendedField('datetime_start', verbose_name="Starting At"),
                       FakeField('short_services', verbose_name="Services", sortable=False),
                       FakeField('tasks')]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)


@login_required()
@permission_required('events.view_event', raise_exception=True)
def findchief(request, start=None, end=None):
    if not start and not end:
        today = datetime.date.today()
        start = today
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=30.5)
        end = end.strftime('%Y-%m-%d')
    context = {}

    events = Event.objects \
        .filter(approved=True).filter(closed=False).filter(cancelled=False) \
        .annotate(num_ccs=Count('ccinstances')) \
        .annotate(services_count=Count('otherservices')) \
        .annotate(lighting_count=Count('lighting')) \
        .annotate(sound_count=Count('sound')) \
        .annotate(projection_count=Count('projection')).all() \
        .filter(num_ccs__lt=(F('ccs_needed'))).distinct()

    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief')
    if request.GET.get('hidedp') and not request.GET.get('hidedp') == '0':
        events = events.exclude(Q(projection__shortname='DP') & Q(lighting__isnull=True) & Q(sound__isnull=True))

    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort') or 'datetime_start'
    events = paginate_helper(events, page, sort)

    context['h2'] = "Needs a Crew Chief"
    context['proj_hideable'] = True
    context['events'] = events
    context['baseurl'] = reverse("events:findchief")
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       FakeExtendedField('datetime_start', verbose_name="Starting At"),
                       'submitted_on',
                       'num_ccs',
                       FakeField('eventcount', verbose_name="# Services"),
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)


@login_required
@permission_required('events.review_event', raise_exception=True)
def unreviewed(request, start=None, end=None):
    context = {}

    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=180)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=180)
        end = end.strftime('%Y-%m-%d')

    now = datetime.datetime.now(pytz.utc)
    # events = Event.objects.filter(approved=True).filter(paid=True)
    events = Event.objects.exclude(Q(closed=True) |
                                   Q(cancelled=True) |
                                   Q(approved=False)) \
        .filter(reviewed=False) \
        .filter(datetime_end__lte=now) \
        .order_by('datetime_start') \
        .prefetch_related('crew_chief') \
        .distinct()
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief')
    if not request.GET.get('hidedp') == '0':
        events = events.exclude(Q(projection__shortname='DP') & Q(lighting__isnull=True) & Q(sound__isnull=True))
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort')
    events = paginate_helper(events, page, sort)

    context['h2'] = "Events Pending Billing Review"
    context['events'] = events
    context['baseurl'] = reverse("events:unreviewed")
    context['pdfurl'] = reverse('events:pdf-multi')
    context['proj_hideable'] = True
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       'crew_chief',
                       FakeField('num_crew_needing_reports', sortable=True, verbose_name="Missing Reports"),
                       FakeField('short_services', verbose_name="Services", sortable=False),
                       FakeField('tasks')]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unbilled(request, start=None, end=None):
    context = {}

    # events = Event.objects.filter(approved=True).filter(paid=True)
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=3652.5)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=3652.5)
        end = end.strftime('%Y-%m-%d')

    events = Event.objects.filter(billings__isnull=True) \
        .exclude(Q(closed=True) |
                 Q(cancelled=True)) \
        .filter(reviewed=True) \
        .filter(billed_by_semester=False) \
        .order_by('datetime_start') \
        .distinct()
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('billings')
    if request.GET.get('hidedp') and not request.GET.get('hidedp') == '0':
        events = events.exclude(Q(projection__shortname='DP') & Q(lighting__isnull=True) & Q(sound__isnull=True))
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort')
    events = paginate_helper(events, page, sort)

    context['h2'] = "Events to be Billed"
    context['events'] = events
    context['baseurl'] = reverse("events:unbilled")
    context['proj_hideable'] = True
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       FakeField('num_crew_needing_reports', sortable=True, verbose_name="Missing Reports"),
                       FakeField('short_services', verbose_name="Services", sortable=False), ]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unbilled_semester(request, start=None, end=None):
    context = {}

    # events = Event.objects.filter(approved=True).filter(paid=True)
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=3652.5)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=3652.5)
        end = end.strftime('%Y-%m-%d')
    events = Event.objects.filter(billings__isnull=True) \
        .exclude(Q(closed=True) |
                 Q(cancelled=True)) \
        .filter(reviewed=True) \
        .filter(billed_by_semester=True) \
        .order_by('datetime_start') \
        .distinct()
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('billings')
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort')
    events = paginate_helper(events, page, sort)

    context['h2'] = "Events to be Billed (Films)"
    context['events'] = events
    context['baseurl'] = reverse("events:unbilled-semester")
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       'crew_chief',
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)


@login_required
@permission_required('events.close_event', raise_exception=True)
def paid(request, start=None, end=None):
    context = {}

    if not start and not end:
        start, end = get_farback_date_range_plus_next_week()

    # events = Event.objects.filter(approved=True).filter(paid=True)
    events = Event.objects.filter(billings__date_paid__isnull=False) \
        .exclude(Q(closed=True) |
                 Q(cancelled=True)) \
        .filter(reviewed=True) \
        .distinct()
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('billings')
    if request.GET.get('hidedp') and not request.GET.get('hidedp') == '0':
        events = events.exclude(Q(projection__shortname='DP') & Q(lighting__isnull=True) & Q(sound__isnull=True))
    events, context = datefilter(events, context, start, end)

    # if events:
    # events = events.latest('billings__date_paid') # limit further

    page = request.GET.get('page')
    sort = request.GET.get('sort')
    events = paginate_helper(events, page, sort)

    context['h2'] = "Paid Events"
    context['events'] = events
    context['baseurl'] = reverse("events:paid")
    context['pdfurl'] = reverse('events:pdf-multi')
    context['proj_hideable'] = True
    context['cols'] = ['event_name',
                       'org',
                       FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       FakeField('last_billed', sortable=True),
                       FakeField('last_paid', verbose_name="Paid On", sortable=True),
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings

    return render(request, 'events.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unpaid(request, start=None, end=None):
    context = {}

    if not start and not end:
        start, end = get_farback_date_range_plus_next_week()

    # events = Event.objects.filter(approved=True).filter(time_setup_start__lte=datetime.datetime.now())
    # .filter(date_setup_start__lte=today)
    events = Event.objects.annotate(numpaid=Count('billings__date_paid')) \
        .filter(billings__date_billed__isnull=False) \
        .exclude(closed=True) \
        .exclude(cancelled=True) \
        .exclude(numpaid__gt=0) \
        .filter(reviewed=True) \
        .order_by('datetime_start').distinct()
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('billings')
    if request.GET.get('hidedp') and not request.GET.get('hidedp') == '0':
        events = events.exclude(Q(projection__shortname='DP') & Q(lighting__isnull=True) & Q(sound__isnull=True))
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort')
    events = paginate_helper(events, page, sort)

    context['h2'] = "Pending Payments"
    context['events'] = events
    context['baseurl'] = reverse("events:unpaid")
    context['proj_hideable'] = True
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       FakeField('last_billed', sortable=True),
                       FakeField('times_billed', sortable=True),
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)


@login_required
@permission_required('events.view_event', raise_exception=True)
def closed(request, start=None, end=None):
    context = {}

    if not start and not end:
        start, end = get_farback_date_range_plus_next_week()

    events = Event.objects.filter(closed=True)
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('crew_chief')
    if request.GET.get('hidedp') and not request.GET.get('hidedp') == '0':
        events = events.exclude(Q(projection__shortname='DP') & Q(lighting__isnull=True) & Q(sound__isnull=True))
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort')
    events = paginate_helper(events, page, sort)

    context['h2'] = "Closed Events"
    context['events'] = events
    context['baseurl'] = reverse("events:closed")
    context['proj_hideable'] = True
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       'crew_chief',
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    # print context['cols']
    return render(request, 'events.html', context)


@login_required
@permission_required('events.view_event', raise_exception=True)
def all(request, start=None, end=None):
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=3652.5)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=3652.5)
        end = end.strftime('%Y-%m-%d')
    context = {}

    events = Event.objects.distinct()
    if not request.user.has_perm('events.event_view_sensitive'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.event_view_debug'):
        events = events.exclude(test_event=True)
    if not request.user.has_perm('events.approve_event'):
        events = events.exclude(approved=False)
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('billings') \
        .prefetch_related('crew_chief')
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort')
    events = paginate_helper(events, page, sort)

    context['h2'] = "All Events"
    context['events'] = events
    context['baseurl'] = reverse("events:all")
    context['pdfurl'] = reverse('events:pdf-multi')
    context['cols'] = ['event_name',
                       'org',
                       'location',
                       'crew_chief',
                       FakeExtendedField('datetime_start', verbose_name="Starting At"),
                       FakeField('short_services', verbose_name="Services", sortable=False),
                       FakeField('tasks')]
    if request.user.has_perm('events.approve_event'):
        context['cols'].append('approved')
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'events.html', context)

def public_facing(request):
    context = {}
    now = datetime.datetime.now(pytz.utc)
    events = Event.objects.filter(approved=True, closed=False, cancelled=False, test_event=False, sensitive=False) \
        .filter(datetime_end__gte=now)
    events = events.order_by('datetime_start')
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('otherservices').prefetch_related('ccinstances__crew_chief')
    context['h2'] = "Active Events"
    context['events'] = events

    return render(request, "events_public.html", context)

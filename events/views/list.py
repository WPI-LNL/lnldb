import datetime
import re

import pytz
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, F, Q, Sum, Case, When, IntegerField
from django.forms.models import modelformset_factory
from django.http.response import HttpResponseRedirect
from django.views.generic.edit import DeleteView
from django.shortcuts import render
from django.urls.base import reverse
from django.utils.http import urlencode
from django.utils.timezone import make_aware

from helpers.mixins import HasPermMixin, LoginRequiredMixin, SetFormMsgMixin
from events.models import BaseEvent, Event2019, Category, MultiBilling, Workshop, WorkshopDate
from events.forms import WorkshopForm, WorkshopDatesForm

DEFAULT_ENTRY_COUNT = 40
DATEFILTER_COOKIE_MAX_AGE = 600


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

    def __init__(self, name, model=BaseEvent, favicon=None, verbose_name=None, sortable=True):
        self.fieldref = model._meta.get_field(name)
        self.name = name
        if verbose_name:
            self.verbose_name = verbose_name
        self.sortable = sortable
        self.favicon = favicon


def map_fields(cols):
    """ Puts field names into actual fields (even if they don't exist) """

    out_cols = []
    all_names = map(lambda f: f.name, BaseEvent._meta.get_fields())

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


def datefilter(eventqs, context, start=None, end=None):
    """ Generic date filtering """
    today = datetime.date.today()
    weekfromnow = today + datetime.timedelta(days=7)

    if start:
        context['start'] = start
        startdate = make_aware(datetime.datetime.strptime(start, '%Y-%m-%d'))
        eventqs = eventqs.filter(datetime_start__gte=startdate)

    if end:
        context['end'] = end
        enddate = make_aware(datetime.datetime.strptime(end, '%Y-%m-%d'))
        eventqs = eventqs.filter(datetime_end__lte=enddate)

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


# currently this function is dead code
# def get_farback_date_range_plus_next_week(delta=180):
#     today = datetime.date.today()
#     end = today + datetime.timedelta(days=7)
#     end = end.strftime('%Y-%m-%d')
#     start = today - datetime.timedelta(days=delta)
#     start = start.strftime('%Y-%m-%d')
#     return start, end


def get_very_large_date_range():
    """ Helper function to return start and end that go very far into past and future """
    today = datetime.date.today()
    start = today - datetime.timedelta(days=3652.5)
    start = start.strftime('%Y-%m-%d')
    end = today + datetime.timedelta(days=3652.5)
    end = end.strftime('%Y-%m-%d')
    return start, end


def build_redirect(request, **kwargs):
    """ Add query string to URL """
    return HttpResponseRedirect(request.path + '?' + urlencode(kwargs))


def filter_events(request, context, events, start, end, prefetch_org=False, prefetch_cc=False, prefetch_billing=False,
                  hide_unapproved=False, event2019=False, sort='-datetime_start'):
    """
    Filter a queryset of events based on specified criteria

    :param request: The calling view's request object
    :param context: The calling view's current context dictionary
    :param events: Queryset of events to filter
    :param start: Datetime to compare event start times to
    :param end: Datetime to compare event end times to
    :param prefetch_org: Boolean - If true, prefetch related items based on client
    :param prefetch_cc: Boolean - If true, prefetch related items based on client or crew chiefs and select related \
    items based on building
    :param prefetch_billing: Boolean - If true, prefetch related items based on client or crew chiefs and select \
    related items based on building
    :param hide_unapproved: Boolean - If true, exclude events that have not been approved
    :param event2019: Boolean - If true, queryset only contains Event2019 objects
    :param sort: String - Default field to sort by (prepend "-" for reverse)
    :returns: Queryset of events and updated context dictionary
    """
    if not request.user.has_perm('events.view_hidden_event'):
        events = events.exclude(sensitive=True)
    if not request.user.has_perm('events.view_test_event'):
        events = events.exclude(test_event=True)
    if not request.user.has_perm('events.approve_event') and hide_unapproved:
        events = events.exclude(approved=False)
    if prefetch_billing or prefetch_cc:
        events = events.select_related('location__building').prefetch_related('org')\
            .prefetch_related('ccinstances__crew_chief')
    elif prefetch_org:
        events = events.prefetch_related('org')
    else:
        events = events.select_related('location__building').prefetch_related('org')
    if event2019:
        if request.GET.get('projection') == 'hide':
            events = events.exclude(
                Q(serviceinstance__service__category__name='Projection') &
                ~Q(serviceinstance__service__category__name__in=Category.objects.exclude(name='Projection')
                   .values_list('name', flat=True))
            )
        elif request.GET.get('projection') == 'only':
            events = events.filter(serviceinstance__service__category__name='Projection')
    else:
        if request.GET.get('projection') == 'hide':
            events = events.exclude(
                (Q(Event___projection__isnull=False, Event___lighting__isnull=True, Event___sound__isnull=True) |
                 Q(serviceinstance__service__category__name='Projection')) &
                ~Q(serviceinstance__service__category__name__in=Category.objects.exclude(name='Projection')
                   .values_list('name', flat=True))
            )
        elif request.GET.get('projection') == 'only':
            events = events.filter(Q(Event___projection__isnull=False) |
                                   Q(serviceinstance__service__category__name='Projection'))
    events, context = datefilter(events, context, start, end)

    page = request.GET.get('page')
    sort = request.GET.get('sort') or sort
    events = paginate_helper(events, page, sort)
    context['pagninate_next_label'] = "Older" if '-datetime_start' in sort else "Newer"
    context['pagninate_last_label'] = "Newer" if '-datetime_start' in sort else "Older"                                                                 
    return events, context


def generate_response(request, context, start, end, time_range_unspecified):
    """
    Build an event list view response object and set cookies if necessary

    :param request: The calling view's request object
    :param context: The calling view's context dictionary
    :param start: Datetime used to filter the events (Optional)
    :param end: Datetime used to filter the events (Optional)
    :param time_range_unspecified: Boolean - If true, will ignore start and end times
    :returns: Response object
    """
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    response = render(request, 'events.html', context)

    if request.GET.get('projection') and request.GET['projection'] != request.COOKIES.get('projection'):
        response.set_cookie('projection', request.GET['projection'])
    if not time_range_unspecified and (start != request.COOKIES.get('start') or end != request.COOKIES.get('end')):
        response.set_cookie('start', start, max_age=DATEFILTER_COOKIE_MAX_AGE)
        response.set_cookie('end', end, max_age=DATEFILTER_COOKIE_MAX_AGE)
    return response


# ## EVENT VIEWS
@login_required
@permission_required('events.view_events', raise_exception=True)
def upcoming(request, start=None, end=None):
    """
    Lists Upcoming Events

    If start and end are both None, then it'll show all upcoming events for the next 15 days
    """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:upcoming',
                                                args=(request.COOKIES.get('start'), request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:upcoming', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:upcoming', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=1)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=15)
        end = end.strftime('%Y-%m-%d')

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.filter(Q(approved=True) & Q(closed=False) & Q(cancelled=False)).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_cc=True, sort='datetime_start')

    context['h2'] = "Upcoming Events"
    context['events'] = events
    context['baseurl'] = reverse("events:upcoming")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('cal:list')
    context['takes_param_projection'] = True
    context['cols'] = ['event_name', 'org', 'location', 'crew_chief',
                       FakeExtendedField('datetime_start', verbose_name="Starts At"),
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.approve_event', raise_exception=True)
def incoming(request, start=None, end=None):
    """ Lists all incoming events (not yet approved) """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:incoming', args=(request.COOKIES.get('start'),
                                                                         request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:incoming', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:incoming', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=365.25)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=365.25)
        end = end.strftime('%Y-%m-%d')

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.filter(approved=False).exclude(Q(closed=True) | Q(cancelled=True)).distinct()
    events, context = filter_events(request, context, events, start, end, sort='datetime_start')

    context['h2'] = "Incoming Events"
    context['events'] = events
    context['baseurl'] = reverse("events:incoming")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:incoming-cal')
    context['takes_param_projection'] = True
    context['cols'] = ['event_name', 'org', 'location', 'submitted_on',
                       FakeExtendedField('datetime_start', verbose_name="Starts At"),
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.approve_event', raise_exception=True)
def incoming_cal(request, start=None, end=None):
    """ Calendar view of incoming events """
    context = {'h2': "Incoming Events", 'listurl': reverse('events:incoming'),
               'bootcal_endpoint': reverse('cal:api-incoming')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.view_events', raise_exception=True)
def openworkorders(request, start=None, end=None):
    """ Lists open events (not cancelled or otherwise closed) """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:open', args=(request.COOKIES.get('start'),
                                                                     request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:open', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:open', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        start, end = get_very_large_date_range()

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.filter(approved=True, closed=False, cancelled=False).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_billing=True, sort='datetime_start')

    context['h2'] = "Open Events"
    context['events'] = events
    context['baseurl'] = reverse("events:open")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:open-cal')
    context['takes_param_projection'] = True
    context['cols'] = ['event_name', 'org', 'location', 'crew_chief',
                       FakeExtendedField('datetime_start', verbose_name="Starting At"),
                       FakeField('short_services', verbose_name="Services", sortable=False), FakeField('tasks')]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.view_events', raise_exception=True)
def openworkorders_cal(request, start=None, end=None):
    """ Calendar view for open events """
    context = {'h2': "Open Events", 'listurl': reverse('events:open'), 'bootcal_endpoint': reverse('cal:api-open')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.view_events', raise_exception=True)
def findchief(request, start=None, end=None):
    """ Lists any events that have been approved and need crew chiefs """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:findchief', args=(request.COOKIES.get('start'),
                                                                          request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:findchief', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:findchief', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        today = datetime.date.today()
        start = today
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=30.5)
        end = end.strftime('%Y-%m-%d')

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.filter(approved=True).filter(closed=False).filter(cancelled=False)\
        .annotate(num_ccs=Count('ccinstances'))\
        .filter(Q(Event___ccs_needed__gt=F('num_ccs')) |
                Q(num_ccs__lt=Count('serviceinstance__service__category', distinct=True))).distinct()

    events, context = filter_events(request, context, events, start, end, prefetch_cc=True, sort='datetime_start')

    context['h2'] = "Needs a Crew Chief"
    context['takes_param_projection'] = True
    context['events'] = events
    context['baseurl'] = reverse("events:findchief")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:findchief-cal')
    context['cols'] = ['event_name', 'org', 'location', FakeExtendedField('datetime_start', verbose_name="Starting At"),
                       'submitted_on', 'num_ccs', FakeField('eventcount', verbose_name="# Services"),
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.view_events', raise_exception=True)
def findchief_cal(request, start=None, end=None):
    """ Calendar view for events that need crew chiefs """
    context = {'h2': "Needs a Crew Chief", 'listurl': reverse('events:findchief'),
               'bootcal_endpoint': reverse('cal:api-findchief')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.review_event', raise_exception=True)
def unreviewed(request, start=None, end=None):
    """ Lists events that are pending review for billing """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:unreviewed', args=(request.COOKIES.get('start'),
                                                                           request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:unreviewed', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:unreviewed', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        today = datetime.date.today()
        start = today - datetime.timedelta(days=180)
        start = start.strftime('%Y-%m-%d')
        end = today + datetime.timedelta(days=180)
        end = end.strftime('%Y-%m-%d')

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    now = datetime.datetime.now(pytz.utc)
    events = BaseEvent.objects.filter(approved=True, closed=False, cancelled=False).filter(reviewed=False)\
        .filter(datetime_end__lte=now).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_cc=True, sort='datetime_start')

    context['h2'] = "Events Pending Billing Review"
    context['events'] = events
    context['baseurl'] = reverse("events:unreviewed")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    # context['calurl'] = reverse('events:unreviewed-cal')
    context['takes_param_projection'] = True
    context['cols'] = ['event_name', 'org', 'location', FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       'crew_chief',
                       FakeField('num_crew_needing_reports', sortable=True, verbose_name="Missing Reports"),
                       FakeField('short_services', verbose_name="Services", sortable=False), FakeField('tasks')]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.review_event', raise_exception=True)
def unreviewed_cal(request, start=None, end=None):
    """ Calendar view for events that are ready to be reviewed for billing """
    context = {'h2': "Events Pending Billing Review", 'listurl': reverse('events:unreviewed'),
               'bootcal_endpoint': reverse('cal:api-unreviewed')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unbilled(request, start=None, end=None):
    """ Lists events that are ready to be billed """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:unbilled', args=(request.COOKIES.get('start'),
                                                                         request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:unbilled', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:unbilled', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        start, end = get_very_large_date_range()

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.filter(closed=False).filter(reviewed=True)\
        .filter(billings__isnull=True, multibillings__isnull=True).filter(billed_in_bulk=False).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_billing=True, sort='datetime_start')
    context['h2'] = "Events to be Billed"
    context['events'] = events
    context['baseurl'] = reverse("events:unbilled")
    context['takes_param_projection'] = True
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:unbilled-cal')
    context['cols'] = ['event_name', 'org', 'location', FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       FakeField('num_crew_needing_reports', sortable=True, verbose_name="Missing Reports"),
                       FakeField('short_services', verbose_name="Services", sortable=False)]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unbilled_cal(request, start=None, end=None):
    """ Calendar view for events that have yet to be billed """
    context = {'h2': "Events to be Billed", 'listurl': reverse('events:unbilled'),
               'bootcal_endpoint': reverse('cal:api-unbilled')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unbilled_semester(request, start=None, end=None):
    """ Lists events that have yet to be billed and are set to be billed in bulk """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:unbilled-semester', args=(request.COOKIES.get('start'),
                                                                                  request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:unbilled-semester', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:unbilled-semester', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        start, end = get_very_large_date_range()

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.filter(closed=False).filter(reviewed=True)\
        .filter(billings__isnull=True, multibillings__isnull=True).filter(billed_in_bulk=True).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_billing=True, sort='datetime_start')

    context['h2'] = "Events to be Billed in Bulk"
    context['events'] = events
    context['baseurl'] = reverse("events:unbilled-semester")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:unbilled-semester-cal')
    context['takes_param_projection'] = True
    context['cols'] = ['event_name', 'org', 'location', FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       'crew_chief', FakeField('short_services', verbose_name="Services", sortable=False)]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unbilled_semester_cal(request, start=None, end=None):
    """ Calendar view for events that have yet to be billed and are set to be billed in bulk """
    context = {'h2': "Events to be Billed in Bulk", 'listurl': reverse('events:unbilled-semester'),
               'bootcal_endpoint': reverse('cal:api-unbilled-semester')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.close_event', raise_exception=True)
def paid(request, start=None, end=None):
    """ Lists events where all bills have been paid """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:paid', args=(request.COOKIES.get('start'),
                                                                     request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:paid', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:paid', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        start, end = get_very_large_date_range()

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    # events = Event.objects.filter(approved=True).filter(paid=True)
    events = BaseEvent.objects.filter(closed=False).filter(Q(billings__date_paid__isnull=False) |
                                                           Q(multibillings__date_paid__isnull=False)).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_billing=True)

    context['h2'] = "Paid Events"
    context['events'] = events
    context['baseurl'] = reverse("events:paid")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:paid-cal')
    context['takes_param_projection'] = True
    context['cols'] = ['event_name', 'org', FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       FakeField('last_billed', sortable=True),
                       FakeField('last_paid', verbose_name="Paid On", sortable=True),
                       FakeField('short_services', verbose_name="Services", sortable=False), FakeField('workday')]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.close_event', raise_exception=True)
def paid_cal(request, start=None, end=None):
    """ Calendar view for events that have already been paid """
    context = {'h2': "Paid Events", 'listurl': reverse('events:paid'), 'bootcal_endpoint': reverse('cal:api-paid')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unpaid(request, start=None, end=None):
    """ Lists events that have unpaid bills """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:unpaid', args=(request.COOKIES.get('start'),
                                                                       request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:unpaid', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:unpaid', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.annotate(numpaid=Count('billings__date_paid')+Count('multibillings__date_paid'))\
        .filter(Q(billings__isnull=False) | Q(multibillings__isnull=False)).exclude(closed=True)\
        .exclude(numpaid__gt=0).filter(reviewed=True) \
        .exclude(billings__isnull=False, Event2019___workday_fund__isnull=False, Event2019___worktag__isnull=False) \
        .exclude(billings__isnull=False, Event2019___entered_into_workday=True).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_billing=True, sort='datetime_start')

    context['h2'] = "Pending Payments"
    context['events'] = events
    context['baseurl'] = reverse("events:unpaid")
    context['takes_param_projection'] = True
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:unpaid-cal')
    context['cols'] = ['event_name', 'org', FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       FakeField('last_billed', sortable=True), FakeField('times_billed', sortable=True),
                       FakeField('cost_total', verbose_name='Price', sortable=True), FakeField('tasks')]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unpaid_cal(request, start=None, end=None):
    """ Calendar view for events that have unpaid bills """
    context = {'h2': "Pending Payments", 'listurl': reverse('events:unpaid'),
               'bootcal_endpoint': reverse('cal:api-unpaid')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def awaitingworkday(request, start=None, end=None):
    """ Lists events that are waiting to be entered into Workday """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:awaitingworkday', args=(request.COOKIES.get('start'),
                                                                                request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:awaitingworkday', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:awaitingworkday', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = Event2019.objects.filter(closed=False)\
        .filter(reviewed=True, billings__isnull=False, workday_fund__isnull=False, worktag__isnull=False,
                entered_into_workday=False) \
        .exclude(Q(billings__date_paid__isnull=False) | Q(multibillings__date_paid__isnull=False)).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_billing=True, event2019=True, sort='datetime_start')

    context['h2'] = "Events to Enter Into Workday"
    context['events'] = events
    context['baseurl'] = reverse("events:awaitingworkday")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['takes_param_projection'] = True
    context['cols'] = [FakeField('cost_total', verbose_name='Extended Amount'),
                       FakeField('contact', verbose_name='Requester'),
                       FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       FakeField('workday_memo', verbose_name='Memo'), 'org', 'workday_fund', 'worktag',
                       'workday_form_comments', FakeField('bill'), FakeField('tasks')]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.bill_event', raise_exception=True)
def unpaid_workday(request, start=None, end=None):
    """ Lists events that have been entered into workday but have not yet been paid for """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:unpaid-workday', args=(request.COOKIES.get('start'),
                                                                               request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:unpaid-workday', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:unpaid-workday', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = Event2019.objects.annotate(numpaid=Count('billings__date_paid')+Count('multibillings__date_paid')) \
        .filter(closed=False, reviewed=True, entered_into_workday=True).exclude(numpaid__gt=0).distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_org=True, event2019=True, sort='datetime_start')

    context['h2'] = "Pending Workday ISDs"
    context['events'] = events
    context['baseurl'] = reverse("events:unpaid-workday")
    context['takes_param_projection'] = True
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['cols'] = ['event_name', 'org', FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       'workday_fund', 'worktag', 'workday_form_comments', FakeField('tasks')]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.view_events', raise_exception=True)
def closed(request, start=None, end=None):
    """ Lists closed events """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:closed', args=(request.COOKIES.get('start'),
                                                                       request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:closed', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:closed', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        start, end = get_very_large_date_range()

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.filter(closed=True)
    events, context = filter_events(request, context, events, start, end, prefetch_cc=True)

    context['h2'] = "Closed Events"
    context['events'] = events
    context['baseurl'] = reverse("events:closed")
    context['takes_param_projection'] = True
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:closed-cal')
    context['cols'] = ['event_name', 'org', 'location', FakeExtendedField('datetime_start', verbose_name="Event Time"),
                       'crew_chief', FakeField('short_services', verbose_name="Services", sortable=False)]
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required
@permission_required('events.view_events', raise_exception=True)
def closed_cal(request, start=None, end=None):
    """ Calendar view for closed events """
    context = {'h2': "Closed Events", 'listurl': reverse('events:closed'),
               'bootcal_endpoint': reverse('cal:api-closed')}
    return render(request, 'events_cal.html', context)


@login_required
@permission_required('events.view_events', raise_exception=True)
def all(request, start=None, end=None):
    """ Lists all events """
    context = {}

    if not start and request.COOKIES.get('start'):
        if not end and request.COOKIES.get('end'):
            return HttpResponseRedirect(reverse('events:all', args=(request.COOKIES.get('start'),
                                                                    request.COOKIES.get('end'))))
        else:
            return HttpResponseRedirect(reverse('events:all', args=(request.COOKIES.get('start'), end)))
    elif not end and request.COOKIES.get('end'):
        return HttpResponseRedirect(reverse('events:all', args=(start, request.COOKIES.get('end'))))
    time_range_unspecified = not start and not end
    if not start and not end:
        start, end = get_very_large_date_range()

    if (not request.GET.get('projection') and request.COOKIES.get('projection')
            and request.COOKIES['projection'] != 'show'):
        return build_redirect(request, projection=request.COOKIES['projection'], **request.GET.dict())

    events = BaseEvent.objects.distinct()
    events, context = filter_events(request, context, events, start, end, prefetch_billing=True, hide_unapproved=True)

    context['h2'] = "All Events"
    context['events'] = events
    context['baseurl'] = reverse("events:all")
    context['pdfurl_workorders'] = reverse('events:pdf-multi')
    context['pdfurl_bills'] = reverse('events:bill-pdf-multi')
    context['calurl'] = reverse('events:all-cal')
    context['takes_param_projection'] = True
    context['cols'] = ['event_name', 'org', 'location', 'crew_chief',
                       FakeExtendedField('datetime_start', verbose_name="Event Start"),
                       FakeExtendedField('datetime_end', verbose_name="Event End"),
                       FakeField('short_services', verbose_name="Services", sortable=False), FakeField('tasks')]
    if request.user.has_perm('events.approve_event'):
        context['cols'].append(FakeField('approval'))
    response = generate_response(request, context, start, end, time_range_unspecified)
    return response


@login_required()
@permission_required('events.view_events', raise_exception=True)
def all_cal(request, start=None, end=None):
    """ Calendar view for all events """
    context = {'h2': "All Events", 'listurl': reverse('events:all'), 'bootcal_endpoint': reverse('cal:api-all')}
    return render(request, 'events_cal.html', context)


def public_facing(request):
    """
    Lists events that have been approved, have not yet ended, and can otherwise be viewed by anyone (i.e. no sensitive
    or test events)
    """
    context = {}
    now = datetime.datetime.now(pytz.utc)
    events = BaseEvent.objects.filter(approved=True, closed=False, cancelled=False, test_event=False, sensitive=False) \
        .filter(datetime_end__gte=now)
    events = events.order_by('datetime_start')
    events = events.select_related('location__building').prefetch_related('org') \
        .prefetch_related('ccinstances__crew_chief')
    context['h2'] = "Active Events"
    context['events'] = events

    return render(request, "events_public.html", context)


@login_required
@permission_required('events.bill_event', raise_exception=True)
def multibillings(request):
    """ Lists all multibills """
    context = {}

    multibills = MultiBilling.objects.annotate(num_closed_events=Sum(Case(
            When(events__closed=True, then=1),
            default=0,
            output_field=IntegerField())))

    page = request.GET.get('page')
    sort = request.GET.get('sort') or '-date_billed'
    multibills = paginate_helper(multibills, page, sort)

    context['h2'] = "MultiBills"
    context['multibillings'] = multibills
    context['cols'] = ['events', FakeField('org', verbose_name="Client", sortable=True),
                       FakeExtendedField('date_billed', model=MultiBilling),
                       FakeExtendedField('date_paid', model=MultiBilling), 'amount', FakeField('email_sent'),
                       FakeField('tasks')]
    context['cols'] = map_fields(context['cols'])  # must use because there are strings
    return render(request, 'multibillings.html', context)


@login_required
@permission_required('events.edit_workshops', raise_exception=True)
def new_workshop(request):
    """ Form to add a new workshop series """
    context = {'msg': "Create Workshop"}
    if request.method == 'POST':
        form = WorkshopForm(request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('events:workshops:list'))
    else:
        form = WorkshopForm()
    context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('events.edit_workshops', raise_exception=True)
def edit_workshop(request, pk):
    """ Form to edit the details for a workshop series """
    context = {'msg': "Edit Workshop"}
    workshop = Workshop.objects.get(pk=pk)
    if request.method == 'POST':
        form = WorkshopForm(request.POST)
        if form.is_valid():
            workshop.name = request.POST['name']
            workshop.instructors = request.POST['instructors']
            workshop.description = request.POST['description']
            workshop.location = request.POST['location']
            workshop.notes = request.POST['notes']
            workshop.save()
            return HttpResponseRedirect(reverse("events:workshops:list"))
    else:
        form = WorkshopForm(instance=workshop)
        context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('events.edit_workshops', raise_exception=True)
def workshop_dates(request, pk):
    """ Form to add / edit sessions (dates) for a workshop series """
    context = {}
    workshop = Workshop.objects.get(pk=pk)
    dates = WorkshopDate.objects.filter(workshop=workshop)
    dates_formset = modelformset_factory(WorkshopDate, exclude=['workshop'], extra=3, can_delete=True,
                                         form=WorkshopDatesForm)
    formset = dates_formset(queryset=dates)

    if request.method == 'POST':
        formset = dates_formset(request.POST)
        if formset.is_valid():
            for form in formset.forms:
                form.instance.workshop = workshop
            formset.save()
            return HttpResponseRedirect(reverse("events:workshops:list"))
    context['formset'] = formset
    context['msg'] = "Workshop Dates for \"" + workshop.name + "\""
    return render(request, 'formset_workshop_dates.html', context)


@login_required
@permission_required('events.edit_workshops', raise_exception=True)
def workshops_list(request):
    """ List all workshop series """
    workshops = Workshop.objects.all()
    return render(request, 'workshops_list.html', {'workshops': workshops})


class DeleteWorkshop(SetFormMsgMixin, LoginRequiredMixin, HasPermMixin, DeleteView):
    """ Delete a series of workshops """
    model = Workshop
    template_name = "form_delete_cbv.html"
    msg = "Delete Workshop"
    perms = 'events.edit_workshops'

    def get_success_url(self):
        return reverse('events:workshops:list')

import datetime
import json
from time import mktime

from django.conf import settings
from django.core.urlresolvers import reverse
from django.db.models import Count, F, Q
from django.http import HttpResponse
from django.template.defaultfilters import slugify
from django.utils.decorators import method_decorator
from django.utils.html import conditional_escape
from django.views.generic.base import View
from django.views.decorators.cache import cache_page
from django_ical.views import ICalFeed

from events.models import Event, EventCCInstance
from meetings.models import Meeting
from helpers.mixins import HasPermMixin

from six import string_types


class BaseFeed(ICalFeed):
    """
    A simple event calender
    """
    product_id = '-//' + settings.ALLOWED_HOSTS[0] + ' //LNLDB//EN'
    timezone = 'UTC'
    file_name = "event.ics"

    @method_decorator(cache_page(15 * 60))
    def __call__(self, *args, **kwargs):
        return super(BaseFeed, self).__call__(*args, **kwargs)

    def item_title(self, item):
        return item.cal_name()

    def item_description(self, item):
        if item.cal_desc():
            return item.cal_desc()
        else:
            return ""

    def item_location(self, item):
        return item.cal_location()

    def item_guid(self, item):
        return item.cal_guid()

    def item_link(self, item):
        return item.cal_link()

    def item_start_datetime(self, item):
        return item.cal_start()

    def item_end_datetime(self, item):
        return item.cal_end()


class EventFeed(BaseFeed):
    def items(self):
        return list(Event.objects.filter(approved=True).exclude(Q(closed=True) |
                                                                Q(cancelled=True) |
                                                                Q(test_event=True) |
                                                                Q(sensitive=True)).order_by('datetime_start').all()) + \
            list(EventCCInstance.objects.filter(event__approved=True).exclude(Q(event__closed=True) |
                                                                              Q(event__cancelled=True))
                                .order_by('setup_start').all()) + \
            list(Meeting.objects.order_by('datetime').all())


class FullEventFeed(BaseFeed):
    def items(self):
        return list(Event.objects.exclude(Q(closed=True) |
                                          Q(cancelled=True) |
                                          Q(test_event=True) |
                                          Q(sensitive=True)).order_by('datetime_start').all()) + \
            list(EventCCInstance.objects.exclude(Q(event__closed=True) | Q(event__cancelled=True))
                                .order_by('setup_start').all()) + \
            list(Meeting.objects.order_by('datetime').all())


class LightEventFeed(BaseFeed):
    def items(self):
        return list(Event.objects.filter(approved=True).exclude(Q(closed=True) |
                                                                Q(cancelled=True) |
                                                                Q(test_event=True) |
                                                                Q(sensitive=True)).order_by('datetime_start').all()) + \
            list(Meeting.objects.order_by('datetime').all())


class BaseCalJsonView(HasPermMixin, View):
    perms = ['events.view_event']
    http_method_names = ['get']


class PublicFacingCalJsonView(View):
    # Does not inherit BaseCalJsonView because it should not require login
    http_method_names = ['get']

    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(approved=True).exclude(Q(closed=True) | Q(cancelled=True) |
                                                               Q(test_event=True) | Q(sensitive=True))

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json_publicfacing(queryset, from_date, to_date))


class FindChiefCalJsonView(BaseCalJsonView):
    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(Q(approved=True) & Q(closed=False) & Q(cancelled=False)) \
            .annotate(num_ccs=Count('ccinstances')).filter(num_ccs__lt=(F('ccs_needed'))).distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class IncomingCalJsonView(BaseCalJsonView):
    perms = ['events.approve_event']

    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(approved=False).exclude(Q(closed=True) | Q(cancelled=True)).distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class OpenCalJsonView(BaseCalJsonView):
    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(approved=True, closed=False, cancelled=False).distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class UnreviewedCalJsonView(BaseCalJsonView):
    perms = ['events.review_event']

    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(approved=True, closed=False, cancelled=False) \
            .filter(reviewed=False) \
            .filter(datetime_end__lte=now) \
            .distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class UnbilledCalJsonView(BaseCalJsonView):
    perms = ['events.bill_event']

    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(closed=False) \
            .filter(reviewed=True) \
            .filter(billings__isnull=True, multibillings__isnull=True) \
            .filter(billed_by_semester=False) \
            .distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class UnbilledSemesterCalJsonView(BaseCalJsonView):
    perms = ['events.bill_event']

    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(closed=False) \
            .filter(reviewed=True) \
            .filter(billings__isnull=True, multibillings__isnull=True) \
            .filter(billed_by_semester=True) \
            .order_by('datetime_start') \
            .distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class PaidCalJsonView(BaseCalJsonView):
    perms = ['events.close_event']

    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(closed=False) \
            .filter(Q(billings__date_paid__isnull=False) | Q(multibillings__date_paid__isnull=False)) \
            .distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class UnpaidCalJsonView(BaseCalJsonView):
    perms = ['events.bill_event']

    def get(self, request, *args, **kwargs):
        queryset = Event.objects.annotate(
            numpaid=Count('billings__date_paid')+Count('multibillings__date_paid')) \
            .filter(closed=False) \
            .filter(Q(billings__date_billed__isnull=False) | Q(multibillings__date_billed__isnull=False)) \
            .exclude(numpaid__gt=0) \
            .filter(reviewed=True) \
            .distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class ClosedCalJsonView(BaseCalJsonView):
    def get(self, request, *args, **kwargs):
        queryset = Event.objects.filter(closed=True)
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


class AllCalJsonView(BaseCalJsonView):
    def get(self, request, *args, **kwargs):
        queryset = Event.objects.distinct()
        if not request.user.has_perm('events.event_view_sensitive'):
            queryset = queryset.exclude(sensitive=True)
        if not request.user.has_perm('events.view_test_event'):
            queryset = queryset.exclude(test_event=True)
        if not request.user.has_perm('events.approve_event'):
            queryset = queryset.exclude(approved=False)

        from_date = request.GET.get('from', False)
        to_date = request.GET.get('to', False)
        return HttpResponse(generate_cal_json(queryset, from_date, to_date))


def generate_cal_json_publicfacing(queryset, from_date=None, to_date=None):
        if from_date and to_date:
            queryset = queryset.filter(
                datetime_start__range=(
                    timestamp_to_datetime(from_date) + datetime.timedelta(-30),
                    timestamp_to_datetime(to_date)
                )
            )
        elif from_date:
            queryset = queryset.filter(
                datetime_start__gte=timestamp_to_datetime(from_date)
            )
        elif to_date:
            queryset = queryset.filter(
                datetime_end__lte=timestamp_to_datetime(to_date)
            )
        objects_body = []
        for event in queryset:
            field = {
                "id": event.cal_guid(),
                "title": conditional_escape(event.cal_name()),
                "url": "#" + str(event.id),
                "class": '',
                "start": datetime_to_timestamp(event.cal_start() + datetime.timedelta(hours=-5)),
                "end": datetime_to_timestamp(event.cal_end() + datetime.timedelta(hours=-5))
            }
            objects_body.append(field)

        objects_head = {"success": 1, "result": objects_body}
        return json.dumps(objects_head)


def generate_cal_json(queryset, from_date=None, to_date=None):
        if from_date and to_date:
            queryset = queryset.filter(
                datetime_start__range=(
                    timestamp_to_datetime(from_date) + datetime.timedelta(-30),
                    timestamp_to_datetime(to_date)
                )
            )
        elif from_date:
            queryset = queryset.filter(
                datetime_start__gte=timestamp_to_datetime(from_date)
            )
        elif to_date:
            queryset = queryset.filter(
                datetime_end__lte=timestamp_to_datetime(to_date)
            )
        objects_body = []
        for event in queryset:
            field = {
                "id": event.cal_guid(),
                "title": conditional_escape(event.cal_name()),
                "url": reverse('events:detail', args=[event.id]),
                "class": 'cal-status-' + slugify(event.status),
                "start": datetime_to_timestamp(event.cal_start() + datetime.timedelta(hours=-5)),
                "end": datetime_to_timestamp(event.cal_end() + datetime.timedelta(hours=-5))
            }
            objects_body.append(field)

        objects_head = {"success": 1, "result": objects_body}
        return json.dumps(objects_head)


def timestamp_to_datetime(timestamp):
    """
    Converts string timestamp to datetime
    with json fix
    """
    if isinstance(timestamp, string_types):

        if len(timestamp) == 13:
            timestamp = int(timestamp) / 1000

        return datetime.datetime.fromtimestamp(timestamp)
    else:
        return ""


def datetime_to_timestamp(date):
    """
    Converts datetime to timestamp
    with json fix
    """
    if isinstance(date, datetime.datetime):

        timestamp = mktime(date.timetuple())
        json_timestamp = int(timestamp) * 1000

        return '{0}'.format(json_timestamp)
    else:
        return ""

from django_ical.views import ICalFeed
from events.models import Event, EventCCInstance
from meetings.models import Meeting
from django.db.models import Q
from django.db.models.query import QuerySet
from django.core.urlresolvers import reverse
import datetime
from time import mktime
from django.http import HttpResponse
import json
from itertools import chain

class EventFeed(ICalFeed):
    """
    A simple event calender
    """
    product_id = '-//lnl.wpi.edu//LNLDB//EN'
    timezone = 'UTC'
    file_name = "event.ics"

    def items(self):
        return list(Event.objects.filter(approved=True).exclude(Q(closed=True)|Q(cancelled=True)).order_by('datetime_start').all()) + \
               list(EventCCInstance.objects.filter(event__approved=True).exclude(Q(event__closed=True)|Q(event__cancelled=True)).order_by('setup_start').all()) + \
               list(Meeting.objects.order_by('datetime').all())

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

def cal_json(request, *args, **kwargs):
    queryset = Event.objects.filter(approved=True).exclude(Q(closed=True)|Q(cancelled=True))
    from_date = request.GET.get('from', False)
    to_date = request.GET.get('to', False)
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
            "title": event.cal_name(),
            "url": "#" + str(event.id),
            "class": '',
            "start": datetime_to_timestamp(event.cal_start()),
            "end": datetime_to_timestamp(event.cal_end())
        }
        objects_body.append(field)

    objects_head = {"success": 1}
    objects_head["result"] = objects_body
    return HttpResponse(json.dumps(objects_head))


def timestamp_to_datetime(timestamp):
    """
    Converts string timestamp to datetime
    with json fix
    """
    if isinstance(timestamp, (str, unicode)):

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


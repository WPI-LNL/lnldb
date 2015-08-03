from django import template
from django.utils.timezone import localtime

register = template.Library()


@register.filter()
def daterange(datetime_start, datetime_end):
    out_str = ""
    datetime_start = localtime(datetime_start)
    out_str += datetime_start.strftime("%a %m/%d/%y %I:%M %p - ")
    datetime_end = localtime(datetime_end)
    if datetime_start.date() == datetime_end.date():
        out_str += datetime_end.strftime("%I:%M %p")
    else:
        out_str += datetime_end.strftime("%a %m/%d/%y %I:%M %p")
    return out_str

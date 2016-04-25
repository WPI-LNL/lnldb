# shamelessly borrowed from http://greenash.net.au/thoughts/2010/06/an-inline-image-django-template-filter/
# but built upon with the love of gabe
from django import template
from django.template.defaultfilters import stringfilter

from django.core.urlresolvers import reverse
from events.models import Event

import re

register = template.Library()

regex = re.compile(r'@(?P<eventid>\d+)')


@register.filter
@stringfilter
def eventlink(value, targeturlname=None):
    """ Returns a html link to a eventname prefixed with @"""
    new_value = value
    it = regex.finditer(value)
    for m in it:
        r = m.groupdict()
        try:
            event = Event.objects.get(pk=r['eventid'])
            if targeturlname:
                new_value = new_value.replace(
                    m.group(), '<a href="%s">@%s</a> ' %
                    (reverse(
                        targeturlname, args=(
                            event.id,)), event.event_name))
            else:
                new_value = new_value.replace(
                    m.group(),
                    '<a href="%s">@%s</a> ' %
                    (reverse(
                        "events-detail",
                        args=(
                            event.id,
                        )),
                        event.event_name))
        except Event.DoesNotExist:
            pass
    return new_value


@register.filter
@stringfilter
def mdeventlink(value, targeturlname=None):
    """ Eventlink Markdown Edition
    Returns a markdown friendly verison so you can chain |markdown after eventlink
    """
    new_value = value
    it = regex.finditer(value)
    for m in it:
        r = m.groupdict()
        try:
            event = Event.objects.get(pk=r['eventid'])
            if targeturlname:
                new_value = new_value.replace(
                    m.group(), '[@%s](%s) ' %
                    (event.event_name, reverse(
                        targeturlname, args=(
                            event.id,))))
            else:
                new_value = new_value.replace(
                    m.group(),
                    '[@%s](%s) ' %
                    (event.event_name,
                        reverse(
                            "events-detail",
                            args=(
                                event.id,
                            ))))
        except Event.DoesNotExist:
            pass
    return new_value

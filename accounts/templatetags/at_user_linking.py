# shamelessly borrowed from http://greenash.net.au/thoughts/2010/06/an-inline-image-django-template-filter/
# but built upon with the love of gabe
import re

from django import template
from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse
from django.template.defaultfilters import stringfilter

register = template.Library()

regex = re.compile(r'@(?P<username>[\w]+)')


@register.filter
@stringfilter
def userlink(value):
    """ Returns a html link to a username prefixed with @"""
    new_value = value
    it = regex.finditer(value)
    for m in it:
        r = m.groupdict()
        try:
            user = get_user_model().objects.get(username=r['username'])
            new_value = new_value.replace(m.group(), '<a href="%s">@%s</a> ' % (
                reverse("accounts:detail", args=(user.id,)), user.username))
        except get_user_model().DoesNotExist:
            pass
    return new_value


@register.filter
@stringfilter
def mduserlink(value):
    """ Userlink Markdown Edition
    Returns a markdown friendly verison so you can chain |markdown after userlink
    """
    new_value = value
    it = regex.finditer(value)
    for m in it:
        r = m.groupdict()
        try:
            user = get_user_model().objects.get(username=r['username'])
            new_value = new_value.replace(m.group(),
                                          '[@%s](%s) ' % (user.username, reverse("accounts:detail", args=(user.id,))))
        except get_user_model().DoesNotExist:
            pass
    return new_value

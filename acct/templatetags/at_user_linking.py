# shamelessly borrowed from http://greenash.net.au/thoughts/2010/06/an-inline-image-django-template-filter/
# but built upon with the love of gabe
from django import template
from django.template.defaultfilters import stringfilter
from django.conf import settings

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse

import re

register = template.Library()

regex = re.compile(r'\@(?P<username>[\w]+) ')

@register.filter
@stringfilter
def userlink(value):
    """ Returns a html link to a username prefixed with @"""
    new_value = value
    it = regex.finditer(value)
    for m in it:
        r = m.groupdict()
        try:
            user = User.objects.get(username=r['username'])
            new_value = new_value.replace(m.group(), '<a href="%s">@%s</a> ' % (reverse("memberdetail", args=(user.id,)),user.username))
        except User.DoesNotExist:
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
            user = User.objects.get(username=r['username'])
            new_value = new_value.replace(m.group(), '[@%s](%s) ' % (user.username,reverse("memberdetail", args=(user.id,))))
        except User.DoesNotExist:
            pass
    return new_value 

from django import template
from django.utils.timezone import localtime
from django.conf import settings

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


@register.filter()
def is_list(string):
    return hasattr(string, '__iter__') and not isinstance(string, basestring)


@register.simple_tag(takes_context=True)
def get_base_url(context):
    if 'request' in context:
        request = context['request']
        return "%s://%s" % (request.scheme, request.get_host())
    # try to guess if the server has https
    is_secure = settings.SECURE_SSL_REDIRECT or settings.SESSION_COOKIE_SECURE\
            or settings.SECURE_HSTS_SECONDS
    scheme = 'https' if is_secure else 'http'
    return '%s://%s' % (scheme, settings.ALLOWED_HOSTS[0])


@register.filter()
def public_field(string):
    output = string
    if settings.PUBLIC_FIELD_FILTERING and string:
        output = string.replace('LnL', 'LNL')
    return output

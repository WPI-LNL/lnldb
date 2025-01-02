import re

from django import template
from lnldb import settings
from django.template.defaultfilters import stringfilter
from django.contrib.auth import get_user_model

from ..api import user_profile, channel_info

register = template.Library()

regex = re.compile(r'#(?P<channel_id>[\w-]{3,})')


@register.filter
@stringfilter
def slack(value):
    """ Returns a html link to any Slack channels mentioned in the text (must be prefixed with #) """
    new_value = value
    it = regex.finditer(value)
    for m in it:
        r = m.groupdict()
        channel = r['channel_id']
        new_value = new_value.replace(m.group(), '[#%s]('+settings.SLACK_BASE_URL+'/app_redirect?channel=%s)' %
                                      (channel, channel))
    return new_value


@register.filter
@stringfilter
def id_to_name(identifier):
    """ Attempts to replace a Slack user's ID with their display name """
    slack_user = user_profile(identifier)
    if slack_user['ok']:
        return slack_user['user']['profile']['real_name']
    return identifier

@register.filter
@stringfilter
def id_to_user_pk(identifier):
    """ Attempts to replace a Slack user's ID with their user pk """
    slack_user = user_profile(identifier)
    if slack_user['ok']:
        username = slack_user['user']['profile'].get('email', '').split('@')[0]
        return get_user_model().objects.filter(username=username).first().pk
    return None


@register.filter
@stringfilter
def channel_from_id(identifier):
    """ Attempts to replace a Slack channel's ID with its name """
    info = channel_info(identifier)
    if info:
        return info['name']
    return identifier

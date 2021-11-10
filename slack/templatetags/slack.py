import re

from django import template
from django.template.defaultfilters import stringfilter

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
        new_value = new_value.replace(m.group(), '[#%s](https://wpilnl.slack.com/app_redirect?channel=%s)' %
                                      (channel, channel))
    return new_value

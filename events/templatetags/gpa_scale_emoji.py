from django import template

register = template.Library()


@register.filter
def gpa_scale_emoji(value):
    """Converts a score on a 4.0 scale to an emoji"""
    if value is None:
        return u'\U00002753'
    elif value <= 0.5:
        return u'\U00002620'
    elif value <= 1.5:
        return u'\U0001f621'
    elif value <= 2.5:
        return u'\U0001f641'
    elif value <= 3.5:
        return u'\U0001f610'
    elif value <= 4.0:
        return u'\U0001f600'
    else:
        return 'ERROR'

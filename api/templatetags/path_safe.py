from django import template
register = template.Library()


@register.filter
def path_safe(string):
    return string.replace('/', '-')

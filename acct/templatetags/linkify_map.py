from django.core.urlresolvers import reverse
from django.db.models.query import QuerySet
from django.template.defaultfilters import register
from django.utils.html import format_html, conditional_escape
from django.utils.safestring import mark_safe


@register.filter
def linkify_map(value, page, escape=True, title_callback=None, id_callback=None):
    if not title_callback:
        title_callback = str
    if not id_callback:
        def id_callback(item):
            return item.id
    try:
        value.__iter__
    except AttributeError:
        value = value.all()
    return map(lambda item: mark_safe(format_html("<a href=\"{0}\">{1}</a>",
                                                  reverse(page, args=[
                                                      conditional_escape(id_callback(item)) if escape else id_callback(
                                                          item)
                                                  ]),
                                                  conditional_escape(
                                                      title_callback(item)) if escape else title_callback(item))),
               value)


@register.filter
def linkify_join(value, page, sep=None, escape=True, title_callback=None, id_callback=None):
    if not sep:
        sep = ', '
    return mark_safe(sep.join(linkify_map(value, page, escape, title_callback, id_callback)))
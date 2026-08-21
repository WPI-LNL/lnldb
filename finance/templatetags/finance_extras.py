"""
Template filters and tags shared by the five finance pages.

Two rules hold across everything in here. First, a filter is handed
whatever the template happens to have -- ``None``, an empty string, a value
straight off a form -- so every one of them coerces defensively and returns
something printable rather than raising: a page that renders a dash is much
better than a page that 500s over one bad cell. Second, anything that emits
markup goes through ``format_html`` unless every substituted value is a
number this module produced itself.
"""
import os
from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def autocomplete_media():
    """
    The scripts django-ajax-selects needs to wire itself up. Scripts only.

    ``AutoCompleteSelectField`` renders an ordinary text box plus a hidden input
    carrying ``data-ajax-select`` and a ``source`` URL. Those attributes are
    inert markup on their own; ``ajax_select.js`` is what finds them on ready
    and attaches the jQuery UI autocomplete.

    ``base.html`` already loads that script site-wide, which makes this look
    redundant. It is not, and the reason is its very last line::

        })(window.jQuery, window.django.jQuery);

    ``window.django`` is created by ``admin/js/jquery.init.js``, which
    ``base.html`` does not load. On a page that supplies nothing further, that
    line throws ``TypeError`` before the module body runs -- so the plugin is
    never registered, nothing binds on ready, and the "Link to Event" box looks
    completely normal, accepts typing and searches nothing. No error reaches the
    page, which is what made it hard to attribute.

    Emitting the real media fixes it by supplying the missing prerequisite and
    re-running ``ajax_select.js`` after it, this time with a ``window.django``
    to read.

    Every other form template in this project gets these from
    ``{{ form.media }}``. The finance pages cannot rely on that: the queue
    renders one form per row and has none at all when the queue is empty, and
    the split modal has a formset rather than a form -- so the pages that need
    the scripts most are the ones with no ``form`` in context. Asking the widget
    class for its own media instead means no finance page can forget, and no
    file list is duplicated here to rot when ajax_select bumps a jQuery version.

    Because this is emitted app-wide, the finance forms set
    ``helper.include_media = False`` so crispy does not emit a second copy on
    the pages it renders. One source for these assets, one place to reason
    about them.

    .. warning::

       The stylesheets are dropped on purpose, and putting them back breaks the
       dropdown. ``ajax_select``'s media carries a complete **jQuery UI 1.13.2**
       theme, but the widget that actually runs here is **jQuery UI 1.10.3** --
       the copy ``base.html`` loads and hands to ``window.$``. Loading 1.13's
       stylesheet over 1.10's markup styles a menu that is not the menu on the
       page: 1.13 wraps each row in ``.ui-menu-item-wrapper`` and drops the
       ``.ui-menu-item a`` rules 1.10 relies on, so the results list rendered
       misaligned and flickered as it opened.

       ``base.html`` already loads a full jQuery UI 1.10.2 stylesheet matching
       that widget, and ``ajax_select.css`` besides, so there is nothing missing
       to supply -- only a mismatched theme to avoid.

    .. note::

       The bundled jQuery is not a conflict. ``AJAX_SELECT_BOOTSTRAP`` is on, so
       this pulls jQuery 3.7.1 alongside the jQuery 1.10 that ``base.html``
       already loaded -- but ``jquery.init.js`` immediately calls
       ``jQuery.noConflict(true)``, which hands the new copy to
       ``django.jQuery`` and puts ``window.$`` back to 1.10. The finance scripts
       keep the jQuery they were written against, and the separate instance also
       isolates them from the ``dismissAddRelatedObjectPopup`` error that
       ``ajax_select.js`` raises outside the admin.
    """
    from django import forms
    from ajax_select.fields import AutoCompleteSelectWidget

    # Any channel will do -- the media is the same for all of them, and the
    # widget is built purely to be asked for it. Taking the script list from
    # ajax_select rather than writing it out here means a version bump in the
    # package cannot leave a stale filename behind in this file.
    scripts = AutoCompleteSelectWidget(channel='Events').media._js
    return forms.Media(js=scripts)


@register.simple_tag
def asset(path):
    """
    A static URL with a cache-buster that actually changes when the file does.

    Every finance page used ``{% static %}?v={{ GIT_RELEASE }}``, and
    GIT_RELEASE is the git SHA: constant across every edit between commits. A
    browser that had already fetched queue.js kept serving its copy back, so
    changes to the stylesheet or the scripts were invisible until someone
    thought to hard-refresh -- and the symptom is a button that silently does
    nothing, which is the hardest kind of bug to attribute.

    In development the stamp is the file's modification time. In production
    files only change when a deploy does, so the release SHA is exactly right
    and no filesystem call is made per request.
    """
    url = staticfiles_storage.url(path)
    stamp = _asset_stamp(path)
    return '%s?v=%s' % (url, stamp) if stamp else url


def _asset_stamp(path):
    """
    The cache-busting stamp for one static file.

    Returns an empty string when there is nothing useful to stamp with, in
    which case :func:`asset` emits a bare URL. A missing file is not an error
    here -- ``collectstatic`` may not have run yet, and refusing to render the
    page over it would help nobody.
    """
    if not settings.DEBUG:
        return getattr(settings, 'GIT_RELEASE', '') or ''
    try:
        found = finders.find(path)
        return str(int(os.path.getmtime(found))) if found else ''
    except OSError:
        return ''


@register.filter
def money(value, show_sign=False):
    """
    Accounting-style currency. Negatives render in parentheses, which is what
    the Treasurer expects to see next to a Workday export.
    """
    if value is None or value == '':
        return '—'
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    negative = amount < 0
    body = intcomma('%.2f' % abs(amount))
    if negative:
        return '($%s)' % body
    return ('+$%s' % body) if show_sign else '$%s' % body


@register.filter
def money_class(value):
    """ CSS class matching the sign, for consistent red/green across pages. """
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return ''
    if amount > 0:
        return 'text-success'
    if amount < 0:
        return 'text-danger'
    return 'text-muted'


@register.filter
def abs_value(value):
    """
    Magnitude without the sign, for rows that show direction some other way.

    Non-numeric input is passed straight back so the template still shows
    whatever it had.
    """
    try:
        return abs(Decimal(value))
    except (InvalidOperation, TypeError, ValueError):
        return value


@register.filter
def percent_of(part, whole):
    """ Clamped 0-100 integer percentage, safe when the denominator is zero. """
    try:
        part, whole = Decimal(part), Decimal(whole)
    except (InvalidOperation, TypeError, ValueError):
        return 0
    if not whole:
        return 0
    return max(0, min(100, int(round(part / whole * 100))))


@register.simple_tag
def burndown_bar(spent, awarded):
    """
    Green remaining / red spent, with an overspend rendered as a full red bar
    plus an explicit overage figure -- a bar that silently clamps at 100% would
    hide the one case the Treasurer most needs to see.
    """
    try:
        spent, awarded = Decimal(spent), Decimal(awarded)
    except (InvalidOperation, TypeError, ValueError):
        return ''

    if awarded <= 0:
        return mark_safe('<div class="progress fin-burndown"><div class="progress-bar '
                         'progress-bar-danger" style="width:100%"></div></div>')

    if spent > awarded:
        over = spent - awarded
        return format_html(
            '<div class="progress fin-burndown" title="Overspent by ${}">'
            '<div class="progress-bar progress-bar-danger" style="width:100%">'
            'Over by ${}</div></div>',
            intcomma('%.2f' % over), intcomma('%.2f' % over))

    spent_pct = int(round(spent / awarded * 100)) if awarded else 0
    spent_pct = max(0, min(100, spent_pct))
    return format_html(
        '<div class="progress fin-burndown" title="${} of ${} spent">'
        '<div class="progress-bar progress-bar-danger" style="width:{}%"></div>'
        '<div class="progress-bar progress-bar-success" style="width:{}%"></div></div>',
        intcomma('%.2f' % spent), intcomma('%.2f' % awarded), spent_pct, 100 - spent_pct)


@register.simple_tag(takes_context=True)
def filter_url(context, **overrides):
    """ Rebuild the current URL with some filter values swapped. """
    state = context.get('filter_state')
    if state is None:
        return '?'
    return state.url_with(**overrides)


@register.simple_tag(takes_context=True)
def sort_url(context, column):
    """ Toggle sort direction on a ledger column header. """
    request = context['request']
    params = request.GET.copy()
    current = params.get('sort', 'date')
    direction = params.get('dir', 'desc')
    params['sort'] = column
    params['dir'] = 'asc' if (current == column and direction == 'desc') else 'desc'
    params.pop('page', None)
    return '?' + params.urlencode()


@register.simple_tag(takes_context=True)
def sort_indicator(context, column):
    """ The up/down arrow on whichever ledger column is currently sorted. """
    request = context['request']
    if request.GET.get('sort', 'date') != column:
        return ''
    arrow = '&#9650;' if request.GET.get('dir', 'desc') == 'asc' else '&#9660;'
    return mark_safe('<span class="fin-sort-arrow">%s</span>' % arrow)


@register.filter
def entry_badge(entry):
    """
    Coloured label for revenue / expense / refund / encumbrance.

    Encumbrances get their own colour as well as their own word: money merely
    reserved should not sit in a column of settled spending looking exactly
    like it.
    """
    mapping = {'revenue': 'success', 'expense': 'default',
               'refund': 'info', 'encumbrance': 'warning'}
    kind = entry.entry_type
    return format_html('<span class="label label-{}">{}</span>',
                       mapping.get(kind, 'default'), entry.get_entry_type_display())


@register.filter
def status_badge(entry):
    """ Settled / pending pill for an entry. """
    if entry.status == 'settled':
        return mark_safe('<span class="label label-success">Settled</span>')
    return mark_safe('<span class="label label-warning">Pending</span>')


@register.filter
def get_item(dictionary, key):
    """
    Subscript a dict from a template, which has no syntax for it.

    Used where the key is itself a variable -- per-column data keyed by
    column name, for instance. Anything that is not dict-like yields
    ``None`` rather than raising.
    """
    if hasattr(dictionary, 'get'):
        return dictionary.get(key)
    return None


@register.filter
def indent_px(level):
    """ Convert an MPTT depth into the left padding the tree rows use. """
    try:
        return int(level) * 18
    except (TypeError, ValueError):
        return 0

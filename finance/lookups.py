"""
Autocomplete channels for the finance forms.

django-ajax-selects calls these over AJAX as the user types, so each one is
deliberately capped and ordered -- an unbounded ``icontains`` across every
event we have ever run would be both slow and useless to read. Every string
that reaches ``format_item_display`` is escaped by hand because the return
value is injected into the page as raw HTML.

.. warning::

   ``check_auth`` must **raise** ``PermissionDenied``. It must not return a
   boolean. ``ajax_select.views.ajax_lookup`` calls it and throws the result
   away::

       if hasattr(lookup, "check_auth"):
           lookup.check_auth(request)

   so a channel that returns ``False`` instead of raising is not protected at
   all -- the endpoint stays open to anyone who knows the URL, logged in or
   not. These two channels did exactly that, which left every event name, date
   and billing org, and every project code, readable by an anonymous visitor
   at ``/db/lookups/ajax_lookup/Events``.
"""
from ajax_select import LookupChannel
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.html import escape

from events.models import BaseEvent
from finance.models import ProjectTag


class EventLookup(LookupChannel):
    """ Powers the "Link to Event" search on revenue lines. """
    model = BaseEvent

    def check_auth(self, request):
        """
        Gate the endpoint behind the same permission as the ledger itself.

        Raises rather than returning; see the module docstring for why that
        distinction is the whole of the protection here.
        """
        if not (request.user.is_authenticated
                and request.user.has_perm('finance.view_subledger')):
            raise PermissionDenied

    def get_query(self, q, request):
        """ Match on the event name or on any of the orgs attached to it. """
        qs = BaseEvent.objects.filter(
            Q(event_name__icontains=q) | Q(org__name__icontains=q) |
            Q(org__shortname__icontains=q) | Q(billing_org__name__icontains=q)
        ).filter(test_event=False).select_related('billing_org').distinct()
        # Most recent first: the Treasurer is nearly always reconciling this term.
        return qs.order_by('-datetime_start')[:25]

    def get_result(self, obj):
        """ Return the plain text that lands in the input once a row is picked. """
        return str(obj)

    def format_match(self, obj):
        """ Render the dropdown row; identical to the chosen-item chip. """
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        """ Render one event as name, date and billing org. """
        org = obj.billing_org or obj.org.first()
        return '&nbsp;<strong>%s</strong> <span class="text-muted">%s%s</span>' % (
            escape(obj.event_name),
            escape(obj.datetime_start.strftime('%b %d, %Y')),
            ' &middot; ' + escape(org.retname) if org else '',
        )


class ProjectTagLookup(LookupChannel):
    """ Powers the project tag picker on allocation and reconcile forms. """
    model = ProjectTag

    def check_auth(self, request):
        """
        Gate the endpoint behind the same permission as the ledger itself.

        Raises rather than returning; see the module docstring for why that
        distinction is the whole of the protection here.
        """
        if not (request.user.is_authenticated
                and request.user.has_perm('finance.view_subledger')):
            raise PermissionDenied

    def get_query(self, q, request):
        """ Match on either half of the tag, and never offer an archived one. """
        return ProjectTag.objects.filter(
            Q(name__icontains=q) | Q(code__icontains=q)).filter(archived=False)[:25]

    def get_result(self, obj):
        """ Return the plain text that lands in the input once a row is picked. """
        return str(obj)

    def format_match(self, obj):
        """ Render the dropdown row; identical to the chosen-item chip. """
        return self.format_item_display(obj)

    def format_item_display(self, obj):
        """ Render one tag as its short code followed by the human name. """
        return '&nbsp;<strong>%s</strong> <span class="text-muted">%s</span>' % (
            escape(obj.code), escape(obj.name))

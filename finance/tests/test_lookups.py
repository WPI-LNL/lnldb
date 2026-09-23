"""
The ajax-select channels behind the Event and Project pickers.

Both are registered in ``settings.AJAX_LOOKUP_CHANNELS`` and reached over HTTP
by django-ajax-selects rather than by any view in this app, which is exactly
why they are worth testing directly: nothing else here imports them, so a
change that breaks one is invisible until somebody types in the box.
"""
import datetime
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.utils import timezone

from events.tests.generators import Event2019Factory, OrgFactory
from finance.lookups import EventLookup, ProjectTagLookup
from finance.models import ProjectTag


def _request(user):
    request = RequestFactory().get('/')
    request.user = user
    return request


class LookupPermissionTests(TestCase):
    """
    Both channels are reachable by URL by anyone who can guess it, so the
    permission check is the only thing standing in front of them.

    The check has to *raise*. ``ajax_select.views.ajax_lookup`` calls
    ``check_auth(request)`` and discards the result, so a channel that returns
    ``False`` is not protected at all -- which is what these two did until the
    endpoint was tested over HTTP rather than by calling the method. Asserting
    on a return value is therefore exactly the wrong test, and
    :class:`LookupEndpointPermissionTests` below checks the thing that actually
    matters.
    """

    def setUp(self):
        User = get_user_model()
        self.nobody = User.objects.create_user(
            username='nobody', email='nobody@wpi.edu', password='x')
        treasurer = User.objects.create_user(
            username='treasurer', email='treasurer@wpi.edu', password='x')
        treasurer.user_permissions.add(Permission.objects.get(codename='view_subledger'))
        # Permission caching is per instance; re-read so the next check sees it.
        self.treasurer = User.objects.get(pk=treasurer.pk)

    def test_an_anonymous_visitor_is_refused(self):
        for channel in (EventLookup(), ProjectTagLookup()):
            with self.subTest(channel=channel.__class__.__name__):
                with self.assertRaises(PermissionDenied):
                    channel.check_auth(_request(AnonymousUser()))

    def test_a_signed_in_user_without_the_permission_is_refused(self):
        for channel in (EventLookup(), ProjectTagLookup()):
            with self.subTest(channel=channel.__class__.__name__):
                with self.assertRaises(PermissionDenied):
                    channel.check_auth(_request(self.nobody))

    def test_the_subledger_view_permission_is_enough(self):
        """ Permitted callers pass through; the method returns nothing. """
        for channel in (EventLookup(), ProjectTagLookup()):
            with self.subTest(channel=channel.__class__.__name__):
                self.assertIsNone(channel.check_auth(_request(self.treasurer)))

    def test_refusal_is_raised_rather_than_returned(self):
        """
        A falsy return is not a refusal, because nothing reads the return value.

        This is the regression guard for the actual defect: both channels used
        to ``return False``, and the endpoint served every event name, date and
        billing org to anonymous callers regardless.
        """
        for channel in (EventLookup(), ProjectTagLookup()):
            with self.subTest(channel=channel.__class__.__name__):
                try:
                    channel.check_auth(_request(AnonymousUser()))
                except PermissionDenied:
                    continue
                self.fail('%s.check_auth returned instead of raising; the ajax_select '
                          'view discards the return value, so this endpoint is open'
                          % channel.__class__.__name__)


class LookupEndpointPermissionTests(TestCase):
    """
    The channels over HTTP, which is the only way they are ever really called.

    Testing ``check_auth`` directly cannot catch the bug these guard against --
    the method looked perfectly correct in isolation. Only a request through
    ``ajax_select``'s own view shows whether the refusal has any effect.
    """

    url = '/db/lookups/ajax_lookup/Events'

    def setUp(self):
        User = get_user_model()
        self.nobody = User.objects.create_user(
            username='nobody', email='nobody@wpi.edu', password='x')
        treasurer = User.objects.create_user(
            username='treasurer', email='treasurer@wpi.edu', password='x')
        treasurer.user_permissions.add(Permission.objects.get(codename='view_subledger'))
        self.treasurer = User.objects.get(pk=treasurer.pk)
        Event2019Factory(event_name='Fall Concert')

    def test_an_anonymous_request_is_refused(self):
        response = self.client.get(self.url, {'term': 'concert'})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b'Fall Concert', response.content)

    def test_a_signed_in_user_without_the_permission_is_refused(self):
        self.client.force_login(self.nobody)
        response = self.client.get(self.url, {'term': 'concert'})
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b'Fall Concert', response.content)

    def test_a_permitted_user_gets_results(self):
        self.client.force_login(self.treasurer)
        response = self.client.get(self.url, {'term': 'concert'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Fall Concert', json.loads(response.content.decode())[0]['value'])


class EventLookupTests(TestCase):
    def setUp(self):
        self.channel = EventLookup()
        self.org = OrgFactory(name='Lens and Lights', shortname='LNL')
        self.event = Event2019Factory(event_name='Fall Concert')
        self.event.org.add(self.org)

    def _names(self, query):
        return [e.event_name for e in self.channel.get_query(query, _request(None))]

    def test_it_matches_on_the_event_name(self):
        self.assertIn('Fall Concert', self._names('concert'))

    def test_it_matches_on_the_client_organisation(self):
        """ The Treasurer is reading a bank line, so they often have the payer. """
        self.assertIn('Fall Concert', self._names('Lens and Lights'))

    def test_it_matches_on_the_organisation_shortname(self):
        self.assertIn('Fall Concert', self._names('LNL'))

    def test_it_matches_on_the_billing_organisation(self):
        payer = OrgFactory(name='Student Activities Office', shortname='SAO')
        self.event.billing_org = payer
        self.event.save()
        self.assertIn('Fall Concert', self._names('Student Activities'))

    def test_test_events_are_never_offered(self):
        """ A test event is not something real money can be filed against. """
        Event2019Factory(event_name='Concert Rehearsal', test_event=True)
        self.assertNotIn('Concert Rehearsal', self._names('concert'))

    def test_an_event_matching_twice_appears_once(self):
        """
        The query ORs across three joined tables, so a matching event comes
        back once per matching row unless the queryset is distinct.
        """
        second = OrgFactory(name='Concert Committee', shortname='CC')
        self.event.org.add(second)
        self.event.billing_org = second
        self.event.save()
        self.assertEqual(self._names('concert').count('Fall Concert'), 1)

    def test_the_most_recent_events_come_first(self):
        """ Reconciling is nearly always about this term. """
        old = Event2019Factory(event_name='Concert Long Ago')
        old.datetime_start = timezone.now() - datetime.timedelta(days=900)
        old.save()
        names = self._names('concert')
        self.assertLess(names.index('Fall Concert'), names.index('Concert Long Ago'))

    def test_the_list_is_capped(self):
        for index in range(30):
            Event2019Factory(event_name='Concert %s' % index)
        self.assertEqual(len(self._names('concert')), 25)

    def test_the_display_names_the_event_and_who_is_paying(self):
        html = self.channel.format_item_display(self.event)
        self.assertIn('Fall Concert', html)
        self.assertIn(self.org.retname, html)

    def test_the_display_survives_an_event_with_no_organisation(self):
        orphan = Event2019Factory(event_name='Unattached Show')
        self.assertIn('Unattached Show', self.channel.format_item_display(orphan))

    def test_the_display_escapes_what_people_typed(self):
        """ Event names are free text, and this string is inserted as markup. """
        self.event.event_name = '<script>alert(1)</script>'
        self.event.save()
        html = self.channel.format_item_display(self.event)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_the_match_and_the_item_read_the_same(self):
        self.assertEqual(self.channel.format_match(self.event),
                         self.channel.format_item_display(self.event))

    def test_the_result_is_the_events_own_label(self):
        self.assertEqual(self.channel.get_result(self.event), str(self.event))


class ProjectTagLookupTests(TestCase):
    def setUp(self):
        self.channel = ProjectTagLookup()
        self.tag = ProjectTag.objects.create(name='New Equipment List 2026', code='NEL26')

    def _codes(self, query):
        return [t.code for t in self.channel.get_query(query, _request(None))]

    def test_it_matches_on_the_name(self):
        self.assertIn('NEL26', self._codes('equipment'))

    def test_it_matches_on_the_code(self):
        self.assertIn('NEL26', self._codes('nel'))

    def test_an_archived_project_is_not_offered(self):
        """ Archived means "file no new spending here". """
        ProjectTag.objects.create(name='Old Rig', code='OLDRIG', archived=True)
        self.assertNotIn('OLDRIG', self._codes('old'))

    def test_the_list_is_capped(self):
        for index in range(30):
            ProjectTag.objects.create(name='Rig %s' % index, code='RIG%s' % index)
        self.assertEqual(len(self._codes('rig')), 25)

    def test_the_display_leads_with_the_code(self):
        """ The code is what appears on a memo, so it is what gets scanned for. """
        html = self.channel.format_item_display(self.tag)
        self.assertLess(html.index('NEL26'), html.index('New Equipment List'))

    def test_the_display_escapes_what_people_typed(self):
        self.tag.name = '<b>bold</b>'
        html = self.channel.format_item_display(self.tag)
        self.assertNotIn('<b>bold</b>', html)
        self.assertIn('&lt;b&gt;', html)

    def test_the_match_and_the_item_read_the_same(self):
        self.assertEqual(self.channel.format_match(self.tag),
                         self.channel.format_item_display(self.tag))

    def test_the_result_is_the_tags_own_label(self):
        self.assertEqual(self.channel.get_result(self.tag), str(self.tag))


class LookupRegistrationTests(TestCase):
    """
    A channel is reached by the name the form field asks for, not by import, so
    a rename that misses the settings entry fails only in the browser.
    """

    def test_both_channels_are_registered_under_the_names_the_forms_use(self):
        from django.conf import settings
        channels = settings.AJAX_LOOKUP_CHANNELS
        self.assertEqual(channels.get('Events'), ('finance.lookups', 'EventLookup'))
        self.assertEqual(channels.get('ProjectTags'), ('finance.lookups', 'ProjectTagLookup'))

    def test_the_event_field_asks_for_the_registered_channel(self):
        from finance.forms import BaseAllocationForm
        self.assertEqual(BaseAllocationForm.base_fields['linked_event'].channel, 'Events')

"""
The ``import_real_events`` management command.

The command exists to answer one question honestly -- how often does a revenue
memo name an event that actually exists -- so the tests here are mostly about
the ways it could answer it dishonestly: importing the same event twice,
deleting an event a transaction is already linked to, or quietly copying
private fields off the production record.

Nothing here touches the network. The API path is exercised through ``--file``,
which takes the same record shape the endpoint returns.
"""
import datetime
import json

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from events.models import BaseEvent, Location, Organization
from events.tests.generators import UserFactory
from finance.management.commands.import_real_events import IMPORT_MARKER
from finance.models import ParsedTransaction, WorkdayTransaction


def api_row(source_id=1, name='BRASA Carnival C26', location='Odeum'):
    """ One record shaped like the ``/api/v1/events`` response. """
    start = timezone.now() - datetime.timedelta(days=30)
    return {
        'id': source_id,
        'event_name': name,
        'description': 'A public description.',
        'location': location,
        'datetime_start': start.isoformat(),
        'datetime_end': (start + datetime.timedelta(hours=3)).isoformat(),
    }


class ImportFromApiShapeTests(TestCase):
    """ The default path: public API records, written through ``--file``. """

    def setUp(self):
        self.user = UserFactory.create(username='treasurer', is_superuser=True)

    def _run(self, rows, **kwargs):
        path = self._write(rows)
        call_command('import_real_events', file=path, verbosity=0, **kwargs)

    def _write(self, rows):
        path = self.get_temp_path()
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(rows, handle)
        return path

    def get_temp_path(self):
        import tempfile
        handle = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
        handle.close()
        self.addCleanup(lambda: __import__('os').unlink(handle.name))
        return handle.name

    def test_creates_the_event(self):
        self._run([api_row()])
        event = BaseEvent.objects.get(event_name='BRASA Carnival C26')
        self.assertFalse(event.test_event)
        self.assertIn(IMPORT_MARKER, event.internal_notes)

    def test_is_not_flagged_as_a_test_event(self):
        """
        ``EventLookup`` filters out test events, so flagging these would hide
        them from the picker the import exists to feed.
        """
        self._run([api_row()])
        self.assertTrue(BaseEvent.objects.filter(
            event_name='BRASA Carnival C26', test_event=False).exists())

    def test_running_twice_imports_once(self):
        """ The marker carries the source id precisely so a re-run is a no-op. """
        rows = [api_row()]
        self._run(rows)
        self._run(rows)
        self.assertEqual(BaseEvent.objects.filter(event_name='BRASA Carnival C26').count(), 1)

    def test_reuses_a_location_of_the_same_name(self):
        """ An existing room is matched case-insensitively rather than duplicated. """
        self._run([api_row(location='Odeum')])
        before = Location.objects.count()
        self._run([api_row(source_id=2, name='Another Show C26', location='odeum')])
        self.assertEqual(Location.objects.count(), before)

    def test_rows_without_a_name_or_date_are_skipped(self):
        broken = api_row(source_id=9)
        broken['datetime_start'] = ''
        self._run([broken])
        self.assertEqual(BaseEvent.objects.count(), 0)

    def test_dry_run_writes_nothing(self):
        path = self._write([api_row()])
        call_command('import_real_events', file=path, dry_run=True, verbosity=0)
        self.assertEqual(BaseEvent.objects.count(), 0)

    def test_unknown_user_is_an_error(self):
        path = self._write([api_row()])
        with self.assertRaises(CommandError):
            call_command('import_real_events', file=path, user='nobody', verbosity=0)


class ImportFromDumpdataTests(TestCase):
    """ The richer path, and the privacy rules that come with it. """

    def setUp(self):
        self.user = UserFactory.create(username='treasurer', is_superuser=True)

    def _dump(self, sensitive=False, include_child=True):
        start = timezone.now() - datetime.timedelta(days=30)
        rows = [
            {'model': 'events.building', 'pk': 3,
             'fields': {'name': 'Alden', 'shortname': 'ALD'}},
            {'model': 'events.location', 'pk': 7,
             'fields': {'name': 'Great Hall', 'building': 3}},
            {'model': 'events.organization', 'pk': 4,
             'fields': {'name': 'Masque', 'shortname': 'Masque', 'workday_fund': 810}},
            {'model': 'events.baseevent', 'pk': 21, 'fields': {
                'event_name': 'Masque Fall Production B26',
                'description': 'Public blurb.',
                'internal_notes': 'The client must never read this.',
                'location': 7,
                'billing_org': 4,
                'sensitive': sensitive,
                'test_event': False,
                'cancelled': False,
                'datetime_setup_complete': start.isoformat(),
                'datetime_start': start.isoformat(),
                'datetime_end': (start + datetime.timedelta(hours=4)).isoformat(),
            }},
        ]
        if include_child:
            rows.append({'model': 'events.event2019', 'pk': 21,
                         'fields': {'workday_fund': 810, 'worktag': 'SO1234'}})
        return rows

    def _run(self, rows):
        import os
        import tempfile
        handle = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
        json.dump(rows, handle)
        handle.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        call_command('import_real_events', file=handle.name, verbosity=0)

    def test_imports_the_billing_org_and_fund(self):
        """ ``workday_fund`` is what ``client_type_for`` reads; it has to survive. """
        self._run(self._dump())
        event = BaseEvent.objects.get(event_name='Masque Fall Production B26')
        self.assertEqual(event.billing_org.name, 'Masque')
        self.assertEqual(event.billing_org.workday_fund, 810)
        self.assertEqual(event.org.count(), 1)

    def test_internal_notes_are_not_copied(self):
        """
        ``internal_notes`` is documented as what the client should never see.
        The marker replaces it rather than sitting beside it.
        """
        self._run(self._dump())
        event = BaseEvent.objects.get(event_name='Masque Fall Production B26')
        self.assertNotIn('never read this', event.internal_notes)
        self.assertIn(IMPORT_MARKER, event.internal_notes)

    def test_sensitive_events_are_skipped(self):
        self._run(self._dump(sensitive=True))
        self.assertEqual(BaseEvent.objects.count(), 0)

    def test_user_foreign_keys_point_at_the_local_account(self):
        """ No production user rows are read, so everything hangs off one local user. """
        self._run(self._dump())
        event = BaseEvent.objects.get(event_name='Masque Fall Production B26')
        self.assertEqual(event.submitted_by, self.user)
        self.assertEqual(event.approved_by, self.user)

    def test_an_export_missing_the_parent_rows_is_an_error(self):
        """
        ``BaseEvent`` is polymorphic with multi-table inheritance, so a dump of
        ``events.Event2019`` alone is half of each event and no event names at
        all. Saying so beats importing nothing and reporting success.
        """
        child_only = [row for row in self._dump() if row['model'] == 'events.event2019']
        with self.assertRaises(CommandError):
            self._run(child_only)


class ClearTests(TestCase):
    """ ``--clear``, and the one thing it must refuse to delete. """

    def setUp(self):
        self.user = UserFactory.create(username='treasurer', is_superuser=True)
        import os
        import tempfile
        handle = tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w')
        json.dump([api_row(1, 'First Show C26'), api_row(2, 'Second Show C26')], handle)
        handle.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        self.path = handle.name
        call_command('import_real_events', file=self.path, verbosity=0)

    def test_clear_removes_what_was_imported(self):
        call_command('import_real_events', clear=True, verbosity=0)
        self.assertEqual(BaseEvent.objects.filter(
            internal_notes__contains=IMPORT_MARKER).count(), 0)

    def test_clear_leaves_hand_made_events_alone(self):
        from events.tests.generators import Event2019Factory
        Event2019Factory.create(event_name='Mine', submitted_by=self.user)
        call_command('import_real_events', clear=True, verbosity=0)
        self.assertTrue(BaseEvent.objects.filter(event_name='Mine').exists())

    def test_clear_keeps_events_a_transaction_is_linked_to(self):
        """
        ``ParsedTransaction.linked_event`` is ``PROTECT``. Deleting a reconciled
        event is the one mistake that loses work, so a linked event is kept and
        reported rather than being allowed to abort the run.
        """
        event = BaseEvent.objects.get(event_name='First Show C26')
        txn = WorkdayTransaction.objects.create(
            operational_transaction='ISD-1',
            accounting_date=datetime.date(2025, 9, 15), net_amount=500)
        ParsedTransaction.objects.create(
            parent_transaction=txn, amount=500, linked_event=event)

        call_command('import_real_events', clear=True, verbosity=0)

        self.assertTrue(BaseEvent.objects.filter(pk=event.pk).exists())
        self.assertFalse(BaseEvent.objects.filter(event_name='Second Show C26').exists())

    def test_clear_then_import_restores_them(self):
        call_command('import_real_events', clear=True, create=True,
                     file=self.path, verbosity=0)
        self.assertEqual(BaseEvent.objects.filter(
            internal_notes__contains=IMPORT_MARKER).count(), 2)
        self.assertEqual(Organization.objects.filter(
            notes__contains=IMPORT_MARKER).count(), 0)

"""
Import real events from the production LNLDB so revenue linking can be tested
against real event names.

Why this exists
---------------

``seed_test_events`` builds part of its set *out of* the memos already in the
ledger: it reads each ISD memo, extracts the event name, and creates an event
called exactly that. Reconciling revenue against those events therefore always
works, because the event was manufactured from the memo it is being matched to.
That is useful for exercising the picker, and worthless for measuring whether
:func:`finance.suggestions.suggest_linked_event` actually finds anything --
the match rate it reports is a property of the seeder.

Real event names are the only thing that answers that question. Matching is
deliberately ``iexact`` with nothing fuzzy about it (a filled box is the one
nobody re-reads), so the interesting cases are all the ways a Treasurer writes
a show's name into Workday that is not character-for-character what the
workorder called it. Those cases cannot be invented; they have to be imported.

Where the data comes from
-------------------------

Two sources, and the default needs no server access:

* **The public API** (``/api/v1/events``). Anonymous -- ``EventViewSet`` sets
  ``authentication_classes = []`` and the project declares no default
  permission class -- and pre-filtered to ``sensitive=False, test_event=False,
  approved=True``, so everything it returns is already public. It carries the
  name, date and location and nothing else. That is exactly the set of fields
  the memo lookup compares, and it is *not* enough to exercise
  :func:`finance.models.client_type_for`, which reads a billing org's
  ``workday_fund``.

  Mind the date range: with no ``start``/``end`` the endpoint quietly narrows
  itself to upcoming, unclosed events, which is the opposite of what
  reconciliation needs. This command always sends an explicit window.

* **A ``dumpdata`` export** from the server, via ``--file``. Richer -- billing
  org and Workday fund come with it -- but it is a dump of live records, so
  rows flagged ``sensitive`` are skipped, ``internal_notes`` is discarded
  rather than copied, and every user foreign key is repointed at one local
  account. No production user rows are ever read or written.

Usage::

    python manage.py import_real_events --fiscal-year 2026
    python manage.py import_real_events --file events_prod.json
    python manage.py import_real_events --clear             # remove them again
    python manage.py import_real_events --clear --create    # rebuild
    python manage.py import_real_events -y 2026 --dry-run   # look, write nothing

Everything written is tagged in ``internal_notes`` with :data:`IMPORT_MARKER`
plus the source event's id, which is what makes a second run a no-op and what
``--clear`` matches on. Deliberately not tagged ``test_event``:
:class:`finance.lookups.EventLookup` filters those out, so an event flagged
that way would be invisible to the picker this exists to feed.
"""
import datetime
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from events.models import (BaseEvent, Building, Event2019, Location, Organization,
                           ServiceInstance)
from finance.models import (ParsedTransaction, WorkdayTransaction, current_fiscal_year,
                            fiscal_year_bounds)
from finance.suggestions import event_name_from_transaction

#: Written into ``internal_notes`` on every row this command creates, followed
#: by ``id=<source pk>``. The bare marker is what ``--clear`` matches; the
#: marker with an id is what makes re-running this idempotent.
IMPORT_MARKER = '[lnldb-import:real-events]'

#: Where the production database lives. Overridable so a staging copy, or a
#: local second instance, can be pointed at instead.
DEFAULT_BASE_URL = 'https://lnl.wpi.edu'

#: A :class:`~events.models.Location` cannot exist without a building, and an
#: imported room name rarely matches one we already have. Rather than guess,
#: park the unknown ones here so they are obvious and easy to sweep up.
IMPORTED_BUILDING = ('Imported', 'IMP')


class Command(BaseCommand):
    """ Pull real events into a development database, or take them back out. """

    help = ('Import real events from the production LNLDB (public API by default) so '
            'the finance revenue-to-event linking can be tested against real names.')

    def add_arguments(self, parser):
        """ Wire up the source, the window, and the clear/create pair. """
        parser.add_argument(
            '--fiscal-year', '-y', type=int, nargs='+', metavar='FY',
            help='Fiscal year(s) to fetch, e.g. "-y 2026" or "-y 2025 2026". '
                 'Defaults to the current fiscal year.')
        parser.add_argument(
            '--start', help='Start of the window as YYYY-MM-DD, overriding --fiscal-year.')
        parser.add_argument(
            '--end', help='End of the window as YYYY-MM-DD, overriding --fiscal-year.')
        parser.add_argument(
            '--file', help='Read events from a JSON file instead of the API. Accepts '
                           'either the API response shape or a dumpdata export.')
        parser.add_argument(
            '--url', default=DEFAULT_BASE_URL,
            help='Base URL of the instance to read from (default %s).' % DEFAULT_BASE_URL)
        parser.add_argument(
            '--user', help='Username to record as the submitter. Defaults to a superuser.')
        parser.add_argument(
            '--clear', action='store_true',
            help='Remove everything a previous run of this command created.')
        parser.add_argument(
            '--create', action='store_true',
            help='Import the events. Implied unless --clear is given on its own.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be imported without writing anything.')
        parser.add_argument(
            '--timeout', type=int, default=30, help='API timeout in seconds (default 30).')

    def handle(self, *args, **options):
        """ Clear, import, or both, inside one transaction. """
        do_clear = options['clear']
        do_create = options['create'] or not do_clear
        dry_run = options['dry_run']

        with transaction.atomic():
            if do_clear:
                self._clear(dry_run)
            if do_create:
                rows = self._collect(options)
                self._import(rows, options, dry_run)
            self._report_match_rate()
            if dry_run:
                # Everything above ran for its output; none of it should land.
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('Dry run: nothing was written.'))

    # -- sources ------------------------------------------------------------
    def _collect(self, options):
        """ Normalised event dicts from whichever source was asked for. """
        if options['file']:
            return self._from_file(options['file'])
        return self._from_api(options)

    def _window(self, options):
        """
        The ``(start, end)`` datetimes to ask the API for.

        Fiscal years are resolved through :func:`finance.models.fiscal_year_bounds`
        rather than hardcoded months, because the boundary is a configurable
        setting and a window that disagreed with it would quietly miss the edges
        of the year being reconciled.
        """
        if options['start'] or options['end']:
            if not (options['start'] and options['end']):
                raise CommandError('--start and --end must be given together.')
            first = self._parse_date(options['start'])
            last = self._parse_date(options['end'])
        else:
            years = options['fiscal_year'] or [current_fiscal_year()]
            bounds = [fiscal_year_bounds(year) for year in years]
            first = min(bound[0] for bound in bounds)
            last = max(bound[1] for bound in bounds)

        start = timezone.make_aware(datetime.datetime.combine(first, datetime.time.min))
        end = timezone.make_aware(datetime.datetime.combine(last, datetime.time.max))
        return start, end

    @staticmethod
    def _parse_date(text):
        """ ``YYYY-MM-DD`` to a date, with a message that says what was wrong. """
        try:
            return datetime.datetime.strptime(text, '%Y-%m-%d').date()
        except ValueError:
            raise CommandError('Dates must be YYYY-MM-DD; got "%s".' % text)

    def _from_api(self, options):
        """
        Fetch the window from ``/api/v1/events``.

        A 204 means the endpoint matched nothing, which it reports with a body
        rather than an empty list -- so the status code is checked before the
        JSON is, or an empty result looks like one event called ``204``.
        """
        try:
            import requests
        except ImportError:  # pragma: no cover - requests is in requirements.txt
            raise CommandError('The requests library is needed to read the API; '
                               'use --file instead.')

        start, end = self._window(options)
        url = options['url'].rstrip('/') + '/api/v1/events'
        params = {'start': start.isoformat(), 'end': end.isoformat()}
        self.stdout.write('Fetching events from %s (%s to %s)...'
                          % (url, start.date(), end.date()))
        try:
            response = requests.get(url, params=params, timeout=options['timeout'])
        except Exception as error:
            raise CommandError('Could not reach %s: %s' % (url, error))

        if response.status_code == 204:
            return []
        if response.status_code != 200:
            raise CommandError('%s returned HTTP %s.' % (url, response.status_code))
        try:
            payload = response.json()
        except ValueError:
            raise CommandError('%s did not return JSON. Is the URL right?' % url)
        if not isinstance(payload, list):
            return []
        return [self._from_api_row(row) for row in payload]

    @staticmethod
    def _from_api_row(row):
        """
        One API record in the shape :meth:`_import` expects.

        The serializer exposes six fields and no more, so the billing org and
        the Workday fund are simply absent here -- not guessed at. An event
        with no org classifies as neither a student org nor a department, which
        is the honest answer for a row that never carried one.
        """
        return {
            'source_id': row.get('id'),
            'event_name': (row.get('event_name') or '').strip(),
            'description': row.get('description') or '',
            'location_name': (row.get('location') or '').strip(),
            'datetime_start': parse_datetime(row.get('datetime_start') or ''),
            'datetime_end': parse_datetime(row.get('datetime_end') or ''),
            'datetime_setup_complete': None,
            'org_name': None,
            'workday_fund': None,
            'cancelled': False,
        }

    def _from_file(self, path):
        """ Read either export shape out of ``path``. """
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle)
        except (IOError, OSError) as error:
            raise CommandError('Could not read %s: %s' % (path, error))
        except ValueError as error:
            raise CommandError('%s is not valid JSON: %s' % (path, error))

        if not isinstance(payload, list):
            raise CommandError('%s should contain a list of events.' % path)
        if payload and isinstance(payload[0], dict) and 'model' in payload[0]:
            return self._from_dumpdata(payload)
        return [self._from_api_row(row) for row in payload]

    def _from_dumpdata(self, payload):
        """
        Flatten a ``dumpdata`` export into the same normalised dicts.

        ``BaseEvent`` is a polymorphic model using multi-table inheritance, so a
        complete export is two rows per event: ``events.baseevent`` holds the
        name, dates and location, and ``events.event2019`` holds the Workday
        fund. They are joined here on the primary key, and an export missing
        either half is reported rather than half-imported.

        Locations and organizations are resolved against the same file, because
        neither model defines a natural key and their raw primary keys mean
        nothing in this database.
        """
        by_model = {}
        for row in payload:
            by_model.setdefault(row.get('model'), {})[row.get('pk')] = row.get('fields', {})

        base = by_model.get('events.baseevent', {})
        extra = by_model.get('events.event2019', {})
        locations = by_model.get('events.location', {})
        orgs = by_model.get('events.organization', {})
        if not base:
            raise CommandError(
                'No events.baseevent rows in that file. A complete export needs both '
                '"events.BaseEvent" and "events.Event2019" -- dumping either one alone '
                'gives you half of each event.')
        if not extra:
            self.stdout.write(self.style.WARNING(
                'No events.event2019 rows in that file, so no Workday funds will be '
                'imported and the client-type split stays untested.'))

        rows = []
        skipped_sensitive = 0
        for pk, fields in base.items():
            # These two are the whole of the privacy filter on this path: an
            # event nobody outside it should know about does not belong in a
            # development database at all, marker or no marker.
            if fields.get('sensitive') or fields.get('test_event'):
                skipped_sensitive += 1
                continue
            location = locations.get(fields.get('location')) or {}
            org = orgs.get(fields.get('billing_org')) or {}
            rows.append({
                'source_id': pk,
                'event_name': (fields.get('event_name') or '').strip(),
                'description': fields.get('description') or '',
                'location_name': (location.get('name') or '').strip(),
                'datetime_start': parse_datetime(fields.get('datetime_start') or ''),
                'datetime_end': parse_datetime(fields.get('datetime_end') or ''),
                'datetime_setup_complete': parse_datetime(
                    fields.get('datetime_setup_complete') or ''),
                'org_name': (org.get('name') or '').strip() or None,
                # The event's own fund wins over the org's; client_type_for reads
                # it in that order and a mismatch here would misclassify.
                'workday_fund': ((extra.get(pk) or {}).get('workday_fund')
                                 or org.get('workday_fund')),
                'cancelled': bool(fields.get('cancelled')),
            })

        if skipped_sensitive:
            self.stdout.write(self.style.WARNING(
                'Skipped %d sensitive or test event(s).' % skipped_sensitive))
        return rows

    # -- import -------------------------------------------------------------
    def _import(self, rows, options, dry_run):
        """ Write one event per source row, skipping any already imported. """
        usable = [row for row in rows
                  if row['event_name'] and row['datetime_start'] and row['datetime_end']]
        malformed = len(rows) - len(usable)
        if not usable:
            self.stdout.write(self.style.WARNING(
                'Nothing to import. If you read from the API, check the date window -- '
                'without one it only returns upcoming events.'))
            return

        user = self._pick_user(options['user'])
        created = 0
        existing = 0
        for row in usable:
            marker = '%s id=%s' % (IMPORT_MARKER, row['source_id'])
            if BaseEvent.objects.filter(internal_notes__contains=marker).exists():
                existing += 1
                continue
            if not dry_run:
                self._create_event(row, user, marker)
            created += 1

        self.stdout.write(self.style.SUCCESS(
            'Imported %d real event(s) (%d already present%s).'
            % (created, existing, ', %d unusable' % malformed if malformed else '')))

    def _create_event(self, row, user, marker):
        """
        Write one event, its location, and its billing org if we know one.

        Every user foreign key points at ``user``: the submitter, contact and
        approver on the real record are people, and copying them here would mean
        importing production user rows into an unencrypted development database
        to satisfy a ``PROTECT`` constraint that nothing in finance reads.
        """
        org = self._organization(row['org_name'], row['workday_fund'], user)
        start = row['datetime_start']
        setup = row['datetime_setup_complete'] or (start - datetime.timedelta(hours=2))
        past = row['datetime_end'] < timezone.now()

        event = Event2019.objects.create(
            event_name=row['event_name'][:128],
            submitted_by=user,
            submitted_ip='127.0.0.1',
            location=self._location(row['location_name']),
            billing_org=org,
            datetime_setup_complete=setup,
            datetime_start=start,
            datetime_end=row['datetime_end'],
            description=row['description'],
            # The marker replaces the real notes rather than sitting beside
            # them: internal_notes is documented as what the client should
            # never see, and it has no business being copied off the server.
            internal_notes=marker,
            workday_fund=row['workday_fund'],
            cancelled=row['cancelled'],
            approved=True,
            approved_on=start,
            approved_by=user,
            closed=past,
            closed_on=row['datetime_end'] if past else None,
            closed_by=user if past else None,
            event_status='Post Event' if past else 'Confirmed',
            # Explicitly false: EventLookup excludes test events, so flagging
            # these would hide them from the picker they exist to feed.
            test_event=False,
        )
        if org:
            event.org.add(org)
        return event

    def _pick_user(self, username):
        """ Somebody local to hang every user foreign key off. """
        User = get_user_model()
        if username:
            user = User.objects.filter(username=username).first()
            if user is None:
                raise CommandError('No user named "%s" in this database.' % username)
            return user
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if user is None:
            raise CommandError(
                'No users exist, and an event needs a submitter. '
                'Create one with `manage.py createsuperuser` first.')
        return user

    def _location(self, name):
        """
        The local room of that name, or a new one under the Imported building.

        Matching is case-insensitive on the name alone. Buildings are not part
        of the API response, so an imported room that happens to share a name
        with one we already have is assumed to be it -- wrong only where two
        buildings hold rooms of the same name, and harmless here because
        nothing in finance reads the location.
        """
        if name:
            match = Location.objects.filter(name__iexact=name).first()
            if match:
                return match
        building, _ = Building.objects.get_or_create(
            name=IMPORTED_BUILDING[0], defaults={'shortname': IMPORTED_BUILDING[1]})
        return Location.objects.create(
            name=(name or 'Unknown')[:64], building=building, show_in_wo_form=False)

    def _organization(self, name, workday_fund, user):
        """
        The client of that name, created if we have not seen it before.

        ``workday_fund`` is the point of importing orgs at all: it is what
        :func:`finance.models.client_type_for` reads to call a payer a student
        organization rather than a department. An existing org keeps whatever
        fund it already has -- a local edit is more likely to be right than a
        value copied out of an export.
        """
        if not name:
            return None
        org, created = Organization.objects.get_or_create(
            name=name[:128],
            defaults={
                'shortname': name[:8],
                'phone': '',
                'user_in_charge': user,
                'workday_fund': workday_fund,
                'notes': IMPORT_MARKER,
            })
        if created:
            org.associated_users.add(user)
        elif workday_fund and org.workday_fund is None:
            org.workday_fund = workday_fund
            org.save(update_fields=['workday_fund'])
        return org

    # -- removal ------------------------------------------------------------
    def _clear(self, dry_run):
        """
        Delete every row a previous run created, except those now in use.

        ``ParsedTransaction.linked_event`` is a ``PROTECT`` foreign key, so an
        event the Treasurer has already reconciled revenue against cannot be
        deleted -- and should not be, since deleting it is exactly the mistake
        that would lose the link. Those are reported and left alone rather than
        being allowed to abort the whole run.
        """
        events = BaseEvent.objects.filter(internal_notes__contains=IMPORT_MARKER)
        linked = set(ParsedTransaction.objects
                     .filter(linked_event__in=events)
                     .values_list('linked_event_id', flat=True))
        removable = events.exclude(pk__in=linked)
        count = removable.count()

        if dry_run:
            org_count = Organization.objects.filter(notes__contains=IMPORT_MARKER).count()
        else:
            ServiceInstance.objects.filter(event__in=removable).delete()
            # Clearing the M2M first; deleting an event does not detach it and
            # the org delete below would otherwise still see the link.
            for event in removable:
                event.org.clear()
            removable.delete()

            orgs = Organization.objects.filter(
                notes__contains=IMPORT_MARKER, events__isnull=True,
                billedevents__isnull=True)
            org_count = orgs.count()
            orgs.delete()

            rooms = Location.objects.filter(
                building__name=IMPORTED_BUILDING[0], baseevent__isnull=True)
            try:
                rooms.delete()
            except ProtectedError:
                # Something outside events -- a meeting, say -- still books the
                # room. Leaving it costs nothing; failing the clear costs a run.
                pass

        self.stdout.write(self.style.WARNING(
            'Removed %d imported event(s) and %d imported organization(s).'
            % (count, org_count)))
        if linked:
            self.stdout.write(self.style.WARNING(
                'Kept %d event(s) that reconciled transactions still point at.'
                % len(linked)))

    # -- reporting ----------------------------------------------------------
    def _report_match_rate(self):
        """
        How many revenue memos now name an event that exists.

        This is the number the whole exercise is for, and it is split three
        ways on purpose. A memo matched only by a seeded event is not evidence
        of anything: ``seed_test_events`` created that event *from* this memo,
        so the match is circular. Only the first line is a real result.
        """
        names = {}
        for txn in WorkdayTransaction.objects.filter(net_amount__gt=0):
            name = event_name_from_transaction(txn)
            if name:
                names.setdefault(name.lower(), name)

        if not names:
            self.stdout.write('No revenue memos in the ledger to match against yet.')
            return

        real = seeded = 0
        unmatched = []
        for name in names.values():
            candidates = BaseEvent.objects.filter(
                event_name__iexact=name, cancelled=False, test_event=False)
            if candidates.filter(internal_notes__contains=IMPORT_MARKER).exists():
                real += 1
            elif candidates.exists():
                seeded += 1
            else:
                unmatched.append(name)

        self.stdout.write('')
        self.stdout.write('Revenue memos naming an event: %d' % len(names))
        self.stdout.write(self.style.SUCCESS(
            '  matched by a real imported event: %d' % real))
        self.stdout.write('  matched only by a seeded event:   %d' % seeded)
        self.stdout.write('  not matched at all:               %d' % len(unmatched))
        for name in sorted(unmatched)[:10]:
            self.stdout.write('      %s' % name)
        if len(unmatched) > 10:
            self.stdout.write('      ... and %d more' % (len(unmatched) - 10))

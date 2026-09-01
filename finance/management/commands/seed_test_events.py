"""
Populate the database with events for exercising the "Link to Event" picker.

The finance pages let a Treasurer attach a bank line to an event, but there is
nothing to attach it to on a fresh checkout -- and an autocomplete with one row
behind it cannot be told apart from an autocomplete that is broken. This
command fills that gap with a spread of realistic, searchable events.

Everything it writes is tagged in ``internal_notes`` with :data:`SEED_MARKER`
so ``--clear`` can find it again. Deliberately **not** tagged with
``test_event``: :class:`finance.lookups.EventLookup` filters those out, so an
event flagged that way would be invisible to the very picker this exists to
exercise.

It creates two sets of events, and the second is the useful one:

* a generic spread across recent fiscal years, so the picker has plenty to
  search and the dashboard charts have a shape; and
* **one event per ISD memo already imported into this database**, named exactly
  the way the memo names it. That is what makes
  :func:`finance.suggestions.suggest_linked_event` demonstrably work: reconcile
  a revenue line and the event should already be filled in.

Usage::

    python manage.py seed_test_events              # create (idempotent)
    python manage.py seed_test_events --clear      # remove them again
    python manage.py seed_test_events --clear --create      # rebuild
    python manage.py seed_test_events --no-from-memos       # generic set only
"""
import datetime
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from events.models import (BaseEvent, Event2019, Location, Organization, Service,
                           ServiceInstance)
from finance.models import WorkdayTransaction, current_fiscal_year, fiscal_year_bounds
from finance.suggestions import event_name_from_transaction

#: Written into ``internal_notes`` on every row this command creates, and the
#: only thing ``--clear`` matches on. A marker beats a name prefix because the
#: names have to look real to be worth searching for.
SEED_MARKER = '[lnldb-seed:finance-test-events]'

#: The Workday fund that means "student organization" -- see
#: :attr:`finance.models.FinanceSettings.student_org_workday_fund`. Clients
#: split into student orgs and departments on this, and the dashboard's
#: client-type breakdown is meaningless unless both kinds exist.
STUDENT_ORG_FUND = 810
DEPARTMENT_FUND = 110

#: ``(name, shortname, is_student_org)``. A deliberate mix so the client-type
#: chart has both slices and the org search has several plausible near-misses.
ORGANIZATIONS = [
    ('Student Activities Board', 'SAB', True),
    ('Masque', 'Masque', True),
    ('Alden Voices', 'Voices', True),
    ('International Students Council', 'ISC', True),
    ('Society of Women Engineers', 'SWE', True),
    ('WPI Music Department', 'Music', False),
    ('Office of Student Activities', 'OSA', False),
    ('Athletics Department', 'Athletics', False),
]

#: ``(event name, org shortname, [service shortnames])``. Names are varied on
#: purpose: a picker is only really tested by terms that match several rows,
#: terms that match one, and terms that match none.
EVENT_TEMPLATES = [
    ('Spring Concert', 'SAB', ['L4', 'S3']),
    ('Fall Concert', 'SAB', ['L3', 'S3']),
    ('Comedy Night', 'SAB', ['L2', 'S2']),
    ('Winter Formal', 'SAB', ['L3', 'S2']),
    ('Masque Fall Production', 'Masque', ['L4', 'S2']),
    ('Masque Spring Production', 'Masque', ['L4', 'S3']),
    ('New Voices Festival', 'Masque', ['L2', 'S1']),
    ('A Cappella Showcase', 'Voices', ['L2', 'S2']),
    ('Winter A Cappella Jam', 'Voices', ['L1', 'S2']),
    ('International Night', 'ISC', ['L3', 'S3']),
    ('Culture Show', 'ISC', ['L3', 'S2']),
    ('SWE Banquet', 'SWE', ['L1', 'S1']),
    ('Engineering Career Fair', 'SWE', ['S1']),
    ('Orchestra Winter Concert', 'Music', ['L2', 'S2']),
    ('Jazz Ensemble Recital', 'Music', ['L1', 'S1']),
    ('Choral Spring Concert', 'Music', ['L2', 'S2']),
    ('New Student Orientation', 'OSA', ['L1', 'S2']),
    ('Accepted Students Day', 'OSA', ['S2']),
    ('Homecoming Rally', 'Athletics', ['L3', 'S3']),
    ('Athletics Awards Banquet', 'Athletics', ['L1', 'S1']),
    ('Senior Week Movie Night', 'SAB', ['35']),
    ('Outdoor Film Screening', 'SAB', ['70']),
]


class Command(BaseCommand):
    """ Create (or remove) a realistic set of events for testing event linking. """

    help = ('Populate the database with searchable test events so the finance '
            '"Link to Event" autocomplete can be exercised.')

    def add_arguments(self, parser):
        """ Wire up ``--clear``, ``--create`` and ``--years``. """
        parser.add_argument(
            '--clear', action='store_true',
            help='Remove everything a previous run of this command created.')
        parser.add_argument(
            '--create', action='store_true',
            help='Create the events. Implied unless --clear is given on its own.')
        parser.add_argument(
            '--years', type=int, default=3,
            help='How many fiscal years back to spread the events over (default 3).')
        parser.add_argument(
            '--no-from-memos', action='store_true',
            help='Skip creating events named after the ISD memos already imported.')

    def handle(self, *args, **options):
        """ Clear, create, or both, inside one transaction. """
        do_clear = options['clear']
        do_create = options['create'] or not do_clear

        with transaction.atomic():
            if do_clear:
                self._clear()
            if do_create:
                self._create(options['years'])
                if not options['no_from_memos']:
                    self._create_from_memos()

    # -- removal ------------------------------------------------------------
    def _clear(self):
        """
        Delete every row a previous run created, events before orgs.

        Ordering matters: an organization cannot go while an event still points
        at it, and the FK is not a cascade.
        """
        events = BaseEvent.objects.filter(internal_notes__contains=SEED_MARKER)
        event_count = events.count()
        ServiceInstance.objects.filter(event__in=events).delete()
        # Clearing the M2M first; deleting an event does not detach it and the
        # org delete below would otherwise still see the link.
        for event in events:
            event.org.clear()
        events.delete()

        orgs = Organization.objects.filter(notes__contains=SEED_MARKER)
        org_count = orgs.count()
        orgs.delete()

        self.stdout.write(self.style.WARNING(
            'Removed %d seeded event(s) and %d seeded organization(s).'
            % (event_count, org_count)))

    # -- creation -----------------------------------------------------------
    def _create(self, years):
        """ Create the organizations, then a run of events across ``years``. """
        user = self._pick_user()
        locations = list(Location.objects.all()[:20])
        if not locations:
            raise CommandError(
                'No Location rows exist, and an event cannot be saved without one. '
                'Load the events fixtures first.')

        orgs = self._create_organizations(user)
        services = {s.shortname: s for s in Service.objects.all()}
        if not services:
            self.stdout.write(self.style.WARNING(
                'No Service rows exist; events will be created without services, so '
                'the dashboard service-mix chart will have nothing to draw.'))

        # Seeded so a re-run produces the same dates rather than a second,
        # slightly different set of events on top of the first.
        rng = random.Random(20260820)

        created = 0
        existing = 0
        for offset in range(years):
            fiscal_year = current_fiscal_year() - offset
            start, end = fiscal_year_bounds(fiscal_year)
            span = (end - start).days

            for index, (name, org_short, service_names) in enumerate(EVENT_TEMPLATES):
                # Spread the events evenly through the year, then jitter, so the
                # cash-flow chart has something with a shape to it.
                base = int(span * (index + 0.5) / len(EVENT_TEMPLATES))
                day = start + datetime.timedelta(days=base + rng.randint(-9, 9))
                day = min(max(day, start), end)

                event_name = '%s %s' % (name, fiscal_year)
                if BaseEvent.objects.filter(event_name=event_name).exists():
                    existing += 1
                    continue

                self._create_event(
                    event_name=event_name,
                    day=day,
                    org=orgs[org_short],
                    user=user,
                    location=rng.choice(locations),
                    services=[services[s] for s in service_names if s in services],
                    rng=rng,
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            'Created %d event(s) across FY%s-FY%s (%d already present).'
            % (created, current_fiscal_year() - years + 1, current_fiscal_year(), existing)))
        self.stdout.write(
            'Search the "Link to Event" box for "concert", "masque" or "SAB" to try it.')

    def _create_from_memos(self):
        """
        Create an event for every ISD memo in the ledger that names one.

        This is what makes the memo lookup testable rather than merely
        plausible. Reconciling revenue is only worth watching if the event the
        memo names actually exists, and on a development database it generally
        does not -- the Workday export is real and the events beside it are not.

        Each event is dated three weeks before the accounting date, because an
        ISD is raised after the show rather than before it, and that ordering is
        what :func:`finance.suggestions.suggest_linked_event` breaks ties on
        when the same event has run in several years.
        """
        rows = [t for t in WorkdayTransaction.objects.filter(net_amount__gt=0)
                if event_name_from_transaction(t)]
        if not rows:
            self.stdout.write(
                'No imported ISD memos to build events from; import a Workday export '
                'first if you want to watch the event auto-fill.')
            return

        user = self._pick_user()
        locations = list(Location.objects.all()[:20])
        orgs = self._create_organizations(user)
        services = {s.shortname: s for s in Service.objects.all()}
        rng = random.Random(20260821)

        # Earliest accounting date wins, so an event billed twice is dated from
        # the first invoice rather than whichever row happened to come last.
        wanted = {}
        for txn in rows:
            name = event_name_from_transaction(txn)
            if name not in wanted or txn.accounting_date < wanted[name].accounting_date:
                wanted[name] = txn

        created = 0
        existing = 0
        for name, txn in sorted(wanted.items()):
            # iexact, because the lookup matches that way: the memos spell the
            # same show "CS Social Movies" one month and "CS social movies" the
            # next, and seeding both would make the match ambiguous.
            if BaseEvent.objects.filter(event_name__iexact=name).exists():
                existing += 1
                continue

            # A line carrying a student organization worktag was billed to a
            # student org; anything else is a department. Rough, but it keeps
            # the dashboard's client split from being all one colour.
            is_student_org = bool((txn.worktag('student_organization') or '').strip())
            pool = [short for _, short, student in ORGANIZATIONS if student == is_student_org]

            self._create_event(
                event_name=name,
                day=txn.accounting_date - datetime.timedelta(days=21),
                org=orgs[rng.choice(pool)],
                user=user,
                location=rng.choice(locations),
                services=[services[s] for s in rng.choice(
                    [['L2', 'S2'], ['L3', 'S3'], ['L1', 'S1']]) if s in services],
                rng=rng,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            'Created %d event(s) named after imported ISD memos (%d already present).'
            % (created, existing)))
        if created:
            self.stdout.write(
                'Open the queue on a revenue line -- the event should already be filled in.')

    def _pick_user(self):
        """
        Somebody to record as having submitted the events.

        Any user will do -- this is a required FK and nothing here reads it
        back -- so prefer a superuser and fall back to whoever exists.
        """
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if user is None:
            raise CommandError(
                'No users exist, and an event needs a submitter. '
                'Create one with `manage.py createsuperuser` first.')
        return user

    def _create_organizations(self, user):
        """
        Get or create the client orgs, keyed on name so re-runs reuse them.

        The ``workday_fund`` is the point of the exercise: it is what
        :attr:`finance.models.ParsedTransaction.client_type` reads to call a
        client a student organization rather than a department.
        """
        orgs = {}
        for name, shortname, is_student_org in ORGANIZATIONS:
            org, was_created = Organization.objects.get_or_create(
                name=name,
                defaults={
                    'shortname': shortname,
                    'email': '%s@wpi.edu' % shortname.lower().replace(' ', ''),
                    'phone': '508-831-5000',
                    'user_in_charge': user,
                    'workday_fund': STUDENT_ORG_FUND if is_student_org else DEPARTMENT_FUND,
                    'notes': SEED_MARKER,
                })
            if was_created:
                org.associated_users.add(user)
            orgs[shortname] = org
        return orgs

    def _create_event(self, event_name, day, org, user, location, services, rng):
        """
        Write one event, its org link and its service instances.

        ``workday_fund`` is copied onto the event as well as the org because
        :attr:`~finance.models.ParsedTransaction.client_type` looks at the
        event first and only falls back to the billing org -- so an event that
        did not carry it would classify correctly only by accident.
        """
        hour = rng.choice([14, 18, 19, 20])
        start = timezone.make_aware(
            datetime.datetime.combine(day, datetime.time(hour, 0)))
        event = Event2019.objects.create(
            event_name=event_name,
            submitted_by=user,
            submitted_ip='127.0.0.1',
            location=location,
            billing_org=org,
            datetime_setup_complete=start - datetime.timedelta(hours=3),
            datetime_start=start,
            datetime_end=start + datetime.timedelta(hours=rng.choice([2, 3, 4])),
            description='Seeded event for exercising the finance event picker.',
            internal_notes=SEED_MARKER,
            workday_fund=org.workday_fund,
            approved=True,
            approved_on=timezone.now(),
            approved_by=user,
            closed=True,
            # Explicitly false: EventLookup excludes test events, so flagging
            # these would hide them from the picker they exist to exercise.
            test_event=False,
        )
        event.org.add(org)
        for service in services:
            ServiceInstance.objects.create(service=service, event=event)
        return event

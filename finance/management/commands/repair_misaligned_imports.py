"""
Find bank lines whose columns were shifted by a bad CSV parse, and retire them.

Between the first Workday imports and the fix in :func:`finance.importers._read_csv`,
``csv.Sniffer`` was allowed to choose the whole dialect rather than only the
delimiter. On some exports it guessed ``doublequote=False``, which breaks the
RFC-4180 ``""`` escape -- so a memo containing a quote (``Stereo 1/4" cables``)
split at its own commas instead of staying one cell. Everything to the right of
that memo shifted one or more columns: the memo tail landed in Fund, Fund landed
in Ledger Account, and Student Organization and Program fell off the end.

Such a row imports and reads plausibly. Its damage shows up twice:

* every worktag on it is wrong, so it lands in the wrong bucket in any report
  that groups by fund, cost center, ledger account or spend category; and
* its fingerprint is a hash of those wrong values, so the *correctly* parsed
  version of the same line from the next export is not recognised as a
  duplicate. The charge is then in the ledger twice.

This command finds those rows by the one mark the shift always leaves -- a
worktag holding something that is not a worktag -- pairs each with the correctly
parsed line if one has since been imported, moves any allocation slices across,
and hard-deletes the bad row.

It prints what it would do and changes nothing unless ``--apply`` is given::

    python manage.py repair_misaligned_imports              # report only
    python manage.py repair_misaligned_imports --apply      # do it
    python manage.py repair_misaligned_imports --pk 779     # one row

A row with no correctly parsed counterpart is reported and left alone: deleting
it would lose the charge entirely, and re-importing the export it came from is
the right fix.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from finance.importers import _near_duplicate_key
from finance.models import ParsedTransaction, WorkdayTransaction

#: A Fund worktag reads like ``810-FD Agency``: digits, a hyphen, a code. Anything
#: else in that column is a fragment of some other cell that arrived there by a
#: column shift -- it is the narrowest test that caught every known case without
#: touching a legitimate row.
FUND_PATTERN = re.compile(r'^\d+\s*-\s*[A-Za-z]{2,}')


def looks_misaligned(txn):
    """
    Whether this row's worktags show the mark of a column shift.

    Only Fund is tested. It is the first column after the two memos, so it is
    the first to be hit by a memo that split, and it has the strictest shape of
    any worktag -- which makes "this is not a Fund" a safe thing to assert.
    """
    fund = (txn.worktag('fund') or '').strip()
    return bool(fund) and not FUND_PATTERN.match(fund)


class Command(BaseCommand):
    help = "Retire bank lines whose columns were shifted by the old CSV parser."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help="Actually move the slices and delete the bad rows.")
        parser.add_argument('--pk', type=int, action='append', dest='pks',
                            help="Only consider this transaction (repeatable).")

    def handle(self, *args, **options):
        rows = WorkdayTransaction.objects.all()
        if options.get('pks'):
            rows = rows.filter(pk__in=options['pks'])

        damaged = [txn for txn in rows if looks_misaligned(txn)]
        if not damaged:
            self.stdout.write(self.style.SUCCESS("No misaligned rows found."))
            return

        plans, orphans = [], []
        for txn in damaged:
            replacement = self._replacement_for(txn)
            (plans if replacement else orphans).append((txn, replacement))

        for txn, replacement in plans:
            slices = list(ParsedTransaction.objects.filter(parent_transaction=txn))
            self.stdout.write(
                "#%s %s %s %s\n"
                "    fund reads %r -- misaligned\n"
                "    replaced by #%s, correctly parsed from %r\n"
                "    %s slice(s) to move: %s\n"
                % (txn.pk, txn.accounting_date, txn.payee, txn.net_amount,
                   txn.worktag('fund'), replacement.pk, replacement.source_file,
                   len(slices),
                   ", ".join("#%s %s" % (s.pk, s.amount) for s in slices) or "none"))

        for txn, _ in orphans:
            self.stdout.write(self.style.WARNING(
                "#%s %s %s %s\n"
                "    fund reads %r -- misaligned, but nothing has replaced it.\n"
                "    Re-import the export it came from (%r), then run this again.\n"
                % (txn.pk, txn.accounting_date, txn.payee, txn.net_amount,
                   txn.worktag('fund'), txn.source_file)))

        if not options['apply']:
            self.stdout.write(self.style.NOTICE(
                "Dry run -- nothing changed. Re-run with --apply to carry it out."))
            return

        with transaction.atomic():
            for txn, replacement in plans:
                # Not a queryset .update(): these slices carry an audit trail and
                # the model's own save() is what keeps it honest.
                for slice_ in ParsedTransaction.objects.filter(parent_transaction=txn):
                    slice_.parent_transaction = replacement
                    slice_.save()
                WorkdayTransaction.objects.filter(pk=txn.pk).hard_delete()

        self.stdout.write(self.style.SUCCESS(
            "Repaired %s row(s); %s left for a re-import." % (len(plans), len(orphans))))

    def _replacement_for(self, txn):
        """
        The correctly parsed version of ``txn``, if one has been imported.

        Matched on date, amount, document and payee -- the fields that come off
        their own columns and so survive the shift that ruined the rest. A
        candidate must itself look well-formed, or a second damaged copy of the
        same line would qualify.
        """
        key = _near_duplicate_key(txn)
        if key is None:
            return None
        for other in WorkdayTransaction.objects.filter(
                accounting_date=txn.accounting_date,
                net_amount=txn.net_amount).exclude(pk=txn.pk):
            if _near_duplicate_key(other) == key and not looks_misaligned(other):
                return other
        return None

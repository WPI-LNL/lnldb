"""
Encumbrances have no date. Money is encumbered from the day it is logged until
its Workday line is matched, so an encumbrance's open lines are dated the day
it was logged.

The date used to be "roughly when the money will go out", and a line dated
after today didn't count on the Balances tab yet. This pulls every open line
dated after the day its encumbrance was logged back to that day, so it counts
now. A line dated earlier keeps its date, and the fiscal year that goes with
it. Unapplying it dates each encumbrance by its earliest open line.
"""

from django.db import migrations
from django.utils import timezone


def date_open_lines_when_logged(apps, schema_editor):
    ParsedTransaction = apps.get_model('finance', 'ParsedTransaction')
    for line in (ParsedTransaction.objects
                 .filter(encumbrance__isnull=False, parent_transaction__isnull=True)
                 .select_related('encumbrance')):
        logged_on = timezone.localdate(line.encumbrance.created_on)
        if line.effective_date > logged_on:
            line.effective_date = logged_on
            line.save(update_fields=['effective_date'])


def date_encumbrances_by_their_lines(apps, schema_editor):
    Encumbrance = apps.get_model('finance', 'Encumbrance')
    for header in Encumbrance.objects.all():
        first = header.lines.order_by('effective_date').first()
        header.effective_date = (first.effective_date if first is not None
                                 else timezone.localdate(header.created_on))
        header.save(update_fields=['effective_date'])


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0020_finance_officers_only'),
    ]

    operations = [
        migrations.RunPython(date_open_lines_when_logged, date_encumbrances_by_their_lines),
        migrations.AlterModelOptions(
            name='encumbrance',
            options={'ordering': ('-created_on', '-pk')},
        ),
        migrations.RemoveField(
            model_name='encumbrance',
            name='effective_date',
        ),
    ]

"""
The fund an expense falls back to when nothing in the export identifies one.

Every LNL expense has to name a fund, and until now the queue left that box
blank on almost all of them. The reason was sound and still is: 810-FD is the
agency fund the whole account sits in, so it appears on every line whoever
actually paid, and reading "SGA Budget" off it would have been a coin flip
presented as a fact. See :func:`finance.suggestions.suggest_fund_source`.

The answer is not to read the worktag but to let the Treasurer state the
fallback once, in the admin, and to label it honestly on the row: the queue
says "LNL's stated default" rather than claiming the export said so. That keeps
the distinction the module is built on -- a lookup is what Workday told us --
while ending the one thing that made reconciling a typing job rather than a
confirming one.

Seeding is ``update`` on the row's slug rather than a blanket default, and it
leaves an already-chosen default alone, for the same reason every other seed
here does: a migration may not overwrite an admin edit.
"""
from django.db import migrations, models

#: The fund LNL spends out of unless something says otherwise.
#:
#: Legacy, on the Treasurer's say-so. An out-of-cycle award names its request
#: number in the memo, and the SGA standing budget is not what an unlabelled
#: line turns out to be, so a line that nothing else identifies is legacy
#: money. Note that Legacy is *also* reachable through its own Workday fund
#: codes (220, 250, 500, 120); this is the separate question of what to do with
#: a line carrying none of them, which in practice means 810-FD.
DEFAULT_FUND_SLUG = 'legacy'


def choose_default(apps, schema_editor):
    """ Mark :data:`DEFAULT_FUND_SLUG` as the fallback, unless one is already set. """
    FundSource = apps.get_model('finance', 'FundSource')
    if FundSource.objects.filter(is_default=True).exists():
        return
    FundSource.objects.filter(slug=DEFAULT_FUND_SLUG).update(is_default=True)


def clear_default(apps, schema_editor):
    """ Nothing to undo beyond the column itself, which the schema op drops. """
    apps.get_model('finance', 'FundSource').objects.update(is_default=False)


class Migration(migrations.Migration):
    """ Adds :attr:`finance.models.FundSource.is_default` and picks one. """

    dependencies = [
        ('finance', '0002_seed_reference_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='fundsource',
            name='is_default',
            field=models.BooleanField(
                default=False,
                help_text='The fund an expense is filled in with when neither the memo nor '
                          'the Fund worktag identifies one. This is a stated default, not a '
                          'reading of the export, and the queue labels it as such -- but '
                          'leaving the one required box on every row blank is what made '
                          'reconciling a typing job. Tick it on exactly one fund.',
                verbose_name='Fill this in when nothing else says'),
        ),
        migrations.RunPython(choose_default, clear_default),
    ]

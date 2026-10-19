"""
The finance pages say a Workday line is *settled*, never "filed", "allocated" or
"reconciled". Labels and help text, plus the settle permission's name, which
Django sets only when it first creates the permission.
"""

from django.db import migrations, models
import django.db.models.deletion


def rename_permission(apps, schema_editor, name):
    Permission = apps.get_model('auth', 'Permission')
    Permission.objects.filter(content_type__app_label='finance',
                              codename='settle_subledger').update(name=name)


def forwards(apps, schema_editor):
    rename_permission(apps, schema_editor, 'Settle Workday lines')


def backwards(apps, schema_editor):
    rename_permission(apps, schema_editor, 'Reconcile and settle transactions')


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('finance', '0010_encumbrance_wording'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='parsedtransaction',
            options={'ordering': ('-effective_date', '-pk'), 'permissions': (('view_subledger', 'View the financial subledger'), ('edit_subledger', 'Create and edit subledger entries'), ('settle_subledger', 'Settle Workday lines'), ('view_subledger_receipts', 'View uploaded receipts')), 'verbose_name': 'Subledger Entry', 'verbose_name_plural': 'Subledger Entries'},
        ),
        migrations.AlterField(
            model_name='billing',
            name='paid_note',
            field=models.CharField(blank=True, help_text='How it was paid, when no payment received in Workday covers it: cash, a check, or a bill from before the books start.', max_length=200, verbose_name='How it was paid'),
        ),
        migrations.AlterField(
            model_name='financesettings',
            name='ledger_start_date',
            field=models.DateField(blank=True, help_text='The first day the subledger accounts for every line. Fund balances are worked out from here: whatever each account held the night before is its opening, and every line on or after it counts. Leave blank to start at the beginning of the fiscal year of the earliest imported line. Lines from before it are history: kept for the forecast, never settled.', null=True, verbose_name='Books start on'),
        ),
        migrations.AlterField(
            model_name='fundsource',
            name='account',
            field=models.ForeignKey(blank=True, help_text="The Workday account this money sits in. The carry-forward fund held in an account is that account's own money: a line nothing else identifies is settled to it, and it absorbs the account's opening balance.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='funds', to='finance.partitioncode', verbose_name='Held in'),
        ),
        migrations.AlterField(
            model_name='fundsource',
            name='is_default',
            field=models.BooleanField(default=False, help_text='The fund an expense is filled in with when neither the memo nor the Fund worktag identifies one. This is a stated default, not a reading of the export, and the queue labels it as such -- but leaving the one required box on every row blank is what made settling a typing job. Tick it on exactly one fund.', verbose_name='Fill this in when nothing else says'),
        ),
        migrations.AlterField(
            model_name='multibilling',
            name='paid_note',
            field=models.CharField(blank=True, help_text='How it was paid, when no payment received in Workday covers it: cash, a check, or a bill from before the books start.', max_length=200, verbose_name='How it was paid'),
        ),
        migrations.AlterField(
            model_name='revenuesource',
            name='credits_fund',
            field=models.ForeignKey(blank=True, help_text="The fund this kind of income always adds to. Picking the source fills it in, and putting the money anywhere else is refused. When the fund draws on funding requests, the income has to name the request it reimburses. Leave blank for income that is simply the account's own money.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='revenue_sources', to='finance.fundsource', verbose_name='Goes into'),
        ),
        migrations.AlterField(
            model_name='spendcategory',
            name='is_event_passthrough',
            field=models.BooleanField(default=False, help_text='The category an expense gets when it names the event it was incurred for -- a sub-rental hired for one show, passed straight through. Filled in automatically so the Treasurer does not have to pick a category that says nothing the linked event does not.', verbose_name='Use for costs billed to an event'),
        ),
        migrations.AlterField(
            model_name='suggestionrule',
            name='match_mode',
            field=models.CharField(choices=[('exact', 'Is exactly — the whole value, e.g. "Rent - Equipment"'), ('starts', 'Starts with — e.g. the account number 71100'), ('contains', 'Contains — a guess about wording'), ('word', 'Contains the whole word — a guess about wording')], default='exact', help_text="Exact and starts-with count as lookups: what they find is filled into the queue's form, because the export itself said it. Contains counts as a guess and is only ever offered as a chip to click.", max_length=12, verbose_name='Match how'),
        ),
        migrations.AlterField(
            model_name='partitioncode',
            name='crossing_requires_reason',
            field=models.BooleanField(default=False, help_text='Off: moving money off this side is allowed and merely shows a warning, which is right for the main account -- a Projection purchase paid out of it and reimbursed by SGA is normal. On: it is still allowed, but the entry cannot be saved without saying why. Turn this on for the account SGA funds for Projection directly.', verbose_name='Counting it on the other side needs an explanation'),
        ),
        migrations.RunPython(forwards, backwards),
    ]

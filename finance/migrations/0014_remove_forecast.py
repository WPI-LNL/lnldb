"""
The Forecast tab is gone, and with it everything only it read.

Planned purchases and corrections to how a line from before the books start
was read are deleted with their rows; so are the minimum reserve, the share of
pre-FY27 billing still charged, and a spend category's "forecast from plans
only". Lines from before the books start stay, outside every balance as
before.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0013_encumbrance_lines'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='plannedpurchase',
            name='created_by',
        ),
        migrations.RemoveField(
            model_name='plannedpurchase',
            name='fund_source',
        ),
        migrations.RemoveField(
            model_name='plannedpurchase',
            name='spend_category',
        ),
        migrations.RemoveField(
            model_name='financesettings',
            name='minimum_reserve',
        ),
        migrations.RemoveField(
            model_name='financesettings',
            name='still_billed_share',
        ),
        migrations.RemoveField(
            model_name='spendcategory',
            name='forecast_from_plans',
        ),
        migrations.AlterField(
            model_name='financesettings',
            name='ledger_start_date',
            field=models.DateField(blank=True, help_text="The first day the subledger accounts for every line. Fund balances are worked out from here: whatever each account held the night before is its opening, and every line on or after it counts. Leave blank to start at the beginning of the fiscal year of the earliest imported line. Lines from before it are history: Workday's record, outside every balance, never settled.", null=True, verbose_name='Books start on'),
        ),
        migrations.DeleteModel(
            name='HistoryOverride',
        ),
        migrations.DeleteModel(
            name='PlannedPurchase',
        ),
    ]

"""
The finance pages call money set aside for a purchase an encumbrance, never
"reserved". Labels and help text only: nothing in the database changes.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0009_still_billed_share'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plannedpurchase',
            name='status',
            field=models.CharField(choices=[('planned', 'Planned'), ('approved', 'Approved'), ('bought', 'Bought or encumbered'), ('dropped', 'Dropped')], default='planned', max_length=12),
        ),
        migrations.AlterField(
            model_name='spendcategory',
            name='forecast_from_plans',
            field=models.BooleanField(default=False, help_text='For spending chosen one purchase at a time, like equipment. The forecast leaves it out of a typical year and counts only what is encumbered or on the planned purchases list, so one big purchase is not expected again every year.', verbose_name='Forecast from plans only'),
        ),
    ]

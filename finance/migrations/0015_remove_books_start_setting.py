"""
The books start is no longer a setting.

Every line imported is in the books and is settled by hand, so nothing is
kept aside as history. The books always start on the first day of the fiscal
year of the earliest line on file, which moves back by itself when an older
export is imported.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0014_remove_forecast'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='financesettings',
            name='ledger_start_date',
        ),
    ]

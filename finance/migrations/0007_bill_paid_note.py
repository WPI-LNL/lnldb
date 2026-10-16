"""
A bill for one event can say how it was paid, as a multi-bill already can.

Marking a bill paid without a payment from Workday that covers it -- cash, a
check, a bill from before the books start -- now asks why, and the answer is
kept on the bill. Existing bills get an empty note.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0006_isd_record_and_no_bill_needed'),
    ]

    operations = [
        migrations.AddField(
            model_name='billing',
            name='paid_note',
            field=models.CharField(blank=True, help_text='How it was paid, when no payment filed from Workday covers it: cash, a check, or a bill from before the books start.', max_length=200, verbose_name='How it was paid'),
        ),
        migrations.AlterField(
            model_name='multibilling',
            name='paid_note',
            field=models.CharField(blank=True, help_text='How it was paid, when no payment filed from Workday covers it: cash, a check, or a bill from before the books start.', max_length=200, verbose_name='How it was paid'),
        ),
    ]

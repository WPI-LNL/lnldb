"""
How long a bill may wait before the weekly billing digest lists it.

Two settings on the Finance Configuration row: days waiting on the client
(14 to start) and days waiting on approval (21). The row keeps its other
values; nothing else changes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0007_bill_paid_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='financesettings',
            name='digest_client_days',
            field=models.PositiveSmallIntegerField(default=14, help_text='The weekly billing digest lists a bill the client has not answered this many days after it was last emailed, so you can email it again.', verbose_name='Billing digest: waiting on client after (days)'),
        ),
        migrations.AddField(
            model_name='financesettings',
            name='digest_approval_days',
            field=models.PositiveSmallIntegerField(default=21, help_text='The weekly billing digest lists an ISD still waiting for the client to approve it this many days after it was recorded.', verbose_name='Billing digest: waiting on approval after (days)'),
        ),
    ]

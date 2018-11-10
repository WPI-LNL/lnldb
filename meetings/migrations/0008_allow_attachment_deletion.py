# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('meetings', '0007_Duration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mtgattachment',
            name='meeting',
            field=models.ForeignKey(related_name='attachments', to='meetings.Meeting', null=True, on_delete=models.CASCADE),
        ),
    ]

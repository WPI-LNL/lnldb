# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime

from django.db import migrations, models

import meetings.models


class Migration(migrations.Migration):
    dependencies = [
        ('meetings', '0006_private_perms'),
    ]

    operations = [
        migrations.AddField(
            model_name='meeting',
            name='duration',
            field=models.DurationField(default=datetime.timedelta(0, 3600)),
        ),
        migrations.AlterField(
            model_name='meeting',
            name='datetime',
            field=models.DateTimeField(verbose_name=b'Start Time'),
        ),
        migrations.AlterField(
            model_name='meeting',
            name='minutes_private',
            field=models.TextField(null=True, verbose_name=b'Closed Minutes', blank=True),
        ),
        migrations.AlterField(
            model_name='mtgattachment',
            name='file',
            field=models.FileField(upload_to=meetings.models.mtg_attachment_file_name),
        ),
    ]

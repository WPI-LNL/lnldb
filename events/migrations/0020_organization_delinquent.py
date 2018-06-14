# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0019_multibilling_org'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='delinquent',
            field=models.BooleanField(default=False),
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('events', '0008_Fund migration'),
    ]

    operations = [
        migrations.AddField(
            model_name='location',
            name='holds_equipment',
            field=models.BooleanField(default=False),
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0009_auto_20160421_1326'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='class_year',
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
    ]

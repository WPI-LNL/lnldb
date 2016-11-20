# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('meetings', '0002_add_perms'),
    ]

    operations = [
        migrations.AddField(
            model_name='meeting',
            name='agenda',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='meeting',
            name='minutes',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='meeting',
            name='minutes_private',
            field=models.TextField(null=True, blank=True),
        ),
    ]

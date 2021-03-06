# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-12-19 17:45
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0023_workday'),
    ]

    operations = [
		migrations.RenameField(
            model_name='baseevent',
            old_name='billed_by_semester',
            new_name='billed_in_bulk',
        ),
        migrations.AlterField(
            model_name='baseevent',
            name='billed_in_bulk',
            field=models.BooleanField(db_index=True, default=False, help_text=b'Check if billing of this event will be deferred so that it can be combined with other events in a single invoice'),
        ),
    ]

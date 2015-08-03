# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('events', '0009_filter_equipment_locations'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='billed_by_semester',
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='ccs_needed',
            field=models.PositiveIntegerField(default=0, db_index=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='datetime_setup_start',
            field=models.DateTimeField(db_index=True, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='datetime_start',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='event_name',
            field=models.CharField(max_length=128, db_index=True),
        ),
        migrations.AlterField(
            model_name='event',
            name='submitted_on',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
    ]

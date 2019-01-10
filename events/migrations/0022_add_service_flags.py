# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0021_Event2019'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='enabled_event2012',
            field=models.BooleanField(default=True, verbose_name='Enabled for 2012 Events'),
        ),
        migrations.AddField(
            model_name='service',
            name='enabled_event2019',
            field=models.BooleanField(default=False, verbose_name='Enabled for 2019 Events'),
        ),
	migrations.AlterField(
            model_name='service',
            name='enabled_event2012',
            field=models.BooleanField(default=False, verbose_name='Enabled for 2012 Events'),
        ),
        migrations.AlterField(
            model_name='service',
            name='enabled_event2019',
            field=models.BooleanField(default=True, verbose_name='Enabled for 2019 Events'),
        ),
    ]

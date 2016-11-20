# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='MeetingNoticeMail',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('ts', models.DateTimeField(auto_now_add=True)),
                ('place', models.CharField(default=b'AK219', max_length=32)),
                ('time', models.TimeField(default=b'17:00')),
                ('date', models.DateField()),
                ('note', models.TextField()),
                ('start_param', models.DateField()),
                ('end_param', models.DateField()),
                ('sent', models.BooleanField(default=False)),
            ],
        ),
    ]

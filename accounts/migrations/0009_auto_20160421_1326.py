# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_auto_20160103_2303'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='locked',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='nickname',
            field=models.CharField(max_length=32, null=True, verbose_name=b'Nickname', blank=True),
        ),
        migrations.AddField(
            model_name='user',
            name='student_id',
            field=models.PositiveIntegerField(null=True, verbose_name=b'Student ID', blank=True),
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0008_auto_20161016_2133'),
    ]

    operations = [
        migrations.AlterField(
            model_name='equipmentclass',
            name='model_number',
            field=models.CharField(max_length=190, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='name',
            field=models.CharField(max_length=190),
        ),
        migrations.AlterField(
            model_name='equipmentitem',
            name='serial_number',
            field=models.CharField(max_length=190, null=True, blank=True),
        ),
    ]

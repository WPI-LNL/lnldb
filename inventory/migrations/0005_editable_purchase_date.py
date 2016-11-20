# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0004_reverse_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='equipmentitem',
            name='purchase_date',
            field=models.DateField(blank=True),
        ),
    ]

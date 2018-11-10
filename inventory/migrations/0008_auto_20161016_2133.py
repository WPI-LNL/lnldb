# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0007_containers'),
    ]

    operations = [
        migrations.AlterField(
            model_name='equipmentitem',
            name='home',
            field=models.ForeignKey(blank=True, to='events.Location', help_text='Place where this item typically resides.', null=True, on_delete=models.CASCADE),
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import mptt.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0002_change_everything'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipmentclass',
            name='url',
            field=models.URLField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='category',
            field=mptt.fields.TreeForeignKey(to='inventory.EquipmentCategory'),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='height',
            field=models.DecimalField(help_text=b'Height in inches', null=True, max_digits=6, decimal_places=2,
                                      blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='length',
            field=models.DecimalField(help_text=b'Length in inches', null=True, max_digits=6, decimal_places=2,
                                      blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='manufacturer',
            field=models.CharField(max_length=128, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='model_number',
            field=models.CharField(max_length=256, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='value',
            field=models.DecimalField(help_text=b'Estimated purchase value', null=True, max_digits=9, decimal_places=2,
                                      blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='weight',
            field=models.DecimalField(help_text=b'Weight in lbs.', null=True, max_digits=6, decimal_places=2,
                                      blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentclass',
            name='width',
            field=models.DecimalField(help_text=b'Width in inches', null=True, max_digits=6, decimal_places=2,
                                      blank=True),
        ),
    ]

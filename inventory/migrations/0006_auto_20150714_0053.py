# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import mptt.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0005_editable_purchase_date'),
    ]

    operations = [
        migrations.AlterField(
            model_name='equipmentcategory',
            name='parent',
            field=mptt.fields.TreeForeignKey(related_name='children', blank=True, to='inventory.EquipmentCategory',
                                             help_text=b"If this is a subcategory, the parent is what this is a subcategory of. Choose '---' if not.",
                                             null=True),
        ),
        migrations.AlterField(
            model_name='equipmentitem',
            name='barcode',
            field=models.BigIntegerField(unique=True, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentitem',
            name='features',
            field=models.CharField(max_length=128, null=True, verbose_name='Identifying Features', blank=True),
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import mptt.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0006_auto_20150714_0053'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipmentclass',
            name='holds_items',
            field=models.BooleanField(default=False, help_text='Can hold other items'),
        ),
        migrations.AddField(
            model_name='equipmentitem',
            name='level',
            field=models.PositiveIntegerField(default=0, editable=False, db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='equipmentitem',
            name='lft',
            field=models.PositiveIntegerField(default=0, editable=False, db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='equipmentitem',
            name='rght',
            field=models.PositiveIntegerField(default=0, editable=False, db_index=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='equipmentitem',
            name='tree_id',
            field=models.PositiveIntegerField(default=0, editable=False, db_index=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='equipmentitem',
            name='case',
            field=mptt.fields.TreeForeignKey(related_name='contents', blank=True, to='inventory.EquipmentItem', help_text='Case or item that contains this item', null=True),
        ),
    ]

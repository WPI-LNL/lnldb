# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0003_links'),
    ]

    operations = [
        migrations.AlterField(
            model_name='equipmentclass',
            name='wiki_text',
            field=models.TextField(help_text=b'How to use this item', null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentitem',
            name='item_type',
            field=models.ForeignKey(related_name='items', to='inventory.EquipmentClass'),
        ),
    ]

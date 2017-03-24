# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import mptt.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('events', '0008_Fund migration'),
        ('inventory', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='EquipmentCategory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64)),
                ('lft', models.PositiveIntegerField(editable=False, db_index=True)),
                ('rght', models.PositiveIntegerField(editable=False, db_index=True)),
                ('tree_id', models.PositiveIntegerField(editable=False, db_index=True)),
                ('level', models.PositiveIntegerField(editable=False, db_index=True)),
                ('parent',
                 mptt.fields.TreeForeignKey(related_name='children', blank=True, to='inventory.EquipmentCategory',
                                            null=True)),
                ('usual_place', models.ForeignKey(blank=True, to='events.Location',
                                                  help_text='Default place for items of this category. Inherits from parent categories.',
                                                  null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='EquipmentClass',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=256)),
                ('description',
                 models.TextField(help_text='Function, appearance, and included acessories', null=True, blank=True)),
                ('value', models.DecimalField(help_text='Estimated purchase value', max_digits=9, decimal_places=2)),
                ('model_number', models.CharField(max_length=256)),
                ('manufacturer', models.CharField(max_length=128)),
                ('length', models.DecimalField(help_text='Length in inches', max_digits=6, decimal_places=2)),
                ('width', models.DecimalField(help_text='Width in inches', max_digits=6, decimal_places=2)),
                ('height', models.DecimalField(help_text='Height in inches', max_digits=6, decimal_places=2)),
                ('weight', models.DecimalField(help_text='Weight in lbs.', max_digits=6, decimal_places=2)),
                ('wiki_text', models.TextField(help_text='How to use this item')),
                ('category', models.ForeignKey(to='inventory.EquipmentCategory')),
            ],
            options={
                'permissions': (('edit_equipment_wiki', 'Edit the wiki of an equipment'),
                                ('view_equipment_value', 'View estimated value of an equipment'),
                                ('view_equipment', 'View equipment')),
            },
        ),
        migrations.CreateModel(
            name='EquipmentItem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('serial_number', models.CharField(max_length=256, null=True, blank=True)),
                ('barcode', models.BigIntegerField(null=True, blank=True)),
                ('purchase_date', models.DateField(auto_now_add=True)),
                ('features', models.CharField(max_length=128, null=True, blank=True)),
                ('case',
                 models.ForeignKey(related_name='contents', blank=True, to='inventory.EquipmentItem', null=True)),
                ('home', models.ForeignKey(blank=True, to='events.Location', null=True)),
                ('item_type', models.ForeignKey(to='inventory.EquipmentClass')),
            ],
        ),
        migrations.RenameModel(
            old_name='Status',
            new_name='EquipmentStatus',
        ),
        migrations.RemoveField(
            model_name='equipment',
            name='subcategory',
        ),
        migrations.RemoveField(
            model_name='subcategory',
            name='category',
        ),
        migrations.AlterModelOptions(
            name='equipmentmaintentry',
            options={'ordering': ['-date'], 'get_latest_by': 'date'},
        ),
        migrations.RenameField(
            model_name='equipmentmaintentry',
            old_name='desc',
            new_name='title',
        ),
        migrations.RenameField(
            model_name='equipmentstatus',
            old_name='iconclass',
            new_name='glyphicon',
        ),
        migrations.RemoveField(
            model_name='equipmentmaintentry',
            name='ts',
        ),
        migrations.AlterField(
            model_name='equipmentmaintentry',
            name='date',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name='equipmentmaintentry',
            name='entry',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='equipmentmaintentry',
            name='equipment',
            field=models.ForeignKey(related_name='maintenance', to='inventory.EquipmentItem'),
        ),
        migrations.DeleteModel(
            name='Category',
        ),
        migrations.DeleteModel(
            name='Equipment',
        ),
        migrations.DeleteModel(
            name='SubCategory',
        ),
    ]

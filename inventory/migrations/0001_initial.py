# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name='Equipment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=256)),
                ('major', models.BooleanField(default=False)),
                ('description', models.TextField()),
                ('purchase_date', models.DateField()),
                ('purchase_cost', models.DecimalField(max_digits=9, decimal_places=2)),
                ('model_number', models.CharField(max_length=256)),
                ('serial_number', models.CharField(max_length=256)),
                ('road_case', models.CharField(max_length=16)),
                ('manufacturer', models.CharField(max_length=128)),
                ('home', models.CharField(blank=True, max_length=2, null=True,
                                          choices=[(b'CC', b'Campus Center'), (b'AH', b'Alden Memorial'),
                                                   (b'FH', b'Founders Hall'), (b'RH', b'Riley Hall'),
                                                   (b'HA', b'Harrington')])),
            ],
        ),
        migrations.CreateModel(
            name='EquipmentMaintEntry',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('ts', models.DateTimeField(auto_now_add=True)),
                ('date', models.DateField(auto_now_add=True)),
                ('desc', models.CharField(max_length=32)),
                ('entry', models.TextField()),
                ('equipment', models.ForeignKey(to='inventory.Equipment')),
            ],
            options={
                'ordering': ['-ts'],
                'get_latest_by': 'ts',
            },
        ),
        migrations.CreateModel(
            name='Status',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=32)),
                ('iconclass', models.CharField(max_length=32)),
            ],
        ),
        migrations.CreateModel(
            name='SubCategory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64)),
                ('category', models.ForeignKey(to='inventory.Category')),
            ],
        ),
        migrations.AddField(
            model_name='equipmentmaintentry',
            name='status',
            field=models.ForeignKey(to='inventory.Status'),
        ),
        migrations.AddField(
            model_name='equipmentmaintentry',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='equipment',
            name='subcategory',
            field=models.ForeignKey(to='inventory.SubCategory'),
        ),
    ]

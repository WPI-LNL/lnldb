# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


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
                                          choices=[('CC', 'Campus Center'), ('AH', 'Alden Memorial'),
                                                   ('FH', 'Founders Hall'), ('RH', 'Riley Hall'),
                                                   ('HA', 'Harrington')])),
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
                ('equipment', models.ForeignKey(to='inventory.Equipment', on_delete=models.CASCADE)),
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
                ('category', models.ForeignKey(to='inventory.Category', on_delete=models.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='equipmentmaintentry',
            name='status',
            field=models.ForeignKey(to='inventory.Status', on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='equipmentmaintentry',
            name='user',
            field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
        ),
        migrations.AddField(
            model_name='equipment',
            name='subcategory',
            field=models.ForeignKey(to='inventory.SubCategory', on_delete=models.CASCADE),
        ),
    ]

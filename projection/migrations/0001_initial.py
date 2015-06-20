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
            name='PitInstance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created_on', models.DateTimeField()),
                ('valid', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='PITLevel',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name_short', models.CharField(max_length=3)),
                ('name_long', models.CharField(max_length=16)),
                ('ordering', models.IntegerField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name='Projectionist',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('license_number', models.CharField(max_length=10, null=True, blank=True)),
                ('license_expiry', models.DateField(null=True, blank=True)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='pitinstance',
            name='pit_level',
            field=models.ForeignKey(related_name='pitinstances', to='projection.PITLevel'),
        ),
        migrations.AddField(
            model_name='pitinstance',
            name='projectionist',
            field=models.ForeignKey(related_name='pitinstances', to='projection.Projectionist'),
        ),
    ]

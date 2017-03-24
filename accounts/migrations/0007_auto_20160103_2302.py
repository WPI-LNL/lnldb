# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_auto_20160103_2241'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='user',
            options={'permissions': (('change_group', 'Change the group membership of a user'), ('edit_mdc', 'Change the MDC of a user'), ('view_user', 'View users'), ('view_member', 'View LNL members'))},
        ),
        migrations.AddField(
            model_name='user',
            name='addr',
            field=models.TextField(null=True, verbose_name='Address / Office Location', blank=True),
        ),
        migrations.AddField(
            model_name='user',
            name='mdc',
            field=models.CharField(max_length=32, null=True, verbose_name='MDC', blank=True),
        ),
        migrations.AddField(
            model_name='user',
            name='phone',
            field=models.CharField(max_length=24, null=True, verbose_name='Phone Number', blank=True),
        ),
        migrations.AddField(
            model_name='user',
            name='wpibox',
            field=models.IntegerField(null=True, verbose_name='WPI Box Number', blank=True),
        ),
    ]

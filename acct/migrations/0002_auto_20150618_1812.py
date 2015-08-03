# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('acct', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='profile',
            options={'permissions': (
            ('change_group', 'Change the group membership of a user'), ('edit_mdc', 'Change the MDC of a user'),
            ('edit_user', 'Edit the name and contact info of a user'))},
        ),
    ]

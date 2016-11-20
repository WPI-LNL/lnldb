# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('acct', '0002_auto_20150618_1812'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='profile',
            options={'permissions': (
            ('change_group', 'Change the group membership of a user'), ('edit_mdc', 'Change the MDC of a user'),
            ('edit_user', 'Edit the name and contact info of a user'), ('view_user', 'View users'),
            ('view_member', 'View LNL members'))},
        ),
    ]

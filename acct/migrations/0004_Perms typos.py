# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('acct', '0003_user_view_perms'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='profile',
            options={'permissions': (
            ('change_group', 'Change the group membership of a user'), ('add_user', 'Add a new user'),
            ('edit_mdc', 'Change the MDC of a user'), ('edit_user', 'Edit the name and contact info of a user'),
            ('view_user', 'View users'), ('view_member', 'View LNL members'))},
        ),
    ]

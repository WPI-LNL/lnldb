# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_user_class_year'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='user',
            options={'ordering': ('last_name', 'first_name', 'class_year'), 'permissions': (('change_group', 'Change the group membership of a user'), ('edit_mdc', 'Change the MDC of a user'), ('view_user', 'View users'), ('view_member', 'View LNL members'))},
        ),
    ]

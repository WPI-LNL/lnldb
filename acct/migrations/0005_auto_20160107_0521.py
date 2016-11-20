# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('acct', '0004_Perms typos'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='orgsync_org',
            name='category',
        ),
        migrations.RemoveField(
            model_name='orgsync_user',
            name='memberships',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='user',
        ),
        migrations.DeleteModel(
            name='Orgsync_Org',
        ),
        migrations.DeleteModel(
            name='Orgsync_OrgCat',
        ),
        migrations.DeleteModel(
            name='Orgsync_User',
        ),
        migrations.DeleteModel(
            name='Profile',
        ),
    ]

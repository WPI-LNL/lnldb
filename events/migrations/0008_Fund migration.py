# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('events', '0007_Perms typos'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='fund',
            options={'permissions': (('view_fund', 'View a fund'),)},
        ),
    ]

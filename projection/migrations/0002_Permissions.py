# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('projection', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='projectionist',
            options={'permissions': (
            ('view_pits', "View a projectionist's PITs"), ('edit_pits', "Edit a projectionist's PITs"),
            ('add_bulk_events', "Create a semester's worth of movies"))},
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('meetings', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='meeting',
            options={'ordering': ('-datetime',), 'permissions': (
            ('view_mtg', 'See all meeting info'), ('edit_mtg', 'Edit all meeting info'),
            ('view_mtg_attendance', 'See meeting attendance'), ('list_mtgs', 'List all meetings'),
            ('create_mtg', 'Create a meeting'), ('send_mtg_notice', 'Send meeting notices manually'))},
        ),
    ]

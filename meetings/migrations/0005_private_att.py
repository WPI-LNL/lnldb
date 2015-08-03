# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('meetings', '0004_attachments'),
    ]

    operations = [
        migrations.AddField(
            model_name='mtgattachment',
            name='private',
            field=models.BooleanField(default=False),
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0018_orgxfer_initiator'),
    ]

    operations = [
        migrations.AddField(
            model_name='multibilling',
            name='org',
            field=models.ForeignKey(to='events.Organization', related_name='multibillings', null=True),
        ),
    ]

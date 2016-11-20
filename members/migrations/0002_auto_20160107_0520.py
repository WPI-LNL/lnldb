# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='statuschange',
            name='groups',
        ),
        migrations.RemoveField(
            model_name='statuschange',
            name='member',
        ),
        migrations.DeleteModel(
            name='StatusChange',
        ),
    ]

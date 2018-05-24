# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0016_multibillings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='test_event',
            field=models.BooleanField(help_text="Check to lower the VP's blood pressure after they see the short-notice S4/L4", default=False),
        ),
        migrations.AlterField(
            model_name='organization',
            name='exec_email',
            field=models.EmailField(verbose_name='Email', null=True, max_length=254),
        ),
    ]

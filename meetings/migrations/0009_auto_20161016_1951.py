# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django_extensions.db.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('meetings', '0008_allow_attachment_deletion'),
    ]

    operations = [
        migrations.AlterField(
            model_name='ccnoticesend',
            name='uuid',
            field=models.UUIDField(null=True, editable=False, blank=True),
        ),
        migrations.AlterField(
            model_name='meetingannounce',
            name='uuid',
            field=models.UUIDField(null=True, editable=False, blank=True),
        ),
        migrations.AlterField(
            model_name='mtgattachment',
            name='created',
            field=django_extensions.db.fields.CreationDateTimeField(auto_now_add=True, verbose_name='created'),
        ),
        migrations.AlterField(
            model_name='mtgattachment',
            name='modified',
            field=django_extensions.db.fields.ModificationDateTimeField(auto_now=True, verbose_name='modified'),
        ),
    ]

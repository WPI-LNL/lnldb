# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.utils.timezone
import django_extensions.db.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('meetings', '0003_add_minutes'),
    ]

    operations = [
        migrations.CreateModel(
            name='MtgAttachment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', django_extensions.db.fields.CreationDateTimeField(default=django.utils.timezone.now,
                                                                              verbose_name='created', editable=False,
                                                                              blank=True)),
                ('modified', django_extensions.db.fields.ModificationDateTimeField(default=django.utils.timezone.now,
                                                                                   verbose_name='modified',
                                                                                   editable=False, blank=True)),
                ('name', models.CharField(max_length=64)),
                ('file', models.FileField(upload_to='')),
                ('author', models.ForeignKey(editable=False, to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('meeting', models.ForeignKey(related_name='attachments', to='meetings.Meeting', on_delete=models.CASCADE)),
            ],
            options={
                'ordering': ('-modified', '-created'),
                'abstract': False,
                'get_latest_by': 'modified',
            },
        ),
    ]

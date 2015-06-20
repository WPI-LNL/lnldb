# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.utils.timezone
from django.conf import settings
import django_extensions.db.fields


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
                ('file', models.FileField(upload_to=b'')),
                ('author', models.ForeignKey(editable=False, to=settings.AUTH_USER_MODEL)),
                ('meeting', models.ForeignKey(related_name='attachments', to='meetings.Meeting')),
            ],
            options={
                'ordering': ('-modified', '-created'),
                'abstract': False,
                'get_latest_by': 'modified',
            },
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sites', '0001_initial'),
        ('data', '0002_Global perms'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResizedRedirect',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('old_path', models.CharField(help_text="This should be an absolute path, excluding the domain name. Example: '/events/search/'.", max_length=190, verbose_name='redirect from', db_index=True)),
                ('new_path', models.CharField(help_text="This can be either an absolute path (as above) or a full URL starting with 'http://'.", max_length=200, verbose_name='redirect to', blank=True)),
                ('site', models.ForeignKey(verbose_name='site', to='sites.Site')),
            ],
            options={
                'ordering': ('old_path',),
                'db_table': 'django_redirect2',
                'verbose_name': 'redirect',
                'verbose_name_plural': 'redirects',
            },
        ),
        migrations.AlterUniqueTogether(
            name='resizedredirect',
            unique_together=set([('site', 'old_path')]),
        ),
    ]

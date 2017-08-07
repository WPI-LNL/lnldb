# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models

import meetings.models


class Migration(migrations.Migration):
    dependencies = [
        ('events', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AnnounceSend',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('sent_success', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='CCNoticeSend',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('sent_success', models.BooleanField(default=False)),
                ('uuid', models.CharField(max_length=32, unique=True, null=True, editable=False, blank=True)),
                ('addtl_message', models.TextField(null=True, verbose_name='Additional Message', blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Meeting',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('datetime', models.DateTimeField()),
                ('attendance', models.ManyToManyField(to=settings.AUTH_USER_MODEL, blank=True)),
                ('location', models.ForeignKey(blank=True, to='events.Location', null=True)),
            ],
            options={
                'ordering': ('-datetime',),
            },
        ),
        migrations.CreateModel(
            name='MeetingAnnounce',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('subject', models.CharField(max_length=128)),
                ('message', models.TextField()),
                ('added', models.DateTimeField(auto_now_add=True)),
                ('uuid', models.CharField(max_length=32, unique=True, null=True, editable=False, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='MeetingType',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=32)),
            ],
        ),
        migrations.CreateModel(
            name='TargetEmailList',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=16)),
                ('email', models.EmailField(max_length=254)),
            ],
        ),
        migrations.AddField(
            model_name='meetingannounce',
            name='email_to',
            field=models.ForeignKey(to='meetings.TargetEmailList'),
        ),
        migrations.AddField(
            model_name='meetingannounce',
            name='events',
            field=models.ManyToManyField(related_name='meetingannouncements', to='events.Event'),
        ),
        migrations.AddField(
            model_name='meetingannounce',
            name='meeting',
            field=models.ForeignKey(to='meetings.Meeting'),
        ),
        migrations.AddField(
            model_name='meeting',
            name='meeting_type',
            field=models.ForeignKey(default=1, to='meetings.MeetingType'),
        ),
        migrations.AddField(
            model_name='ccnoticesend',
            name='email_to',
            field=models.ForeignKey(default=meetings.models.get_default_email, to='meetings.TargetEmailList'),
        ),
        migrations.AddField(
            model_name='ccnoticesend',
            name='events',
            field=models.ManyToManyField(related_name='meetingccnoticeevents', to='events.Event'),
        ),
        migrations.AddField(
            model_name='ccnoticesend',
            name='meeting',
            field=models.ForeignKey(related_name='meetingccnotices', to='meetings.Meeting'),
        ),
        migrations.AddField(
            model_name='announcesend',
            name='announce',
            field=models.ForeignKey(to='meetings.MeetingAnnounce'),
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Orgsync_Org',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('orgsync_id', models.IntegerField()),
                ('name', models.CharField(max_length=128)),
                ('keywords', models.TextField(null=True, blank=True)),
                ('president_email', models.EmailField(max_length=254, null=True, blank=True)),
                ('org_email', models.EmailField(max_length=254, null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Orgsync_OrgCat',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64)),
                ('orgsync_id', models.IntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='Orgsync_User',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('orgsync_id', models.IntegerField()),
                ('title', models.CharField(max_length=256, null=True, blank=True)),
                ('account_id', models.IntegerField()),
                ('first_name', models.CharField(max_length=128)),
                ('last_name', models.CharField(max_length=128)),
                ('email_address', models.EmailField(max_length=254)),
                ('last_login', models.DateField(null=True, blank=True)),
                ('about_me', models.TextField(null=True, blank=True)),
                ('portfolio', models.CharField(max_length=256, null=True, blank=True)),
                ('memberships', models.ManyToManyField(to='acct.Orgsync_Org', blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('wpibox', models.IntegerField(null=True, verbose_name=b'WPI Box Number', blank=True)),
                ('phone', models.CharField(max_length=24, null=True, verbose_name=b'Phone Number', blank=True)),
                ('addr', models.TextField(null=True, verbose_name=b'Address / Office Location', blank=True)),
                ('mdc', models.CharField(max_length=32, null=True, verbose_name=b'MDC', blank=True)),
                ('locked', models.BooleanField(default=False)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name='orgsync_org',
            name='category',
            field=models.ForeignKey(blank=True, to='acct.Orgsync_OrgCat', null=True),
        ),
    ]

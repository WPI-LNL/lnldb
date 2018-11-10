# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0015_billing_emails'),
    ]

    operations = [
        migrations.CreateModel(
            name='MultiBilling',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', auto_created=True, primary_key=True)),
                ('date_billed', models.DateField()),
                ('date_paid', models.DateField(blank=True, null=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=8)),
            ],
            options={
                'ordering': ('-date_billed', 'date_paid'),
            },
        ),
        migrations.CreateModel(
            name='MultiBillingEmail',
            fields=[
                ('id', models.AutoField(serialize=False, verbose_name='ID', auto_created=True, primary_key=True)),
                ('subject', models.CharField(max_length=128)),
                ('message', models.TextField()),
                ('sent_at', models.DateTimeField(null=True)),
                ('email_to_orgs', models.ManyToManyField(to='events.Organization')),
                ('email_to_users', models.ManyToManyField(to=settings.AUTH_USER_MODEL)),
                ('multibilling', models.ForeignKey(to='events.MultiBilling', on_delete=models.CASCADE)),
            ],
        ),
        migrations.AddField(
            model_name='multibilling',
            name='events',
            field=models.ManyToManyField(to='events.Event', related_name='multibillings'),
        ),
    ]

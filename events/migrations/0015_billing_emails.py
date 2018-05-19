# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('events', '0014_auto_20180513_2039'),
    ]

    operations = [
        migrations.CreateModel(
            name='BillingEmail',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=128)),
                ('message', models.TextField()),
                ('sent_at', models.DateTimeField(null=True)),
            ],
        ),
        migrations.RemoveField(
            model_name='billing',
            name='opt_out_initial_email',
        ),
        migrations.RemoveField(
            model_name='billing',
            name='opt_out_update_email',
        ),
        migrations.AddField(
            model_name='billingemail',
            name='billing',
            field=models.ForeignKey(to='events.Billing'),
        ),
        migrations.AddField(
            model_name='billingemail',
            name='email_to_orgs',
            field=models.ManyToManyField(to='events.Organization'),
        ),
        migrations.AddField(
            model_name='billingemail',
            name='email_to_users',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL),
        ),
    ]

# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.db.models.deletion
import uuidfield.fields
from django.conf import settings
from django.db import migrations, models

import events.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Billing',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date_billed', models.DateField()),
                ('date_paid', models.DateField(null=True, blank=True)),
                ('amount', models.DecimalField(max_digits=8, decimal_places=2)),
                ('opt_out_initial_email', models.BooleanField(default=False)),
                ('opt_out_update_email', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ('-date_billed', 'date_paid'),
            },
        ),
        migrations.CreateModel(
            name='Building',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=128)),
                ('shortname', models.CharField(max_length=4)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=16)),
            ],
        ),
        migrations.CreateModel(
            name='CCReport',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('report', models.TextField()),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('updated_on', models.DateTimeField(auto_now=True)),
                ('crew_chief', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('submitted_ip', models.GenericIPAddressField()),
                ('submitted_on', models.DateTimeField(auto_now_add=True)),
                ('event_name', models.CharField(max_length=128)),
                ('datetime_setup_start', models.DateTimeField(null=True, blank=True)),
                ('datetime_setup_complete', models.DateTimeField()),
                ('datetime_start', models.DateTimeField()),
                ('datetime_end', models.DateTimeField()),
                ('lighting_reqs', models.TextField(null=True, blank=True)),
                ('sound_reqs', models.TextField(null=True, blank=True)),
                ('proj_reqs', models.TextField(null=True, blank=True)),
                ('description', models.TextField(null=True, blank=True)),
                ('otherservice_reqs', models.TextField(null=True, blank=True)),
                ('approved', models.BooleanField(default=False)),
                ('approved_on', models.DateTimeField(null=True, blank=True)),
                ('reviewed', models.BooleanField(default=False)),
                ('reviewed_on', models.DateTimeField(null=True, blank=True)),
                ('closed', models.BooleanField(default=False)),
                ('closed_on', models.DateTimeField(null=True, blank=True)),
                ('cancelled', models.BooleanField(default=False)),
                ('cancelled_on', models.DateTimeField(null=True, blank=True)),
                ('cancelled_reason', models.TextField(null=True, blank=True)),
                ('payment_amount', models.IntegerField(default=None, null=True, blank=True)),
                ('ccs_needed', models.PositiveIntegerField(default=0)),
                ('internal_notes', models.TextField(null=True, blank=True)),
                ('billed_by_semester', models.BooleanField(default=False)),
                ('sensitive', models.BooleanField(default=False)),
                ('test_event', models.BooleanField(default=False)),
                ('approved_by',
                 models.ForeignKey(related_name='eventapprovals', blank=True, to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'permissions': (('view_event', "Show an event that isn't hidden or all events"),
                                ('event_images', 'Lets you upload or modify images to an event'),
                                ('view_hidden_event', 'Show hidden events'),
                                ('cancel_event', 'Declare an event to be cancelled'),
                                ('event_attachments', 'Lets you upload or modify attachments to an event'),
                                ('edit_event_times', 'Lets you modify the dates for an event'),
                                ('add_event_report', 'Lets you write comments about the event'),
                                ('edit_event_fund', 'Change where money for an event comes from'),
                                ('view_event_billing', 'See financial info for event'),
                                ('edit_event_text', 'Lets you update any descriptions'),
                                ('adjust_event_owner', 'Lets you change the event contact and organization'),
                                ('edit_event_hours', 'Lets you modify the time sheets'),
                                ('event_view_sensitive', 'Show internal notes and other metadata marked as not public'),
                                ('accept_event', 'Accept an event'), ('decline_event', 'Decline an event'),
                                ('review_event', 'Review an event for billing'),
                                ('adjust_event_charges', 'Add charges and change event type'),
                                ('bill_event', 'Send bills and mark event paid'),
                                ('close_event', 'Lock an event after everything is done.'),
                                ('view_test_event', 'Show events for testing'),
                                ('event_view_granular', 'See debug data like ip addresses'),
                                ('reopen_event', 'Allows you to reopen a closed, declined, or cancelled event')),
            },
        ),
        migrations.CreateModel(
            name='EventArbitrary',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('key_name', models.CharField(max_length=64)),
                ('key_value', models.DecimalField(max_digits=8, decimal_places=2)),
                ('key_quantity', models.PositiveSmallIntegerField(default=1)),
                ('event', models.ForeignKey(related_name='arbitraryfees', to='events.Event')),
            ],
        ),
        migrations.CreateModel(
            name='EventAttachment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('attachment', models.FileField(upload_to=events.models.attachment_file_name)),
                ('note', models.TextField(default=b'', null=True, blank=True)),
                ('externally_uploaded', models.BooleanField(default=False)),
                ('event', models.ForeignKey(related_name='attachments', to='events.Event')),
            ],
        ),
        migrations.CreateModel(
            name='EventCCInstance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('setup_start', models.DateTimeField(null=True, blank=True)),
                ('crew_chief', models.ForeignKey(related_name='ccinstances', to=settings.AUTH_USER_MODEL)),
                ('event', models.ForeignKey(related_name='ccinstances', to='events.Event')),
            ],
            options={
                'ordering': ('-event__datetime_start',),
            },
        ),
        migrations.CreateModel(
            name='Extra',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64)),
                ('cost', models.DecimalField(max_digits=8, decimal_places=2)),
                ('desc', models.TextField()),
                ('disappear', models.BooleanField(default=False, help_text=b'Disappear this extra instead of disable')),
                ('checkbox',
                 models.BooleanField(default=False, help_text=b'Use a checkbox instead of an integer entry')),
                ('category', models.ForeignKey(to='events.Category')),
            ],
        ),
        migrations.CreateModel(
            name='ExtraInstance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('quant', models.PositiveIntegerField()),
                ('event', models.ForeignKey(to='events.Event')),
                ('extra', models.ForeignKey(to='events.Extra')),
            ],
        ),
        migrations.CreateModel(
            name='Fund',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('fund', models.IntegerField()),
                ('organization', models.IntegerField()),
                ('account', models.IntegerField(default=71973)),
                ('name', models.CharField(max_length=128)),
                ('notes', models.TextField(null=True, blank=True)),
                ('last_used', models.DateField(null=True)),
                ('last_updated', models.DateField(null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Hours',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('hours', models.DecimalField(null=True, max_digits=7, decimal_places=2, blank=True)),
                ('event', models.ForeignKey(related_name='hours', to='events.Event')),
            ],
        ),
        migrations.CreateModel(
            name='Location',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=64)),
                ('setup_only', models.BooleanField(default=False)),
                ('show_in_wo_form', models.BooleanField(default=True, verbose_name=b'Event Location')),
                ('available_for_meetings', models.BooleanField(default=False)),
                ('building', models.ForeignKey(to='events.Building')),
            ],
            options={
                'ordering': ['building', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=128)),
                ('shortname', models.CharField(max_length=8, null=True, blank=True)),
                (
                'email', models.EmailField(max_length=254, null=True, verbose_name=b'normal_email_unused', blank=True)),
                ('exec_email', models.EmailField(max_length=254, null=True, verbose_name=b'EMail', blank=True)),
                ('email_exec', models.BooleanField(default=True)),
                ('email_normal', models.BooleanField(default=False)),
                ('address', models.TextField(null=True, blank=True)),
                ('phone', models.CharField(max_length=32)),
                ('notes', models.TextField(null=True, blank=True)),
                ('personal', models.BooleanField(default=False)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('archived', models.BooleanField(default=False)),
                ('accounts', models.ManyToManyField(related_name='orgfunds', to='events.Fund')),
                ('associated_orgs',
                 models.ManyToManyField(related_name='associated_orgs_rel_+', verbose_name=b'Associated Clients',
                                        to='events.Organization', blank=True)),
                ('associated_users', models.ManyToManyField(related_name='orgusers', to=settings.AUTH_USER_MODEL)),
                ('user_in_charge', models.ForeignKey(related_name='orgowner', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
                'verbose_name': 'Client',
                'verbose_name_plural': 'Clients',
            },
        ),
        migrations.CreateModel(
            name='OrganizationTransfer',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('uuid', uuidfield.fields.UUIDField(unique=True, max_length=32, editable=False, blank=True)),
                ('created', models.DateTimeField(auto_now=True)),
                ('completed_on', models.DateTimeField(null=True, blank=True)),
                ('expiry', models.DateTimeField(null=True, blank=True)),
                ('completed', models.BooleanField(default=False)),
                ('new_user_in_charge', models.ForeignKey(related_name='xfer_new', to=settings.AUTH_USER_MODEL)),
                ('old_user_in_charge', models.ForeignKey(related_name='xfer_old', to=settings.AUTH_USER_MODEL)),
                ('org', models.ForeignKey(to='events.Organization')),
            ],
        ),
        migrations.CreateModel(
            name='OrgBillingVerificationEvent',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('date', models.DateField()),
                ('note', models.TextField(null=True, blank=True)),
                ('org', models.ForeignKey(related_name='verifications', to='events.Organization')),
                ('verified_by', models.ForeignKey(related_name='verification_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-id'],
                'get_latest_by': 'id',
            },
        ),
        migrations.CreateModel(
            name='ReportReminder',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('sent', models.DateTimeField(auto_now_add=True)),
                ('crew_chief', models.ForeignKey(related_name='ccreportreminders', to=settings.AUTH_USER_MODEL)),
                ('event', models.ForeignKey(related_name='ccreportreminders', to='events.Event')),
            ],
        ),
        migrations.CreateModel(
            name='Service',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('shortname', models.CharField(max_length=2)),
                ('longname', models.CharField(max_length=64)),
                ('base_cost', models.DecimalField(max_digits=8, decimal_places=2)),
                ('addtl_cost', models.DecimalField(max_digits=8, decimal_places=2)),
                ('help_desc', models.TextField(null=True, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='Lighting',
            fields=[
                ('service_ptr',
                 models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False,
                                      to='events.Service')),
            ],
            bases=('events.service',),
        ),
        migrations.CreateModel(
            name='Projection',
            fields=[
                ('service_ptr',
                 models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False,
                                      to='events.Service')),
            ],
            bases=('events.service',),
        ),
        migrations.CreateModel(
            name='Sound',
            fields=[
                ('service_ptr',
                 models.OneToOneField(parent_link=True, auto_created=True, primary_key=True, serialize=False,
                                      to='events.Service')),
            ],
            bases=('events.service',),
        ),
        migrations.AddField(
            model_name='service',
            name='category',
            field=models.ForeignKey(to='events.Category'),
        ),
        migrations.AddField(
            model_name='hours',
            name='service',
            field=models.ForeignKey(related_name='hours', blank=True, to='events.Service', null=True),
        ),
        migrations.AddField(
            model_name='hours',
            name='user',
            field=models.ForeignKey(related_name='hours', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='extra',
            name='services',
            field=models.ManyToManyField(to='events.Service'),
        ),
        migrations.AddField(
            model_name='eventccinstance',
            name='service',
            field=models.ForeignKey(related_name='ccinstances', to='events.Service'),
        ),
        migrations.AddField(
            model_name='eventccinstance',
            name='setup_location',
            field=models.ForeignKey(related_name='ccinstances', to='events.Location'),
        ),
        migrations.AddField(
            model_name='eventattachment',
            name='for_service',
            field=models.ManyToManyField(related_name='attachments', to='events.Service', blank=True),
        ),
        migrations.AddField(
            model_name='event',
            name='billing_fund',
            field=models.ForeignKey(related_name='event_accounts', on_delete=django.db.models.deletion.SET_NULL,
                                    to='events.Fund', null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='billing_org',
            field=models.ForeignKey(related_name='billedevents', blank=True, to='events.Organization', null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='cancelled_by',
            field=models.ForeignKey(related_name='eventcancellations', blank=True, to=settings.AUTH_USER_MODEL,
                                    null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='closed_by',
            field=models.ForeignKey(related_name='eventclosings', blank=True, to=settings.AUTH_USER_MODEL, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='contact',
            field=models.ForeignKey(verbose_name=b'Contact', blank=True, to=settings.AUTH_USER_MODEL, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='crew',
            field=models.ManyToManyField(related_name='crewx', to=settings.AUTH_USER_MODEL, blank=True),
        ),
        migrations.AddField(
            model_name='event',
            name='crew_chief',
            field=models.ManyToManyField(related_name='crewchiefx', to=settings.AUTH_USER_MODEL, blank=True),
        ),
        migrations.AddField(
            model_name='event',
            name='location',
            field=models.ForeignKey(to='events.Location'),
        ),
        migrations.AddField(
            model_name='event',
            name='org',
            field=models.ManyToManyField(to='events.Organization', verbose_name=b'Client', blank=True),
        ),
        migrations.AddField(
            model_name='event',
            name='otherservices',
            field=models.ManyToManyField(to='events.Service', blank=True),
        ),
        migrations.AddField(
            model_name='event',
            name='reviewed_by',
            field=models.ForeignKey(related_name='eventbillingreview', blank=True, to=settings.AUTH_USER_MODEL,
                                    null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='setup_location',
            field=models.ForeignKey(related_name='setuplocation', blank=True, to='events.Location', null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='submitted_by',
            field=models.ForeignKey(related_name='submitter', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='ccreport',
            name='event',
            field=models.ForeignKey(to='events.Event'),
        ),
        migrations.AddField(
            model_name='ccreport',
            name='for_service_cat',
            field=models.ManyToManyField(to='events.Category', verbose_name=b'Services', blank=True),
        ),
        migrations.AddField(
            model_name='billing',
            name='event',
            field=models.ForeignKey(related_name='billings', to='events.Event'),
        ),
        migrations.AlterUniqueTogether(
            name='hours',
            unique_together=set([('event', 'user', 'service')]),
        ),
        migrations.AddField(
            model_name='event',
            name='lighting',
            field=models.ForeignKey(related_name='lighting', blank=True, to='events.Lighting', null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='projection',
            field=models.ForeignKey(related_name='projection', blank=True, to='events.Projection', null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='sound',
            field=models.ForeignKey(related_name='sound', blank=True, to='events.Sound', null=True),
        ),
    ]

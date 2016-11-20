# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('events', '0006_IncomingEventPerms'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='event',
            options={'permissions': (
            ('view_event', "Show an event that isn't hidden"), ('add_raw_event', 'Use the editor to create an event'),
            ('event_images', 'Upload images to an event'), ('view_hidden_event', 'Show hidden events'),
            ('cancel_event', 'Declare an event to be cancelled'),
            ('event_attachments', 'Upload attachments to an event'),
            ('edit_event_times', 'Modify the dates for an event'), ('add_event_report', 'Add reports about the event'),
            ('edit_event_fund', 'Change where money for an event comes from'),
            ('view_event_billing', 'See financial info for event'),
            ('edit_event_text', 'Update any event descriptions'),
            ('adjust_event_owner', 'Change the event contact and organization'),
            ('edit_event_hours', 'Modify the time sheets'), ('edit_event_flags', 'Add flags to an event'),
            ('event_view_sensitive', 'Show internal notes and other metadata marked as not public'),
            ('approve_event', 'Accept an event'), ('decline_event', 'Decline an event'),
            ('can_chief_event', 'Can crew chief an event'), ('review_event', 'Review an event for billing'),
            ('adjust_event_charges', 'Add charges and change event type'),
            ('bill_event', 'Send bills and mark event paid'),
            ('close_event', 'Lock an event after everything is done.'), ('view_test_event', 'Show events for testing'),
            ('event_view_granular', 'See debug data like ip addresses'), ('event_view_debug', 'See debug events'),
            ('reopen_event', 'Reopen a closed, declined, or cancelled event'))},
        ),
    ]

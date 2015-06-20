# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):
    dependencies = [
        ('events', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='event',
            options={'permissions': (('view_event', "Show an event that isn't hidden or all events"),
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
                                     ('edit_event_hours', 'Lets you modify the time sheets'), ('event_view_sensitive',
                                                                                               'Show internal notes and other metadata marked as not public'),
                                     ('approve_event', 'Accept an event'), ('decline_event', 'Decline an event'),
                                     ('review_event', 'Review an event for billing'),
                                     ('adjust_event_charges', 'Add charges and change event type'),
                                     ('bill_event', 'Send bills and mark event paid'),
                                     ('close_event', 'Lock an event after everything is done.'),
                                     ('view_test_event', 'Show events for testing'),
                                     ('event_view_granular', 'See debug data like ip addresses'),
                                     ('reopen_event', 'Allows you to reopen a closed, declined, or cancelled event'))},
        ),
    ]

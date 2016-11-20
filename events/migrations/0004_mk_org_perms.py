# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('events', '0003_auto_20150503_0211'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='organization',
            options={'ordering': ['name'], 'verbose_name': 'Client', 'verbose_name_plural': 'Clients', 'permissions': (
            ('view_org', "See an Organization's basic properties"),
            ('list_org_events', "View an Org's non-hidden events"),
            ('list_org_hidden_events', "View an Org's hidden events"),
            ('edit_org', "Edit an Org's name and description"),
            ('show_org_billing', "See an Org's account and billing info"),
            ('edit_org_billing', "Modify an Org's account and billing info"),
            ('list_org_members', 'View who is in an Org'), ('edit_org_members', 'Edit who is in an Org'),
            ('create_org_event', "Create an event in an Org's name"),
            ('view_verifications', 'Show proofs of Org account ownership'),
            ('create_verifications', 'Create proofs of Org account ownership'),
            ('transfer_org_ownership', 'Give an Org a new owner'), ('add_org', 'Create an Organization'),
            ('deprecate_org', 'Mark an Organization as defunct'))},
        ),
    ]

# Generated by Django 4.2.13 on 2024-12-29 07:09

from django.db import migrations
import multiselectfield.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_auto_20240731_1407'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userpreferences',
            name='cc_add_subscriptions',
            field=multiselectfield.db.fields.MultiSelectField(blank=True, choices=[('email', 'Email'), ('slack', 'Slack Notification')], default=['email'], max_length=11, null=True),
        ),
    ]

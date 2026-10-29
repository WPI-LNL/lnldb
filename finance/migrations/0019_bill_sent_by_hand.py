"""
A bill can be marked sent without its email.

A bill handed to the client some other way stayed *Not sent* until its worktag
came back or it was paid. ``sent_on`` and ``sent_note`` record the day it went
out and how, and move it on to *Waiting on client* as the email would.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0018_revenue_links_to_multibill'),
    ]

    operations = [
        migrations.AddField(
            model_name='billing',
            name='sent_note',
            field=models.CharField(blank=True, help_text='How the bill reached the client, such as handed over at a meeting.', max_length=200, verbose_name='How it was sent'),
        ),
        migrations.AddField(
            model_name='billing',
            name='sent_on',
            field=models.DateField(blank=True, help_text='When the bill reached the client some other way than its email from lnldb.', null=True, verbose_name='Sent on'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='sent_note',
            field=models.CharField(blank=True, help_text='How the bill reached the client, such as handed over at a meeting.', max_length=200, verbose_name='How it was sent'),
        ),
        migrations.AddField(
            model_name='multibilling',
            name='sent_on',
            field=models.DateField(blank=True, help_text='When the bill reached the client some other way than its email from lnldb.', null=True, verbose_name='Sent on'),
        ),
    ]

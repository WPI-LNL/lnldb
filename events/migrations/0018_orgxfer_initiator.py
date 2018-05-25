# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


def populate_initiator(apps, schema_editor):
    """
    Populates initiator field for OrganizationTransfer instances already in the database.
    """
    OrganizationTransfer = apps.get_model('events', 'OrganizationTransfer')
    for transfer in OrganizationTransfer.objects.filter(initiator__isnull=True):
        transfer.initiator = transfer.old_user_in_charge
        transfer.save()


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0017_auto_20180523_2242'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationtransfer',
            name='initiator',
            field=models.ForeignKey(settings.AUTH_USER_MODEL, related_name="xfer_initiated", null=True),
        ),
        migrations.RunPython(populate_initiator, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='organizationtransfer',
            name='initiator',
            field=models.ForeignKey(settings.AUTH_USER_MODEL, related_name="xfer_initiated"),
        )
    ]

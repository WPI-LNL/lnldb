# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def forwards(apps, schema_editor):
    Profile = apps.get_model("acct", "Profile")
    for prof in Profile.objects.all():
        user = prof.user
        user.addr = prof.addr
        user.mdc = prof.mdc
        user.wpibox = prof.wpibox
        user.phone = prof.phone
        user.save()

def backwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Profile = apps.get_model("acct", "Profile")
    for user in User.objects.all():
        prof = Profile.objects.get_or_create(user=user)
        prof.addr = user.addr
        prof.mdc = user.mdc
        prof.wpibox = user.wpibox
        prof.phone = user.phone
        prof.save()

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_auto_20160103_2302'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

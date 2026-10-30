"""
Finance is for Officers only. Active members no longer see the finance pages.

``fixtures/groups.json`` gave the Active group ``view_subledger`` and
``view_fundingrequest``. A fresh install now loads the fixture without them;
this takes them back from a database that already loaded it. On a database where
the group or the permissions don't exist yet it does nothing, since Django
creates permissions after the migrations run.
"""

from django.db import migrations

ACTIVE_GRANTS = ('view_subledger', 'view_fundingrequest')


def officers_only(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    active = Group.objects.filter(name='Active').first()
    if active is None:
        return
    active.permissions.remove(*Permission.objects.filter(
        content_type__app_label='finance', codename__in=ACTIVE_GRANTS))


def give_active_read_access(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    active = Group.objects.filter(name='Active').first()
    if active is None:
        return
    active.permissions.add(*Permission.objects.filter(
        content_type__app_label='finance', codename__in=ACTIVE_GRANTS))


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0019_bill_sent_by_hand'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(officers_only, give_active_read_access),
    ]

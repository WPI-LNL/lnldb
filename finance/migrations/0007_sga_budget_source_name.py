"""
The SGA budget's revenue source is called "SGA Budget".

``0006_revenue_sources`` named it "SGA Budget Deposit". The Treasurer asked for
the plain name, the one SGA itself uses. Only a row still carrying 0006's name
is renamed, so a name a Treasurer chose in the admin is kept, and nothing is
renamed onto a name another source already has.
"""
from django.db import migrations

OLD_NAME = 'SGA Budget Deposit'
NEW_NAME = 'SGA Budget'


def _rename(apps, old, new):
    RevenueSource = apps.get_model('finance', 'RevenueSource')
    if RevenueSource.objects.filter(name=new).exists():
        return
    RevenueSource.objects.filter(slug='sga_baseline', name=old).update(name=new)


def rename(apps, schema_editor):
    """ Give the budget's source the name SGA uses. """
    _rename(apps, OLD_NAME, NEW_NAME)


def restore(apps, schema_editor):
    """ Put back 0006's name, if the row still has the one given here. """
    _rename(apps, NEW_NAME, OLD_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0006_revenue_sources'),
    ]

    operations = [
        migrations.RunPython(rename, restore),
    ]

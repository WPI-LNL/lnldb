"""
Give the Officer group the finance permissions on a database that already has it.

``fixtures/groups.json`` holds them, but it is only loaded when a database is
built, and ``manage.py loaddata`` replaces each group's permissions wholesale,
so it is not something to run on a live site. Without this, every Officer who
isn't a superuser would lose the finance pages on deploy: the Finance menu is
the only way to them, and it asks for ``finance.view_subledger``.

Django creates permissions after all the migrations have run, so on a first
deploy these rows may not exist yet. They are made here, under the keys
``post_migrate`` looks for, and it leaves rows it finds alone.

On a new database there is no Officer group yet and nothing to do: the fixture
makes the group, with these permissions.
"""
from django.db import migrations

#: ``(codename, model)``, the same nine ``finance/tests/test_rollups.py`` checks
#: the fixture for.
OFFICER_PERMISSIONS = (
    ('manage_fundingrequest', 'fundingrequest'),
    ('view_fundingrequest', 'fundingrequest'),
    ('edit_subledger', 'parsedtransaction'),
    ('settle_subledger', 'parsedtransaction'),
    ('view_subledger', 'parsedtransaction'),
    ('view_subledger_receipts', 'parsedtransaction'),
    ('manage_projecttag', 'projecttag'),
    ('import_workdaytransaction', 'workdaytransaction'),
    ('close_fiscalyear', 'fiscalyearclose'),
)


def grant_to_officers(apps, schema_editor):
    """ Add the permissions to the Officer group, keeping the ones it has. """
    officer = apps.get_model('auth', 'Group').objects.filter(name='Officer').first()
    if officer is None:
        return
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    for codename, model in OFFICER_PERMISSIONS:
        content_type, _ = ContentType.objects.get_or_create(app_label='finance', model=model)
        options = apps.get_model('finance', model)._meta
        name = dict(options.permissions).get(codename, 'Can view %s' % options.verbose_name_raw)
        permission, _ = Permission.objects.get_or_create(
            content_type=content_type, codename=codename, defaults={'name': name})
        officer.permissions.add(permission)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('finance', '0005_sga_budgets'),
    ]

    operations = [
        # Reversing leaves the grants alone: taking permissions off a group
        # could remove ones an administrator gave it on purpose.
        migrations.RunPython(grant_to_officers, migrations.RunPython.noop),
    ]

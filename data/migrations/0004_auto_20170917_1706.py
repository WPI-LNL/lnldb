# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def forward(apps, schema_editor):
	BuiltinRedirect = apps.get_model('redirects', 'Redirect')
	OurRedirect = apps.get_model('data', 'ResizedRedirect')

	for redirect in BuiltinRedirect.objects.all():
		OurRedirect.objects.update_or_create(
			defaults={'new_path': redirect.new_path},
			site=redirect.site,
			old_path=redirect.old_path
		)

def reverse(apps, schema_editor):
	BuiltinRedirect = apps.get_model('redirects', 'Redirect')
	OurRedirect = apps.get_model('data', 'ResizedRedirect')

	for redirect in OurRedirect.objects.all():
		BuiltinRedirect.objects.update_or_create(
			defaults={'new_path': redirect.new_path},
			site=redirect.site,
			old_path=redirect.old_path
		)

class Migration(migrations.Migration):

    dependencies = [
        ('data', '0003_auto_20170324_0225'),
        ('redirects', '0001_initial_patched'),
    ]

    operations = [
			migrations.RunPython(forward, reverse)
    ]

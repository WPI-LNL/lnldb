# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django.conf import settings
from six import python_2_unicode_compatible


@python_2_unicode_compatible
class Laptop(models.Model):
    name = models.CharField(max_length=20)
    description = models.TextField(blank=True)
    serial = models.CharField(max_length=12, null=True, blank=True)
    asset_tag = models.CharField(max_length=25, blank=True, null=True)
    api_key_hash = models.CharField(max_length=64, db_index=True, verbose_name='API key hash',
                                    help_text='SHA-256 hash of the API key that the laptop uses to communicate with '
                                              'the database')
    user_password = models.CharField(max_length=64)
    admin_password = models.CharField(max_length=64)
    last_checkin = models.DateTimeField(null=True, blank=True)
    last_ip = models.CharField(max_length=15, blank=True, null=True, verbose_name="Last Network IP Address")
    mdm_enrolled = models.BooleanField(default=False, verbose_name="Enrolled in MDM")
    retired = models.BooleanField(default=False)

    class Meta:
        permissions = (
            ('view_laptop_history', 'View password retrieval history for a laptop'),
            ('retrieve_user_password', 'Retrieve the user password for a laptop'),
            ('retrieve_admin_password', 'Retrieve the admin password for a laptop'),
            ('manage_mdm', 'Enroll and/or manage devices through the MDM'),
        )

    def __str__(self):
        return self.name


class LaptopPasswordRetrieval(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    laptop = models.ForeignKey(Laptop, on_delete=models.CASCADE, related_name='password_retrievals')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    admin = models.BooleanField()


class LaptopPasswordRotation(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    laptop = models.ForeignKey(Laptop, on_delete=models.CASCADE, related_name='password_rotations')


class ConfigurationProfile(models.Model):
    name = models.CharField(max_length=100)
    profile = models.FilePathField(path=settings.MEDIA_ROOT + "/profiles/", match=".*\.json$")
    scope = models.CharField(choices=(('System', 'System'), ('User', 'User')), max_length=6, default='System')
    created_on = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)
    pending_install = models.ManyToManyField(Laptop, related_name="pending", blank=True)
    installed = models.ManyToManyField(Laptop, related_name="installed", blank=True)

    class Meta:
        ordering = ['last_modified']
        permissions = (
            ('view_removal_password', 'Retrieve the removal password for a profile'),
        )

    def __str__(self):
        return self.name


class MacOSApp(models.Model):
    name = models.CharField(max_length=128)
    identifier = models.CharField(max_length=64, help_text="Homebrew Identifier")
    version = models.CharField(max_length=36, blank=True, null=True)
    developer = models.CharField(max_length=64, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    pending_install = models.ManyToManyField(Laptop, related_name="apps_pending", blank=True)
    pending_removal = models.ManyToManyField(Laptop, related_name="apps_remove", blank=True)
    installed = models.ManyToManyField(Laptop, related_name="apps_installed", blank=True)
    update_available = models.BooleanField(blank=True, default=False)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "managed app"
        permissions = (
            ('view_apps', 'View managed laptop applications'),
            ('add_apps', 'Add apps to library'),
            ('manage_apps', 'Manage the app library')
        )


class InstallationRecord(models.Model):
    profile = models.ForeignKey(ConfigurationProfile, on_delete=models.CASCADE, null=True, blank=True,
                                related_name="install_records")
    app = models.ForeignKey(MacOSApp, on_delete=models.CASCADE, null=True, blank=True, related_name="install_records")
    device = models.ForeignKey(Laptop, on_delete=models.CASCADE, related_name="install_records")
    version = models.CharField(max_length=36, blank=True, null=True)
    installed_on = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        if self.profile:
            return "%s (v%s) on %s" % (str(self.profile), str(self.version), str(self.device))
        else:
            return "%s (v%s) on %s" % (str(self.app), str(self.version), str(self.device))

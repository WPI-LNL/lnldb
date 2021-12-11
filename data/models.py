from django.conf import settings
from django.db import models

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.utils.translation import gettext_lazy as _


NOTIF_TYPE = (
    ('info', 'Info'),
    ('advisory', 'Advisory'),
    ('warning', 'Warning')
)

FORMATS = (
    ('alert', 'Alert'),
    ('notification', 'Notification')
)


class StupidCat(models.Model):
    """ For logging when a user goes somewhere they shouldn't be going """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, blank=True, null=True)
    user_ip = models.GenericIPAddressField(max_length=16)
    requested_uri = models.CharField(max_length=512)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = "timestamp"


class GlobalPerms(models.Model):
    # it's a dummy class
    class Meta:
        permissions = (
            ('search', 'Enables search functionality'),
        )


class ResizedRedirect(models.Model):
    """Custom redirect (configured from the admin site)"""
    name = models.CharField(max_length=64, help_text='User friendly name', blank=True, null=True)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, verbose_name=_('site'))
    old_path = models.CharField(
        _('redirect from'),
        max_length=190,
        db_index=True,
        help_text=_("This should be an absolute path, excluding the domain name. Example: '/events/search/'."),
    )
    new_path = models.CharField(
        _('redirect to'),
        max_length=200,
        blank=True,
        help_text=_("This can be either an absolute path (as above) or a full URL starting with 'http://'."),
    )
    sitemap = models.BooleanField(default=False, verbose_name='Include in Sitemap')

    class Meta:
        verbose_name = _('redirect')
        verbose_name_plural = _('redirects')
        db_table = 'django_redirect2'
        unique_together = (('site', 'old_path'),)
        ordering = ('old_path',)

    def __str__(self):
        return "%s ---> %s" % (self.old_path, self.new_path)

    def clean(self):
        if not self.name and self.sitemap:
            raise ValidationError('A name is required to include this redirect in the sitemap')


class Notification(models.Model):
    """Passive site notifications - accessible through the API"""
    title = models.CharField(max_length=128)
    message = models.TextField(max_length=500)
    format = models.CharField(max_length=12, choices=FORMATS)
    type = models.CharField(max_length=8, choices=NOTIF_TYPE)
    dismissible = models.BooleanField(default=False)
    target = models.CharField(max_length=200,
                              help_text="To target a specific page, include the full pathname (i.e. "
                                        "'/services/lighting.html' or '/events/'). To target a directory, "
                                        "include only the directory name (i.e. 'events'). For a sitewide "
                                        "notification, enter 'All'.")
    expires = models.DateTimeField()

    def __str__(self):
        return self.title + " - " + self.target

    class Meta:
        unique_together = ("format", "target")


class Extension(models.Model):
    """Application registered to use the API"""
    name = models.CharField(max_length=120)
    developer = models.CharField(max_length=64)
    description = models.TextField()
    icon = models.ImageField(null=True, blank=True)

    api_key = models.CharField(max_length=36, verbose_name="API Key")
    enabled = models.BooleanField()

    # endpoints = models.ManyToManyField(Endpoint, related_name="apps", blank=True)
    registered = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    users = models.ManyToManyField(get_user_model(), related_name="connected_services", blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Third-party application"

from django.db import models
from django.conf import settings
# Create your models here.


class StupidCat(models.Model):
    """ For logging when a user goes somewhere they shouldn't be going """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True)
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

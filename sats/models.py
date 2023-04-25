from django.conf import settings
from django.db import models

# Create your models here.

class Asset(models.Model):
    asset_id = models.IntegerField(primary_key=True)
    asset_display_name = models.CharField(max_length=10, null=False,
                                          blank=False)
    asset_desc = models.CharField(max_length=32, null=True, blank=True)
    asset_status = models.CharField(max_length=5, null=False, blank=False,
                                    default="UNK")
    asset_position = models.IntegerField(null=True, blank=True)
    asset_user = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.CASCADE, null=True, blank=True)

    asset_archived = models.BooleanField(null=False, blank=False, default=False)
    asset_last_seen = models.DateTimeField(null=False, blank=False)


class AssetEvent(models.Model):
    event_id = models.IntegerField(primary_key=True)

    event_type = models.CharField(max_length=5, null=False, blank=False)
    asset_id = models.ForeignKey("asset", on_delete=models.CASCADE)
    asset_position = models.IntegerField(blank=True, null=True)
    
    event_datetime = models.DateTimeField(blank=False, null=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE)

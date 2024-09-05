from django.contrib import admin
from . import models

# Register your models here.

admin.site.register(models.Asset)
admin.site.register(models.AssetEvent)
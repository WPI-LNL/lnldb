# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin

from . import models


class LaptopAdmin(admin.ModelAdmin):
    readonly_fields = ['serial', 'last_ip', 'last_checkin', 'mdm_enrolled']


admin.site.register(models.Laptop, LaptopAdmin)
admin.site.register(models.ConfigurationProfile)
admin.site.register(models.MacOSApp)

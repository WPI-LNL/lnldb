from django.contrib import admin
from mptt.admin import MPTTModelAdmin

from inventory import models

# It's a tree, so it's special...
admin.site.register(models.EquipmentCategory, MPTTModelAdmin)

admin.site.register(models.EquipmentStatus)
admin.site.register(models.EquipmentMaintEntry)
admin.site.register(models.EquipmentItem)
admin.site.register(models.EquipmentClass)
admin.site.register(models.AccessRecord)

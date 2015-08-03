from mptt.admin import MPTTModelAdmin
from inventory.models import *
from django.contrib import admin

# It's a tree, so it's special...
admin.site.register(EquipmentCategory, MPTTModelAdmin)

admin.site.register(EquipmentStatus)
admin.site.register(EquipmentMaintEntry)
admin.site.register(EquipmentItem)
admin.site.register(EquipmentClass)

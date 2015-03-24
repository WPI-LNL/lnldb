from inventory.models import *
from django.contrib import admin


class MaintEntryAdmin(admin.ModelAdmin):
    list_display = ('desc', 'date', 'ts', 'equipment', 'status')
    list_filter = ('status', 'equipment', 'date')


admin.site.register(Category)
admin.site.register(SubCategory)
admin.site.register(EquipmentMaintEntry, MaintEntryAdmin)
admin.site.register(Equipment)
admin.site.register(Status)

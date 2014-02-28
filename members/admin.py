from django.contrib import admin
from members.models import StatusChange

class SCAdmin(admin.ModelAdmin):
    list_display = ["member","group_list","date"]
admin.site.register(StatusChange,SCAdmin)
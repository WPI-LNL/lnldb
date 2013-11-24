from django.contrib import admin
from members.models import StatusChange

class SCAdmin(admin.ModelAdmin):
    pass
admin.site.register(StatusChange)
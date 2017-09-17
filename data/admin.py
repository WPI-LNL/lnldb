from django.contrib import admin
from .models import ResizedRedirect

class RedirectAdmin(admin.ModelAdmin):
    pass
admin.site.register(ResizedRedirect, RedirectAdmin)

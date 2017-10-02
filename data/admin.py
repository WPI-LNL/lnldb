from django.contrib import admin
from django.contrib.redirects.models import Redirect as BaseRedirect
from .models import ResizedRedirect

class RedirectAdmin(admin.ModelAdmin):
    pass
admin.site.unregister(BaseRedirect)
admin.site.register(ResizedRedirect, RedirectAdmin)

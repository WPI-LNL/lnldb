from django.contrib import admin
from django.contrib.redirects.models import Redirect as BaseRedirect
from .models import ResizedRedirect, Notification


class RedirectAdmin(admin.ModelAdmin):
    pass


admin.site.index_template = "admin/index.html"
admin.site.unregister(BaseRedirect)
admin.site.register(ResizedRedirect, RedirectAdmin)
admin.site.register(Notification)

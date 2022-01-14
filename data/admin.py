from cryptography.fernet import Fernet
from django.contrib import admin
from django.conf import settings
from django.contrib.redirects.models import Redirect as BaseRedirect
from .models import ResizedRedirect, Notification, Extension


class RedirectAdmin(admin.ModelAdmin):
    pass


class ExtensionAdmin(admin.ModelAdmin):
    list_display = ('name', 'developer', 'client_id')

    def client_id(self, obj):
        if obj.api_key and settings.CRYPTO_KEY:
            cipher_suite = Fernet(settings.CRYPTO_KEY)
            return cipher_suite.encrypt(obj.api_key.encode('utf-8')).decode('utf-8')
        return "Not available"


admin.site.index_template = "admin/index.html"
admin.site.unregister(BaseRedirect)
admin.site.register(ResizedRedirect, RedirectAdmin)
admin.site.register(Notification)
admin.site.register(Extension, ExtensionAdmin)

from django.contrib import admin
from django.shortcuts import reverse
from django.utils.html import format_html
from . import models


class SpotifyUserAdmin(admin.ModelAdmin):
    exclude = ('token_info',)
    readonly_fields = ('display_name', 'spotify_id', 'auth_buttons')

    def auth_buttons(self, instance):
        if not instance.user:
            return None
        if not instance.token_info:
            return format_html('<a href="{}" class="button">Authenticate</a>'.format(reverse("spotify:signin") +
                                                                                     "?user=" + str(instance.pk)))
        else:
            return format_html('<p>Signed in</p>')
    auth_buttons.short_description = "Spotify API"
    auth_buttons.allow_tags = True


# Register your models here.
admin.site.register(models.SpotifyUser, SpotifyUserAdmin)
admin.site.register(models.Session)

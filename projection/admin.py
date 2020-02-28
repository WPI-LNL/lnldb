from django.contrib import admin

from projection.models import PitInstance, PITLevel, Projectionist, PitRequest


class LevelAdmin(admin.ModelAdmin):
    list_display = ('name_short', 'name_long', 'ordering')


admin.site.register(Projectionist)
admin.site.register(PITLevel, LevelAdmin)
admin.site.register(PitInstance)
admin.site.register(PitRequest)

from django.contrib import admin
from projection.models import PITLevel, Projectionist, PitInstance


class LevelAdmin(admin.ModelAdmin):
    list_display = ('name_short', 'name_long', 'ordering')


admin.site.register(Projectionist)
admin.site.register(PITLevel, LevelAdmin)
admin.site.register(PitInstance)

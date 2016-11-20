from . import models
from django.contrib import admin
from reversion.admin import VersionAdmin


class MAAdmin(VersionAdmin):
    list_display = ('added', 'uuid', 'email_to')


class CCAdmin(admin.ModelAdmin):
    list_display = ('uuid',)


admin.site.register(models.Meeting)
admin.site.register(models.MeetingType)
admin.site.register(models.MeetingAnnounce, MAAdmin)
admin.site.register(models.TargetEmailList)
admin.site.register(models.AnnounceSend)
admin.site.register(models.CCNoticeSend, CCAdmin)
admin.site.register(models.MtgAttachment)

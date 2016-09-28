from meetings.models import *
from django.contrib import admin
from reversion.admin import VersionAdmin


class MAAdmin(VersionAdmin):
    list_display = ('added', 'uuid', 'email_to')


class CCAdmin(admin.ModelAdmin):
    list_display = ('uuid',)


admin.site.register(Meeting)
admin.site.register(MeetingType)
admin.site.register(MeetingAnnounce, MAAdmin)
admin.site.register(TargetEmailList)
admin.site.register(AnnounceSend)
admin.site.register(CCNoticeSend, CCAdmin)
admin.site.register(MtgAttachment)

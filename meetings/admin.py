from meetings.models import *
from django.contrib import admin


admin.site.register(Meeting)
admin.site.register(MeetingType)
admin.site.register(MeetingAnnounce)
admin.site.register(TargetEmailList)
admin.site.register(AnnounceSend)
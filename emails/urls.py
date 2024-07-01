from django.urls import re_path

from . import views

app_name = 'emails'

urlpatterns = [
    re_path(r'^announce/(?P<slug>[-0-9a-f]+)/$', views.MeetingAnnounceView.as_view(),
        name="pre-meeting"),
    re_path(r'^announcecc/(?P<slug>[-0-9a-f]+)/$', views.MeetingAnnounceCCView.as_view(),
        name="post-meeting"),
    re_path(r'^dispatch/$', views.dispatch_console, name="dispatch"),
    re_path(r'^dispatch/srv-announce/$', views.mk_srv_announce, name="service-announcement"),
    re_path(r'^dispatch/sms/$', views.send_sms, name="sms"),
    re_path(r'^dispatch/sms/active/$', views.send_active_sms, name="sms-active"),
    re_path(r'^dispatch/cc-poke/$', views.poke_cc, name="poke-cc"),
]

from django.conf.urls import url

from . import views

app_name = 'emails'

urlpatterns = [
    url(r'^announce/(?P<slug>[-0-9a-f]+)/$', views.MeetingAnnounceView.as_view(),
        name="pre-meeting"),
    url(r'^announcecc/(?P<slug>[-0-9a-f]+)/$', views.MeetingAnnounceCCView.as_view(),
        name="post-meeting"),
    url(r'^dispatch/$', views.dispatch_console, name="dispatch"),
    url(r'^dispatch/srv-announce/$', views.mk_srv_announce, name="service-announcement"),
    url(r'^dispatch/sms/$', views.send_sms, name="sms"),
    url(r'^dispatch/sms/active/$', views.send_active_sms, name="sms-active"),
    url(r'^dispatch/cc-poke/$', views.poke_cc, name="poke-cc"),
]

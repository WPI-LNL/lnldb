from django.conf.urls import url

from . import views

app_name = 'emails'

urlpatterns = [
    url(r'^announce/(?P<slug>[-0-9a-f]+)/$', views.MeetingAnnounceView.as_view(),
        name="pre-meeting"),
    url(r'^announcecc/(?P<slug>[-0-9a-f]+)/$', views.MeetingAnnounceCCView.as_view(),
        name="post-meeting"),
]

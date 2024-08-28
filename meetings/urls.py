from django.conf.urls import include
from django.urls import re_path

from . import views

app_name = 'meetings'

urlpatterns = [
    re_path(r'^new/$', views.newattendance, name="new"),
    re_path(r'^$', views.listattendance, name="list"),
    re_path(r'^page/(?P<page>\d+)/$', views.listattendance, name="list_bypage"),
    re_path(r'^(?P<mtg_id>\d+)/', include([
        re_path(r'^$', views.viewattendance, name="detail"),
        re_path(r'^addchief/(?P<event_id>\d+)/$', views.updateevent, name="addchief"),
        re_path(r'^edit/$', views.editattendance, name="edit"),
        re_path(r'^remind/mtg/$', views.mknotice, name="email"),
        re_path(r'^remind/cc/$', views.mkccnotice, name="cc-email"),
        re_path(r'^invite/$', views.download_invite, name="invite"),
        re_path(r'^download/(?P<att_id>\d+)/$', views.download_att, name="att-dl"),
        re_path(r'^file/(?P<att_id>\d+)/$', views.modify_att, name="att-edit"),
        re_path(r'^rm/(?P<att_id>\d+)/$', views.rm_att, name="att-rm"),
        re_path(r'^delete/$', views.DeleteMeeting.as_view(), name="delete")
    ]))
]

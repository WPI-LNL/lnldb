from django.conf.urls import include, url

from . import views

app_name = 'meetings'

urlpatterns = [
    url(r'^new/$', views.newattendance, name="new"),
    url(r'^$', views.listattendance, name="list"),
    url(r'^page/(?P<page>\d+)/$', views.listattendance, name="list_bypage"),
    url(r'^(?P<mtg_id>\d+)/', include([
        url(r'^$', views.viewattendance, name="detail"),
        url(r'^addchief/(?P<event_id>\d+)/$', views.updateevent, name="addchief"),
        url(r'^edit/$', views.editattendance, name="edit"),
        url(r'^remind/mtg/$', views.mknotice, name="email"),
        url(r'^remind/cc/$', views.mkccnotice, name="cc-email"),
        url(r'^download/(?P<att_id>\d+)/$', views.download_att, name="att-dl"),
        url(r'^file/(?P<att_id>\d+)/$', views.modify_att, name="att-edit"),
        url(r'^rm/(?P<att_id>\d+)/$', views.rm_att, name="att-rm"),
    ]))
]

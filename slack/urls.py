from django.urls import re_path
from . import api, views, event_handlers

# URLs for DB users should start with `db/`

# URLs for Slack app should start with nothing or `slack/`


app_name = "Slack"

urlpatterns = [
    re_path(r'^moderate/$', views.report_list, name="moderate"),
    re_path(r'^moderate/(?P<pk>\d+)/$', views.view_report, name="report"),
    re_path(r'^channels/$', views.channel_list, name="channel-list"),
    re_path(r'^channel/(?P<id>[^/]+)/edit/$', views.channel_detail_edit, name="channel-edit"),
    re_path(r'^channel/(?P<id>[^/]+)/$', views.channel_detail, name="channel"),
]

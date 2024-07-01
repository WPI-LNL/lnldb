from django.urls import re_path
from . import api, views


app_name = "Slack"

urlpatterns = [
    re_path(r'^interactive-endpoint/$', api.handle_interaction, name="interactive-endpoint"),
    re_path(r'^events/$', api.handle_event, name="event-endpoint"),
    re_path(r'^moderate/$', views.report_list, name="moderate"),
    re_path(r'^moderate/(?P<pk>\d+)/$', views.view_report, name="report")
]

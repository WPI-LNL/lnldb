from django.conf.urls import url
from . import api, views


app_name = "Slack"

urlpatterns = [
    url(r'^interactive-endpoint/$', api.handle_interaction, name="interactive-endpoint"),
    url(r'^events/$', api.handle_event, name="event-endpoint"),
    url(r'^moderate/$', views.report_list, name="moderate"),
    url(r'^moderate/(?P<pk>\d+)/$', views.view_report, name="report")
]

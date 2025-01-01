from django.urls import re_path
from . import api, views, event_handlers

# URLs for DB users should start with `db/`

# URLs for Slack app should start with nothing or `slack/`


app_name = "Slack"

urlpatterns = [
    re_path(r'^interactive-endpoint/$', event_handlers.handle_interaction, name="interactive-endpoint"),
    re_path(r'^events/$', event_handlers.handle_event, name="event-endpoint"),
    re_path(r'^db/moderate/$', views.report_list, name="moderate"),
    re_path(r'^db/moderate/(?P<pk>\d+)/$', views.view_report, name="report"),
]

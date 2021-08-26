from django.conf.urls import url
from . import api


app_name = "Slack"

urlpatterns = [
    url(r'^interactive-endpoint/$', api.handle_interaction, name="interactive-endpoint"),
    url(r'^events/$', api.handle_event, name="event-endpoint")
]

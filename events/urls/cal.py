from django.conf.urls import url

from .. import cal
from ..views import list as list_views

urlpatterns = [
    url(r'^$', list_views.public_facing, name="list"),
    url(r'^feed.ics$', cal.EventFeed(), name='feed'),
    url(r'^feed_full.ics$', cal.FullEventFeed(), name='feed-full'),
    url(r'^feed_light.ics$', cal.LightEventFeed(), name='feed-light'),
    url(r'^json(/*?.*)*$', cal.cal_json, name="api"),
]

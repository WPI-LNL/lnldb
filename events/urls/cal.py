from django.conf.urls import url

from .. import cal
from ..views import list as list_views

app_name = 'lnldb'

urlpatterns = [
    url(r'^$', list_views.public_facing, name="list"),
    url(r'^feed.ics$', cal.EventFeed(), name='feed'),
    url(r'^feed_full.ics$', cal.FullEventFeed(), name='feed-full'),
    url(r'^feed_light.ics$', cal.LightEventFeed(), name='feed-light'),
    url(r'^json/public(/*?.*)*$', cal.PublicFacingCalJsonView.as_view(), name="api-public"),
    url(r'^json/findchief(/*?.*)*$', cal.FindChiefCalJsonView.as_view(), name="api-findchief"),
    url(r'^json/prerequest(/*?.*)*$', cal.IncomingCalJsonView.as_view(), name="api-prerequest"),
    url(r'^json/incoming(/*?.*)*$', cal.IncomingCalJsonView.as_view(), name="api-incoming"),
    url(r'^json/confirmed(/*?.*)*$', cal.IncomingCalJsonView.as_view(), name="api-confirmed"),
    url(r'^json/open(/*?.*)*$', cal.OpenCalJsonView.as_view(), name="api-open"),
    url(r'^json/unreviewed(/*?.*)*$', cal.UnreviewedCalJsonView.as_view(), name="api-unreviewed"),
    url(r'^json/unbilled(/*?.*)*$', cal.UnbilledCalJsonView.as_view(), name="api-unbilled"),
    url(r'^json/bulk-unbilled(/*?.*)*$', cal.UnbilledSemesterCalJsonView.as_view(), name="api-unbilled-semester"),
    url(r'^json/paid(/*?.*)*$', cal.PaidCalJsonView.as_view(), name="api-paid"),
    url(r'^json/unpaid(/*?.*)*$', cal.UnpaidCalJsonView.as_view(), name="api-unpaid"),
    url(r'^json/closed(/*?.*)*$', cal.ClosedCalJsonView.as_view(), name="api-closed"),
    url(r'^json/all(/*?.*)*$', cal.AllCalJsonView.as_view(), name="api-all"),
]

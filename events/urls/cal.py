from django.urls import re_path

from .. import cal
from ..views import list as list_views

app_name = 'lnldb'

urlpatterns = [
    re_path(r'^$', list_views.public_facing, name="list"),
    re_path(r'^feed.ics$', cal.EventFeed(), name='feed'),
    re_path(r'^feed_full.ics$', cal.FullEventFeed(), name='feed-full'),
    re_path(r'^feed_light.ics$', cal.LightEventFeed(), name='feed-light'),
    re_path(r'^json/public(/*?.*)*$', cal.PublicFacingCalJsonView.as_view(), name="api-public"),
    re_path(r'^json/findchief(/*?.*)*$', cal.FindChiefCalJsonView.as_view(), name="api-findchief"),
    re_path(r'^json/prerequest(/*?.*)*$', cal.IncomingCalJsonView.as_view(), name="api-prerequest"),
    re_path(r'^json/prospective(/*?.*)*$', cal.IncomingCalJsonView.as_view(), name="api-prospective"),
    re_path(r'^json/incoming(/*?.*)*$', cal.IncomingCalJsonView.as_view(), name="api-incoming"),
    re_path(r'^json/confirmed(/*?.*)*$', cal.IncomingCalJsonView.as_view(), name="api-confirmed"),
    re_path(r'^json/open(/*?.*)*$', cal.OpenCalJsonView.as_view(), name="api-open"),
    re_path(r'^json/unreviewed(/*?.*)*$', cal.UnreviewedCalJsonView.as_view(), name="api-unreviewed"),
    re_path(r'^json/unbilled(/*?.*)*$', cal.UnbilledCalJsonView.as_view(), name="api-unbilled"),
    re_path(r'^json/bulk-unbilled(/*?.*)*$', cal.UnbilledSemesterCalJsonView.as_view(), name="api-unbilled-semester"),
    re_path(r'^json/paid(/*?.*)*$', cal.PaidCalJsonView.as_view(), name="api-paid"),
    re_path(r'^json/unpaid(/*?.*)*$', cal.UnpaidCalJsonView.as_view(), name="api-unpaid"),
    re_path(r'^json/closed(/*?.*)*$', cal.ClosedCalJsonView.as_view(), name="api-closed"),
    re_path(r'^json/allfuture(/*?.*)*$', cal.AllFutureCalJsonView.as_view(), name="api-all-future"),
    re_path(r'^json/all(/*?.*)*$', cal.AllCalJsonView.as_view(), name="api-all"),
    
]

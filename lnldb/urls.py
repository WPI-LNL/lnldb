import debug_toolbar
import django.contrib.auth.views
import permission
from ajax_select import urls as ajax_select_urls
from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic.base import RedirectView

import data.views
from emails.views import MeetingAnnounceCCView, MeetingAnnounceView
from events.cal import EventFeed, FullEventFeed, LightEventFeed, cal_json
from events.forms import named_event_forms
from events.views.flow import CCRCreate, CCRDelete, CCRUpdate
from events.views.indices import admin as db_home
from events.views.indices import event_search
from events.views.list import public_facing
from pages.views import page as view_page
from projection.views import (BulkUpdateView, ProjectionCreate,
                              ProjectionistDelete)

admin.autodiscover()
permission.autodiscover()


# Error pages
handler403 = 'data.views.err403'
handler404 = 'data.views.err404'
handler500 = 'data.views.err500'

urlpatterns = [
    # Examples:
    # url(r'^$', 'lnldb.views.home', name='home'),
    # url(r'^lnldb/', include('lnldb.foo.urls')),

    # Include other modules
    url(r'^admin/', include(admin.site.urls)),
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^hijack/', include('hijack.urls')),
    url(r'^__debug__/', include(debug_toolbar.urls)),
    url(r'^db/lookups/', include(ajax_select_urls)),
    url(r'^db/meetings/', include('meetings.urls', namespace='meetings')),
    url(r'^db/clients/', include('events.urls.orgs', namespace='orgs')),
    url(r'^db/inventory/', include('inventory.urls', namespace='inventory')),
    url(r'^db/events/', include('events.urls.events', namespace='events')),
    url(r'^workorder/', include('events.urls.wizard', namespace='wizard')),
    url(r'^my/', include('events.urls.my', namespace='my')),
    url(r'', include('accounts.urls', namespace='accounts')),

    # 'MY' {{{
    url(r'^my/orgs/transfer/(?P<id>[0-9]+)/$', 'events.views.orgs.org_mkxfer', name="my-orgs-xfer"),
    url(r'^my/orgs/transfer/(?P<idstr>[0-9a-f]+)/$', 'events.views.orgs.org_acceptxfer',
        name="my-orgs-acceptxfer"),
    url(r'^my/events/$', 'events.views.my.myevents', name="my-events"),
    url(r'^my/events/(?P<eventid>[0-9]+)/files/$', 'events.views.my.eventfiles',
        name="my-eventfiles"),
    url(r'^my/events/(?P<eventid>[0-9]+)/report/$', 'events.views.my.ccreport', name="my-ccreport"),
    url(r'^my/events/(?P<eventid>[0-9]+)/hours/$', 'events.views.my.hours_list', name="my-cchours"),
    url(r'^my/events/(?P<eventid>[0-9]+)/hours/bulk/$', 'events.views.my.hours_bulk',
        name="my-cchours-bulk"),
    url(r'^my/events/(?P<eventid>[0-9]+)/hours/mk/$', 'events.views.my.hours_mk',
        name="my-cchours-mk"),
    url(r'^my/events/(?P<eventid>[0-9]+)/hours/(?P<userid>[0-9]+)$', 'events.views.my.hours_edit',
        name="my-cchours-edit"),
    url(r'^my/events/(?P<eventid>[0-9]+)/repeat/$', 'events.views.my.myworepeat', name="my-repeat"),
    # }}}

    # projection {{{
    url(r'^db/projection/list/$', 'projection.views.plist_detail',
        name="projection-list-detail"),
    url(r'^db/projection/list/other/$', 'projection.views.plist', name="projection-list"),
    url(r'^db/projection/bulk/$', BulkUpdateView.as_view(), name="projection-bulk-update"),
    url(r'^db/projection/update/(?P<id>[0-9a-f]+)/$', "projection.views.projection_update",
        name="projection-update"),
    url(r'^db/projection/rm/(?P<pk>[0-9a-f]+)/$', ProjectionistDelete.as_view(),
        name="projection-delete"),
    url(r'^db/projection/mk/$', ProjectionCreate.as_view(), name="projection-create"),
    url(r'^db/projection/list/detail/pdf/$', 'pdfs.views.generate_projection_pdf',
        name="proj-pdf-multi"),

    url(r'^db/projection/bulkevents/$', 'projection.views.bulk_projection',
        name="projection-bulk2"),
    # }}}

    # event lists {{{
    url(r'^list/$', public_facing, name="list"),
    url(r'^list/feed.ics$', EventFeed(), name='public_cal_feed'),
    url(r'^list/feed_full.ics$', FullEventFeed(), name='full_cal_feed'),
    url(r'^list/feed_light.ics$', LightEventFeed(), name='light_cal_feed'),
    url(r'^list/json(/*?.*)*$', cal_json),
    # }}}

    # emails
    url(r'^email/announce/(?P<slug>[-0-9a-f]+)/$', MeetingAnnounceView.as_view(),
        name="email-view-announce"),
    url(r'^email/announcecc/(?P<slug>[-0-9a-f]+)/$', MeetingAnnounceCCView.as_view(),
        name="email-view-announce-cc"),

    # special urls
    url(r'^status/$', data.views.status),
    url(r'^db/accesslog/$', data.views.access_log, name="access-log"),
    url(r'^NOTOUCHING/$', data.views.fuckoffkitty),
    url(r'^lnldb/fuckoffkitty/$', RedirectView.as_view(url="/NOTOUCHING/", permanent=False)),
    url(r'^db/$', db_home, name="db"),
    url(r'^(?P<slug>[-\w]+)/$', view_page),
    url(r'^db/oldsearch$', event_search, name="events-search"),
    url(r'^db/search$', data.views.search, name="search"),

    # Uncomment to have javascript translation support
    # url(r'^jsi18n', 'django.views.i18n.javascript_catalog'),

    # keep old urls
    url(r'^lnadmin/$', RedirectView.as_view(url="/db/", permanent=True)),
    url(r'^lnadmin/(?P<newpath>.+)$', RedirectView.as_view(url="/db/%(newpath)s", permanent=True)),

    # debugging
]

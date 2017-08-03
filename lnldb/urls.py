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
from events.forms import named_event_forms
from events.views.flow import CCRCreate, CCRDelete, CCRUpdate
from events.views.indices import admin as db_home
from events.views.indices import event_search
from pages.views import page as view_page

admin.autodiscover()
permission.autodiscover()


# Error pages
handler403 = 'data.views.err403'
handler404 = 'data.views.err404'
handler500 = 'data.views.err500'

urlpatterns = [
    # Examples:
    # url(r'^$', some_function, name='home'),
    # url(r'^lnldb/', include('lnldb.foo.urls', [namespace='foo'])),

    # Include other modules
    url(r'^admin/', include(admin.site.urls)),
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^hijack/', include('hijack.urls')),
    url(r'^__debug__/', include(debug_toolbar.urls)),
    url(r'^db/lookups/', include(ajax_select_urls)),
    url(r'^db/meetings/', include('meetings.urls', namespace='meetings')),
    url(r'^db/clients/', include('events.urls.orgs', namespace='orgs')),
    url(r'^db/inventory/', include('inventory.urls', namespace='inventory')),
    url(r'^db/projection/', include('projection.urls', namespace='projection')),
    url(r'^db/events/', include('events.urls.events', namespace='events')),
    url(r'^workorder/', include('events.urls.wizard', namespace='wizard')),
    url(r'^my/', include('events.urls.my', namespace='my')),
    url(r'^list/', include('events.urls.cal', namespace='cal')),
    url(r'^email/', include('emails.urls', namespace='emails')),
    url(r'', include('accounts.urls', namespace='accounts')),

    # special urls
    url(r'^db/$', db_home, name="home"),
    url(r'^(?P<slug>[-\w]+)/$', view_page, name="page"),
    url(r'^db/oldsearch$', event_search, name="events-search"),
    url(r'^db/search$', data.views.search, name="search"),

    # keep old urls
    url(r'^lnadmin/$', RedirectView.as_view(url="/db/", permanent=True)),
    url(r'^lnadmin/(?P<newpath>.+)$', RedirectView.as_view(url="/db/%(newpath)s", permanent=True)),
]

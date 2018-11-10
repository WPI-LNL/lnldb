import debug_toolbar
import django.contrib.auth.views
import permission
from ajax_select import urls as ajax_select_urls
from django.conf import settings
from django.urls import include, path, re_path
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
    path('admin/', admin.site.urls),
    path('admin/doc/', include('django.contrib.admindocs.urls')),
    path('hijack/', include('hijack.urls')),
    path('__debug__/', include(debug_toolbar.urls)),
    path('db/lookups/', include(ajax_select_urls)),
    path('db/meetings/', include('meetings.urls', namespace='meetings')),
    path('db/clients/', include('events.urls.orgs', namespace='orgs')),
    path('db/inventory/', include('inventory.urls', namespace='inventory')),
    path('db/projection/', include('projection.urls', namespace='projection')),
    path('db/events/', include('events.urls.events', namespace='events')),
    path('workorder/', include('events.urls.wizard', namespace='wizard')),
    path('my/', include('events.urls.my', namespace='my')),
    path('list/', include('events.urls.cal', namespace='cal')),
    path('email/', include('emails.urls', namespace='emails')),
    path('', include('accounts.urls', namespace='accounts')),

    # special urls
    path('db/', db_home, name="home"),
    re_path(r'^(?P<slug>[-\w]+)/$', view_page, name="page"),
    path('db/oldsearch', event_search, name="events-search"),
    path('db/search', data.views.search, name="search"),
    path('db/workorderwizard-load', data.views.workorderwizard_load, name="wizard-load"),
    path('db/workorderwizard-submit', data.views.workorderwizard_submit, name="wizard-submit"),

    # keep old urls
    path('lnadmin/', RedirectView.as_view(url="/db/", permanent=True)),
    re_path(r'^lnadmin/(?P<newpath>.+)$', RedirectView.as_view(url="/db/%(newpath)s", permanent=True)),
]

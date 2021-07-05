import debug_toolbar
import permission
from ajax_select import urls as ajax_select_urls
from django.conf import settings
from django.conf.urls import include, url
from django.contrib import admin
from django.views.generic.base import RedirectView

import hijack.urls
import data.views
from events.views.indices import admin as db_home, index
from events.views.indices import event_search, survey_dashboard, workshops
from pages.views import page as view_page

admin.autodiscover()
permission.autodiscover()

# Error pages
handler403 = 'data.views.err403'
handler404 = 'data.views.err404'
handler500 = 'data.views.err500'

urlpatterns = []

if settings.SAML2_ENABLED:
    urlpatterns += [
        url(r'^saml2_auth/', include('django_saml2_auth.urls', namespace='djangosaml2')),
    ]

urlpatterns += [
    # Examples:
    # url(r'^$', some_function, name='home'),
    # url(r'^lnldb/', include('lnldb.foo.urls', [namespace='foo'])),

    # Include other modules
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', admin.site.urls),
    url(r'^hijack/', include(hijack.urls)),
    url(r'^__debug__/', include(debug_toolbar.urls)),
    url(r'^db/lookups/', include(ajax_select_urls)),
    url(r'^db/meetings/', include(('meetings.urls', 'meetings'), namespace='meetings')),
    url(r'^db/clients/', include(('events.urls.orgs', 'lnldb'), namespace='orgs')),
    url(r'^db/equipment/', include(('inventory.urls', 'inventory'), namespace='equipment')),
    url(r'^db/laptops/', include(('devices.urls.laptops', 'laptops'), namespace='laptops')),
    url(r'^db/projection/', include(('projection.urls', 'projection'), namespace='projection')),
    url(r'^db/events/', include(('events.urls.events', 'lnldb'), namespace='events')),
    url(r'^my/', include(('events.urls.my', 'lnldb'), namespace='my')),
    url(r'^list/', include(('events.urls.cal', 'lnldb'), namespace='cal')),
    url(r'^email/', include(('emails.urls', 'emails'), namespace='emails')),
    url(r'', include(('accounts.urls', 'accounts'), namespace='accounts')),
    url(r'', include(('members.urls', 'members'), namespace='members')),
    url(r'^api/', include(('api.urls', 'api'), namespace='api')),
    url(r'^mdm/', include(('devices.urls.mdm', 'mdm'), namespace="mdm")),
    url(r'^support/', include(('rt.urls', 'support'), namespace='support')),
    url(r'', include(('pages.urls', 'pages'), namespace='pages')),

    # special urls
    url(r'^db/$', db_home, name="home"),
    url(r'^welcome/$', index, name="index"),
    url(r'^db/oldsearch$', event_search, name="events-search"),
    url(r'^db/search$', data.views.search, name="search"),
    url(r'^db/survey-dashboard/$', survey_dashboard, name="survey-dashboard"),
    url(r'^db/workorderwizard-load$', data.views.workorderwizard_load, name="wizard-load"),
    url(r'^db/workorderwizard-submit$', data.views.workorderwizard_submit, name="wizard-submit"),
    url(r'^db/workorderwizard-autopopulate$', data.views.workorderwizard_findprevious, name="wizard-findprevious"),
    url(r'^workorder/', RedirectView.as_view(url='/workorder/', permanent=False)),
    url(r'^workshops/$', workshops, name='workshops'),

    # Download checkin data (hopefully this url can be removed some day)
    url(r'^downloads/logs/contact-tracing/$', data.views.contact_tracing_logs, name="csv-logs"),
    url(r'^maintenance/$', data.views.maintenance, name="maintenance"),

    # keep old urls
    url(r'^lnadmin/$', RedirectView.as_view(url="/db/", permanent=True)),
    url(r'^lnadmin/(?P<newpath>.+)$', RedirectView.as_view(url="/db/%(newpath)s", permanent=True)),

    # This has to be at the end so that it doesn't mask other urls
    url(r'^(?P<slug>[-\w]+)/$', view_page, name="page"),
]

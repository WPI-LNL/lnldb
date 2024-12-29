import debug_toolbar
import permission
from ajax_select import urls as ajax_select_urls
from django.conf import settings
from django.conf.urls import include
from django.urls import re_path
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
    import django_saml2_auth.views
    urlpatterns += [
        re_path(r'^sso/', include('django_saml2_auth.urls', namespace='djangosaml2')),
    ]

    

urlpatterns += [
    # Examples:
    # re_path(r'^$', some_function, name='home'),
    # re_path(r'^lnldb/', include('lnldb.foo.urls', [namespace='foo'])),

    # Include other modules
    re_path(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^hijack/', include(hijack.urls)),
    re_path(r'^__debug__/', include(debug_toolbar.urls)),
    re_path(r'^db/lookups/', include(ajax_select_urls)),
    re_path(r'^db/meetings/', include(('meetings.urls', 'meetings'), namespace='meetings')),
    re_path(r'^db/clients/', include(('events.urls.orgs', 'lnldb'), namespace='orgs')),
    re_path(r'^db/equipment/', include(('inventory.urls', 'inventory'), namespace='equipment')),
    re_path(r'^db/laptops/', include(('devices.urls.laptops', 'laptops'), namespace='laptops')),
    re_path(r'^db/projection/', include(('projection.urls', 'projection'), namespace='projection')),
    re_path(r'^db/events/', include(('events.urls.events', 'lnldb'), namespace='events')),
    re_path(r'^my/', include(('events.urls.my', 'lnldb'), namespace='my')),
    re_path(r'^list/', include(('events.urls.cal', 'lnldb'), namespace='cal')),
    re_path(r'^email/', include(('emails.urls', 'emails'), namespace='emails')),
    re_path(r'', include(('accounts.urls', 'accounts'), namespace='accounts')),
    re_path(r'', include(('members.urls', 'members'), namespace='members')),
    re_path(r'^api/', include(('api.urls', 'api'), namespace='api')),
    re_path(r'^slack/', include(('slack.urls', 'slack'), namespace='slack')),
    re_path(r'^mdm/', include(('devices.urls.mdm', 'mdm'), namespace="mdm")),
    re_path(r'^support/', include(('rt.urls', 'support'), namespace='support')),
    re_path(r'^spotify/', include(('spotify.urls', 'spotify'), namespace='spotify')),
    re_path(r'', include(('pages.urls', 'pages'), namespace='pages')),

    # special urls
    re_path(r'^db/$', db_home, name="home"),
    re_path(r'^welcome/$', index, name="index"),
    re_path(r'^db/oldsearch$', event_search, name="events-search"),
    re_path(r'^db/search$', data.views.search, name="search"),
    re_path(r'^db/survey-dashboard/$', survey_dashboard, name="survey-dashboard"),
    #    re_path(r'^db/workorderwizard-load$', data.views.workorderwizard_load, name="wizard-load"),
    #    re_path(r'^db/workorderwizard-submit$', data.views.workorderwizard_submit, name="wizard-submit"),
    #    re_path(r'^db/workorderwizard-autopopulate$', data.views.workorderwizard_findprevious, name="wizard-findprevious"),
    #    re_path(r'^workorder/', RedirectView.as_view(url='/workorder/', permanent=False)),
    re_path(r'^workshops/$', workshops, name='workshops'),

    re_path(r'^maintenance/$', data.views.maintenance, name="maintenance"),

    # keep old urls
    re_path(r'^lnadmin/$', RedirectView.as_view(url="/db/", permanent=True)),
    re_path(r'^lnadmin/(?P<newpath>.+)$', RedirectView.as_view(url="/db/%(newpath)s", permanent=True)),

    # This has to be at the end so that it doesn't mask other urls
    re_path(r'^(?P<slug>[-\w]+)/$', view_page, name="page"),
]

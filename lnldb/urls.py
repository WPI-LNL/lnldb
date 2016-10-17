import debug_toolbar
from ajax_select import urls as ajax_select_urls
from django.conf import settings
from django.conf.urls import include, url

from accounts.forms import LoginForm
from events.cal import EventFeed, FullEventFeed, LightEventFeed
from events.forms import named_event_forms
from events.views.wizard import EventWizard
from events.views.wizard import show_lighting_form_condition, show_sound_form_condition, \
    show_projection_form_condition, show_other_services_form_condition

# Uncomment the next two lines to enable the admin:
from django.contrib import admin

import permission

from django.views.generic.base import RedirectView

# cbv imports
# from acct.views import AcctUpdate, LNLUpdate, LNLAdd
# from members.views import UserUpdate
# from members.views import MemberUpdate
from events.views.flow import BillingCreate, BillingUpdate, BillingDelete
from events.views.flow import CCRCreate, CCRUpdate, CCRDelete
from events.views.orgs import OrgVerificationCreate
from emails.views import MeetingAnnounceView
from emails.views import MeetingAnnounceCCView
from projection.views import ProjectionCreate
from projection.views import BulkUpdateView
from projection.views import ProjectionistDelete
# event wizard form defenitions

from django.contrib.auth.decorators import login_required

admin.autodiscover()
permission.autodiscover()

event_wizard = EventWizard.as_view(
    named_event_forms,
    url_name='event_step',
    done_step_name='finished',
    condition_dict={
        'lighting': show_lighting_form_condition,
        'sound': show_sound_form_condition,
        'projection': show_projection_form_condition,
        'other': show_other_services_form_condition,
    }
)


# hacky as hell, but it secures our wizards
@login_required
def login_wrapped_wo(request, **kwargs):
    return event_wizard(request, **kwargs)

# Error pages
handler403 = 'data.views.err403'
handler404 = 'data.views.err404'
handler500 = 'data.views.err500'

# generics

urlpatterns = [
                       # Examples:
                       # url(r'^$', 'lnldb.views.home', name='home'),
                       # url(r'^lnldb/', include('lnldb.foo.urls')),

                       # Uncomment the admin/doc line below to enable admin documentation:
                       url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
                       url(r'^jsi18n', 'django.views.i18n.javascript_catalog'),

                       # Uncomment the next line to enable the admin:
                       url(r'^admin/', include(admin.site.urls)),
                       #
                       url(r'^$', 'pages.views.page', {'slug': 'index'}),
                       # use the nice redirector
                       #url(r'^login/$', 'django_cas_ng.views.login', name="cas-login"),
                       url(r'^login/$', 'accounts.views.smart_login', name="login"),
                       # best use CAS for logout, since it's guaranteed to log the user out
                       #  (without immediately signing them back in)
                       url(r'^logout/$', 'django_cas_ng.views.logout', name="logout"),

                       url(r'^cas/login/$', 'django_cas_ng.views.login', name="cas-explicit-login"),
                       url(r'^cas/logout/$', 'django_cas_ng.views.logout', name="cas-logout"),
                       # maybe we do
                       url(r'^local/login/$', 'django.contrib.auth.views.login',
                           {'template_name': 'registration/login.html',
                            'authentication_form': LoginForm},
                           name="local-login"),
                       url(r'^local/logout/$', 'django.contrib.auth.views.logout',
                           {'template_name': 'registration/logout.html'},
                           name="local-logout"),

                       url(r'^local/reset/$', 'django.contrib.auth.views.password_reset',
                           {'template_name': 'registration/reset_password.html',
                            'from_email': settings.DEFAULT_FROM_ADDR},
                           name='password_reset'),
                       url(r'^local/reset/confirm/(?P<uidb64>[0-9A-Za-z]+)-(?P<token>.+)/$',
                           'django.contrib.auth.views.password_reset_confirm',
                           {'template_name': 'registration/reset_password_form.html'},
                           name='password_reset_confirm'),
                       url(r'^local/reset/sent/$', 'django.contrib.auth.views.password_reset_done',
                           {'template_name': 'registration/reset_password_sent.html'},
                           name='password_reset_done'),
                       url(r'^local/reset/done/$', 'django.contrib.auth.views.password_reset_complete',
                           {'template_name': 'registration/reset_password_finished.html'},
                           name='password_reset_complete'),
                       # static

                       # user facing shit
                       url(r'^my/workorders/$', 'events.views.my.mywo', name="my-wo"),
                       url(r'^my/workorders/attach/(?P<id>[0-9]+)/$', 'events.views.flow.assignattach_external',
                           name="my-wo-attach"),
                       url(r'^my/orgs/$', 'events.views.my.myorgs'),
                       url(r'^my/orgs/form/$', 'events.views.my.myorgform', name="selfserivceorg"),
                       url(r'^my/orgs/incharge/$', 'events.views.orgs.orglist', name="my-orgs-incharge-list"),
                       url(r'^my/orgs/incharge/(?P<id>[0-9a-f]+)/$', 'events.views.orgs.orgedit',
                           name="my-orgs-incharge-edit"),
                       url(r'^my/orgs/transfer/(?P<id>[0-9]+)/$', 'events.views.orgs.org_mkxfer', name="my-orgs-xfer"),
                       url(r'^my/orgs/transfer/(?P<idstr>[0-9a-f]+)/$', 'events.views.orgs.org_acceptxfer',
                           name="my-orgs-acceptxfer"),
                       url(r'^my/events/$', 'events.views.my.myevents', name="my-events"),
                       url(r'^my/events/(?P<id>[0-9a-f]+)/pdf/$', 'pdfs.views.generate_event_pdf',
                           name="my-events-pdf"),
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
                       # workorders
                       url(r'^workorder/(?P<step>.+)/$', login_wrapped_wo, name='event_step'),
                       url(r'^workorder/$', login_wrapped_wo, name='event'),
                       url(r'^my/events/(?P<eventid>[0-9]+)/repeat/$', 'events.views.my.myworepeat', name="my-repeat"),
                       #
                       url(r'^db/$', 'events.views.indices.admin', name="db"),
                       url(r'^db/status/$', 'events.views.indices.dbg_land'),
                       url(r'^db/lookups/', include(ajax_select_urls)),

                       # events
                       url(r'^db/events/view/(?P<id>[0-9a-f]+)/$', 'events.views.flow.viewevent',
                           name="events-detail"),
                       url(r'^db/events/view/(?P<id>[0-9a-f]+)/pdf/$', 'pdfs.views.generate_event_pdf',
                           name="events-pdf"),
                       url(r'^db/events/pdf/(?P<ids>\d+(,\d+)*)/$', 'pdfs.views.generate_event_pdf_multi',
                           name="events-pdf-multi"),
                       url(r'^db/events/pdf/$', 'pdfs.views.generate_event_pdf_multi',
                           name="events-pdf-multi-empty"),
                       url(r'^db/events/mk/$', 'events.views.mkedrm.eventnew', name="event-new"),
                       url(r'^db/events/edit/(?P<id>[0-9a-f]+)/$', 'events.views.mkedrm.eventnew',
                           name="event-edit"),
                       url(r'^db/events/approve/(?P<id>[0-9a-f]+)/$', 'events.views.flow.approval',
                           name="event-approve"),
                       url(r'^db/events/deny/(?P<id>[0-9a-f]+)/$', 'events.views.flow.denial', name="event-deny"),
                       url(r'^db/events/review/(?P<id>[0-9a-f]+)/$', 'events.views.flow.review',
                           name="event-review"),
                       url(r'^db/events/review/(?P<id>[0-9a-f]+)/remind/(?P<uid>[0-9a-f]+)/$',
                           'events.views.flow.reviewremind', name="event-review-remind"),
                       url(r'^db/events/close/(?P<id>[0-9a-f]+)/$', 'events.views.flow.close', name="event-close"),
                       url(r'^db/events/cancel/(?P<id>[0-9a-f]+)/$', 'events.views.flow.cancel', name="event-cancel"),
                       url(r'^db/events/reopen/(?P<id>[0-9a-f]+)/$', 'events.views.flow.reopen', name="event-reopen"),
                       url(r'^db/events/view/(?P<id>[0-9]+)/billing/pdf/$', 'pdfs.views.generate_event_bill_pdf',
                           name="events-pdf-bill"),
                       url(r'^db/events/view/(?P<event>[0-9]+)/billing/mk/$', BillingCreate.as_view(),
                           name="event-mkbilling"),
                       url(r'^db/events/view/(?P<event>[0-9]+)/billing/update/(?P<pk>[0-9]+)/$',
                           BillingUpdate.as_view(), name="event-updbilling"),
                       url(r'^db/events/view/(?P<event>[0-9]+)/billing/rm/(?P<pk>[0-9]+)/$',
                           BillingDelete.as_view(), name="event-rmbilling"),
                       url(r'^db/events/view/(?P<event>[0-9]+)/report/mk/$', CCRCreate.as_view(), name="event-mkccr"),
                       url(r'^db/events/view/(?P<event>[0-9]+)/report/update/(?P<pk>[0-9]+)/$', CCRUpdate.as_view(),
                           name="event-updccr"),
                       url(r'^db/events/view/(?P<event>[0-9]+)/report/rm/(?P<pk>[0-9]+)/$', CCRDelete.as_view(),
                           name="event-rmccr"),

                       url(r'^db/events/upcoming/$', 'events.views.list.upcoming', name="upcoming"),
                       url(r'^db/events/upcoming/(?P<start>\d{4}-\d{2}-\d{2})/$', 'events.views.list.upcoming'),
                       url(r'^db/events/upcoming/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.upcoming'),


                       url(r'^db/oldsearch$', "events.views.indices.event_search", name="events-search"),
                       url(r'^db/search$', "data.views.search", name="search"),

                       # meetings
                       url(r'^db/meetings/', include('meetings.urls', namespace='meetings')),
                       url(r'^db/clients/', include('events.urls.orgs', namespace='orgs')),

                       # projection
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
                           name="events-pdf-multi"),

                       url(r'^db/projection/bulkevents/$', 'projection.views.bulk_projection',
                           name="projection-bulk2"),

                       url(r'^db/events/findchief/$', 'events.views.list.findchief', name="findchief"),
                       url(r'^db/events/findchief/(?P<start>\d{4}-\d{2}-\d{2})/$', 'events.views.list.findchief'),
                       url(r'^db/events/findchief/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.findchief'),

                       url(r'^db/events/incoming/$', 'events.views.list.incoming', name="incoming"),
                       url(r'^db/events/incoming/(?P<start>\d{4}-\d{2}-\d{2})/$', 'events.views.list.incoming'),
                       url(r'^db/events/incoming/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.incoming'),

                       url(r'^db/events/open/$', 'events.views.list.openworkorders', name="open"),
                       url(r'^db/events/open/(?P<start>\d{4}-\d{2}-\d{2})/$', 'events.views.list.openworkorders'),
                       url(r'^db/events/open/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.openworkorders'),

                       url(r'^db/events/unreviewed/$', 'events.views.list.unreviewed', name="unreviewed"),
                       url(r'^db/events/unreviewed/(?P<start>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.unreviewed'),
                       url(r'^db/events/unreviewed/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.unreviewed'),

                       url(r'^db/events/unbilled/$', 'events.views.list.unbilled', name="unbilled"),
                       url(r'^db/events/unbilled/(?P<start>\d{4}-\d{2}-\d{2})/$', 'events.views.list.unbilled'),
                       url(r'^db/events/unbilled/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.unbilled'),

                       url(r'^db/events/unbilledsemester/$', 'events.views.list.unbilled_semester',
                           name="unbilled-semester"),
                       url(r'^db/events/unbilledsemester/(?P<start>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.unbilled_semester'),
                       url(r'^db/events/unbilledsemester/'
                           r'(?P<start>\d{4}-\d{2}-\d{2})/'
                           r'(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.unbilled_semester'),

                       url(r'^db/events/paid/$', 'events.views.list.paid', name="paid"),
                       url(r'^db/events/paid/(?P<start>\d{4}-\d{2}-\d{2})/$', 'events.views.list.paid'),
                       url(r'^db/events/paid/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.paid'),
                       url(r'^db/events/unpaid/$', 'events.views.list.unpaid', name="unpaid"),
                       url(r'^db/events/unpaid/(?P<start>\d{4}-\d{2}-\d{2})/$', 'events.views.list.unpaid'),
                       url(r'^db/events/unpaid/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.unpaid'),

                       url(r'^db/events/closed/$', 'events.views.list.closed', name="closed"),
                       url(r'^db/events/closed/(?P<start>\d{4}-\d{2}-\d{2})/$', 'events.views.list.closed'),
                       url(r'^db/events/closed/(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$',
                           'events.views.list.closed'),

                       url(r'^db/events/crew/(?P<id>[0-9a-f]+)/$', 'events.views.flow.assigncrew'),
                       url(r'^db/events/rmcrew/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$',
                           'events.views.flow.rmcrew'),
                       url(r'^db/events/crewchief/(?P<id>[0-9a-f]+)/$', 'events.views.flow.assigncc'),

                       url(r'^db/events/(?P<id>[0-9]+)/hours/bulk/$', 'events.views.flow.hours_bulk_admin',
                           name="admin-cchours-bulk"),

                       url(r'^db/events/attachments/(?P<id>[0-9a-f]+)/$', 'events.views.flow.assignattach',
                           name="eventattachments"),
                       url(r'^db/events/extras/(?P<id>[0-9a-f]+)/$', 'events.views.flow.extras',
                           name="eventextras"),
                       url(r'^db/events/oneoff/(?P<id>[0-9a-f]+)/$', 'events.views.flow.oneoff',
                           name="eventoneoff"),
                       url(r'^db/events/rmcc/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$', 'events.views.flow.rmcc'),

                       url(r'^list/$', 'events.views.list.public_facing', name="list"),
                       url(r'^list/feed.ics$', EventFeed(), name='public_cal_feed'),
                       url(r'^list/feed_full.ics$', FullEventFeed(), name='full_cal_feed'),
                       url(r'^list/feed_light.ics$', LightEventFeed(), name='light_cal_feed'),
                       url(r'^list/json(/*?.*)*$', 'events.cal.cal_json'),

                       # orgs (clients)
                       url(r'^db/clients/funds/edit/(?P<id>[0-9]+)/$', 'events.views.orgs.fund_edit',
                           name="admin-fundedit"),
                       url(r'^db/clients/funds/add/$', 'events.views.orgs.fund_edit', name="admin-fundadd"),
                       url(r'^db/clients/funds/add/(?P<org>[0-9]+)/$', 'events.views.orgs.fund_edit',
                           name="admin-fundaddorg"),

                       # nice include statements (ie. the future)
                       url(r'^db/inventory/', include('inventory.urls', namespace='inventory')),
                       url(r'', include('accounts.urls', namespace='accounts')),

                       # emails
                       url(r'^email/announce/(?P<slug>[0-9a-f]+)/$', MeetingAnnounceView.as_view(),
                           name="email-view-announce"),
                       url(r'^email/announcecc/(?P<slug>[0-9a-f]+)/$', MeetingAnnounceCCView.as_view(),
                           name="email-view-announce-cc"),

                       # special urls
                       url(r'^status/$', "data.views.status"),
                       url(r'^db/accesslog/$', 'data.views.access_log', name="access-log"),
                       url(r'^NOTOUCHING/$', 'data.views.fuckoffkitty'),
                       url(r'^lnldb/fuckoffkitty/$', RedirectView.as_view(url="/NOTOUCHING/", permanent=False)),
                       url(r'^lnadmin/$', RedirectView.as_view(url="/db/", permanent=True)),

                       url(r'^(?P<slug>[-\w]+)/$', 'pages.views.page'),

                       # keep old urls
                       url(r'^lnadmin/(?P<newpath>.+)$', RedirectView.as_view(url="/db/%(newpath)s", permanent=True)),

                       # debugging
                       url(r'^hijack/', include('hijack.urls')),
                       url(r'^__debug__/', include(debug_toolbar.urls))
]

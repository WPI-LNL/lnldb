from django.conf import settings
from acct.forms import LoginForm
import debug_toolbar
from django.conf.urls import patterns, include, url

from events.cal import EventFeed
from events.forms import named_event_forms
from events.views.wizard import EventWizard
from events.views.wizard import show_lighting_form_condition, show_sound_form_condition, show_projection_form_condition, \
    show_other_services_form_condition

from django.views.generic.base import TemplateView

from ajax_select import urls as ajax_select_urls

# Uncomment the next two lines to enable the admin:
from django.contrib import admin

admin.autodiscover()
import permission

permission.autodiscover()

# cbv imports
from acct.views import AcctUpdate, LNLUpdate, LNLAdd
from members.views import UserUpdate
from members.views import MemberUpdate
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
from django.views.generic.base import RedirectView

urlpatterns = patterns('',
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
                       url(r'^login/$', 'acct.views.smart_login', name="login"),
                       # best use CAS for logout, since it's guaranteed to log the user out
                       #  (without immediately signing them back in)
                       url(r'^logout/$', 'django_cas.views.logout', name="logout"),

                       url(r'^cas/login/$', 'django_cas.views.login', name="cas-login"),
                       url(r'^cas/logout/$', 'django_cas.views.logout', name="cas-logout"),
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
                       url(r'^my/$', 'events.views.my.my', name="my"),
                       url(r'^my/contact/$', LNLUpdate.as_view(), name="my-lnl"),
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
                       url(r'^my/acct/$', AcctUpdate.as_view(), name="my-acct"),
                       url(r'^my/acct/send_lnl_member_request/$', 'acct.views.send_member_request',
                           name="my-acct-request-lnl"),
                       url(r'^my/events/$', 'events.views.my.myevents', name="my-events"),
                       url(r'^my/events/(?P<id>[0-9]+)$', 'events.views.my.myeventdetail', name="my-event-detail"),
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
                       #workorders
                       url(r'^workorder2/$', 'events.views.indices.workorder'),
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


                       # members
                       url(r'^list/mdc/raw/$', 'members.views.mdc_raw', name="mdc_raw"),
                       url(r'^list/mdc/$', 'members.views.mdc'),
                       url(r'^db/members/officers/$', 'members.views.officers'),
                       url(r'^db/members/active/$', 'members.views.active'),
                       url(r'^db/members/associate/$', 'members.views.associate'),
                       url(r'^db/members/alum/$', 'members.views.alum'),
                       url(r'^db/members/away/$', 'members.views.away'),
                       url(r'^db/members/inactive/$', 'members.views.inactive'),
                       url(r'^db/members/detail/(?P<id>[0-9a-f]+)/$', 'members.views.detail', name="memberdetail"),
                       url(r'^db/members/detail/(?P<username>[^/]+)/$', 'members.views.named_detail',
                           name="namedmemberdetail"),
                       url(r'^db/members/edit/(?P<pk>[0-9a-f]+)/$', UserUpdate.as_view(), name="memberupdate"),
                       url(r'^db/members/editcontact/(?P<pk>[0-9a-f]+)/$', MemberUpdate.as_view(),
                           name="membercontact"),

                       #misc
                       url(r'^db/misc/users/contact/$', 'members.views.contactusers', name="users-contact"),
                       url(r'^db/misc/users/unsorted/$', 'members.views.limbousers', name="users-limbo"),
                       url(r'^db/misc/users/add/$', LNLAdd.as_view(), name="users-add"),
                       url(r'^db/oldsearch$', "events.views.indices.event_search", name="events-search"),
                       url(r'^db/search$', "data.views.search", name="search"),


                       #meetings
                       url(r'^db/meetings/new/$', 'meetings.views.newattendance', name="meeting-new"),
                       url(r'^db/meetings/$', 'meetings.views.listattendance', name="meeting-list"),
                       url(r'^db/meetings/(\d+)/list/$', 'meetings.views.listattendance', ),
                       url(r'^db/meetings/(\d+)/$', 'meetings.views.viewattendance', name="meeting-view"),
                       url(r'^db/meetings/(\d+)/addchief/(\d+)/$', 'meetings.views.updateevent',
                           name="meeting-updateevent"),
                       url(r'^db/meetings/(\d+)/edit/$', 'meetings.views.editattendance', name="meeting-edit"),
                       url(r'^db/meetings/(\d+)/remind/mtg/$', 'meetings.views.mknotice', name="meeting-email"),
                       url(r'^db/meetings/(\d+)/remind/cc/$', 'meetings.views.mkccnotice',
                           name="meeting-cc-email"),
                       url(r'^db/meetings/(?P<mtg_id>\d+)/download/(?P<att_id>\d+)/$',
                           'meetings.views.download_att', name="meeting-att-dl"),
                       url(r'^db/meetings/(?P<mtg_id>\d+)/file/(?P<att_id>\d+)/$', 'meetings.views.modify_att',
                           name="meeting-att-edit"),
                       url(r'^db/meetings/(?P<mtg_id>\d+)/rm/(?P<att_id>\d+)/$',
                           'meetings.views.rm_att', name="meeting-att-rm"),

                       #projection
                       url(r'^db/projection/list/$', 'projection.views.plist_detail',
                           name="projection-list-detail"),
                       url(r'^db/projection/list/other/$', 'projection.views.plist', name="projection-list"),
                       url(r'^db/projection/bulk/$', BulkUpdateView.as_view(), name="projection-bulk-update"),
                       # url(r'^db/projection/update/(?P<pk>[0-9a-f]+)/$', ProjectionUpdate.as_view(),
                       # name="projection-update"),
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
                       url(r'^list/json(/*?.*)*$', 'events.cal.cal_json'),

                       # orgs (clients)
                       url(r'^db/clients/$', 'events.views.orgs.vieworgs', name="admin-orglist"),
                       url(r'^db/clients/(?P<id>[0-9]+)/$', 'events.views.orgs.orgdetail', name="admin-orgdetail"),
                       url(r'^db/clients/(?P<org>\d+)/verify/$', OrgVerificationCreate.as_view(),
                           name="admin-org-verify"),
                       url(r'^db/clients/add/$', 'events.views.orgs.addeditorgs', name="admin-orgadd"),
                       url(r'^db/clients/edit/(\d+)/$', 'events.views.orgs.addeditorgs', name="admin-orgedit"),
                       url(r'^db/clients/funds/edit/(?P<id>[0-9]+)/$', 'events.views.orgs.fund_edit',
                           name="admin-fundedit"),
                       url(r'^db/clients/funds/add/$', 'events.views.orgs.fund_edit', name="admin-fundadd"),
                       url(r'^db/clients/funds/add/(?P<org>[0-9]+)/$', 'events.views.orgs.fund_edit',
                           name="admin-fundaddorg"),


                       #inventory
                       url(r'^db/inventory/', include('inventory.urls', namespace='inventory')),

                       #members
                       url(r'^list/mdc/raw/$', 'members.views.mdc_raw'),
                       url(r'^list/mdc/$', 'members.views.mdc'),
                       url(r'^db/members/officers/$', 'members.views.officers'),
                       url(r'^db/members/active/$', 'members.views.active'),
                       url(r'^db/members/associate/$', 'members.views.associate'),
                       url(r'^db/members/alum/$', 'members.views.alum'),
                       url(r'^db/members/away/$', 'members.views.away'),
                       url(r'^db/members/inactive/$', 'members.views.inactive'),
                       url(r'^db/members/detail/(?P<id>[0-9a-f]+)/$', 'members.views.detail', name="memberdetail"),
                       url(r'^db/members/edit/(?P<pk>[0-9a-f]+)/$', UserUpdate.as_view(), name="memberupdate"),
                       url(r'^db/members/editcontact/(?P<pk>[0-9a-f]+)/$', MemberUpdate.as_view(),
                           name="membercontact"),

                       #misc
                       url(r'^db/misc/users/contact/$', 'members.views.contactusers', name="users-contact"),
                       url(r'^db/misc/users/unsorted/$', 'members.views.limbousers', name="users-limbo"),
                       url(r'^db/misc/users/add/$', LNLAdd.as_view(), name="users-add"),
                       url(r'^db/search$', "events.views.indices.event_search", name="events-search"),


                       # projection
                       url(r'^db/projection/list/$', 'projection.views.plist_detail',
                           name="projection-list-detail"),
                       url(r'^db/projection/list/other/$', 'projection.views.plist', name="projection-list"),
                       url(r'^db/projection/bulk/$', BulkUpdateView.as_view(), name="projection-bulk-update"),
                       # url(r'^db/projection/update/(?P<pk>[0-9a-f]+)/$',
                       #     ProjectionUpdate.as_view(),
                       #     name="projection-update"),
                       url(r'^db/projection/update/(?P<id>[0-9a-f]+)/$', "projection.views.projection_update",
                           name="projection-update"),
                       url(r'^db/projection/rm/(?P<pk>[0-9a-f]+)/$', ProjectionistDelete.as_view(),
                           name="projection-delete"),
                       url(r'^db/projection/mk/$', ProjectionCreate.as_view(), name="projection-create"),
                       url(r'^db/projection/list/detail/pdf/$', 'pdfs.views.generate_projection_pdf',
                           name="events-pdf-multi"),

                       url(r'^db/projection/bulkevents/$', 'projection.views.bulk_projection',
                           name="projection-bulk2"),


                       #emails
                       url(r'^email/announce/(?P<slug>[0-9a-f]+)/$', MeetingAnnounceView.as_view(),
                           name="email-view-announce"),
                       url(r'^email/announcecc/(?P<slug>[0-9a-f]+)/$', MeetingAnnounceCCView.as_view(),
                           name="email-view-announce-cc"),

                       #special urls
                       url(r'^status/$', "data.views.status"),
                       url(r'^db/accesslog/$', 'data.views.access_log', name="access-log"),
                       url(r'^NOTOUCHING/$', 'data.views.fuckoffkitty'),
                       url(r'^lnldb/fuckoffkitty/$', RedirectView.as_view(url="/NOTOUCHING/", permanent=False)),
                       url(r'^lnadmin/$', RedirectView.as_view(url="/db/", permanent=True)),

                       url(r'^(?P<slug>[-\w]+)/$', 'pages.views.page'),

                       # keep old urls
                       url(r'^lnadmin/(?P<newpath>.+)$', RedirectView.as_view(url="/db/%(newpath)s", permanent=True)),
                       # url(r'^db/(?P<msg>\w+)/$', 'events.views.indices.admin'),

                       # debugging
                       url(r'^hijack/', include('hijack.urls')),
                       url(r'^__debug__/', include(debug_toolbar.urls)))

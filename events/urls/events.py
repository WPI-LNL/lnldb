from django.conf.urls import include, url

from ..views import list as list_views, flow as flow_views, mkedrm as mkedrm_views
from pdfs import views as pdf_views


def generate_date_patterns(func, name):
    return include([
        url(r'^$', func, name=name),
        url(r'^(?P<start>\d{4}-\d{2}-\d{2})/$', func, name=name),
        url(r'^(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$', func, name=name),
    ])

app_name = 'lnldb'

# prefix: /db/events
urlpatterns = [
    # list views
    url(r'^upcoming/', generate_date_patterns(list_views.upcoming, name="upcoming")),
    url(r'^findchief/', generate_date_patterns(list_views.findchief, name="findchief")),
    url(r'^incoming/', generate_date_patterns(list_views.incoming, name="incoming")),
    url(r'^open/', generate_date_patterns(list_views.openworkorders, name="open")),
    url(r'^unreviewed/', generate_date_patterns(list_views.unreviewed, name="unreviewed")),
    url(r'^unbilled/', generate_date_patterns(list_views.unbilled, name="unbilled")),
    url(r'^unbilledsemester/', generate_date_patterns(list_views.unbilled_semester, name="unbilled-semester")),
    url(r'^paid/', generate_date_patterns(list_views.paid, name="paid")),
    url(r'^unpaid/', generate_date_patterns(list_views.unpaid, name="unpaid")),
    url(r'^workday/', generate_date_patterns(list_views.awaitingworkday, name="awaitingworkday")),
    url(r'^closed/', generate_date_patterns(list_views.closed, name="closed")),
    url(r'^all/', generate_date_patterns(list_views.all, name="all")),

    # calendar views corresponding to the list views
    url(r'^findchief/calendar/', generate_date_patterns(list_views.findchief_cal, name="findchief-cal")),
    url(r'^incoming/calendar/', generate_date_patterns(list_views.incoming_cal, name="incoming-cal")),
    url(r'^open/calendar/', generate_date_patterns(list_views.openworkorders_cal, name="open-cal")),
    url(r'^unreviewed/calendar/', generate_date_patterns(list_views.unreviewed_cal, name="unreviewed-cal")),
    url(r'^unbilled/calendar/', generate_date_patterns(list_views.unbilled_cal, name="unbilled-cal")),
    url(r'^unbilledsemester/calendar/', generate_date_patterns(list_views.unbilled_semester_cal,
                                                               name="unbilled-semester-cal")),
    url(r'^paid/calendar/', generate_date_patterns(list_views.paid_cal, name="paid-cal")),
    url(r'^unpaid/calendar/', generate_date_patterns(list_views.unpaid_cal, name="unpaid-cal")),
    url(r'^closed/calendar/', generate_date_patterns(list_views.closed_cal, name="closed-cal")),
    url(r'^all/calendar/', generate_date_patterns(list_views.all_cal, name="all-cal")),

    # Actual event pages

    url(r'^view/(?P<id>[0-9a-f]+)/$', flow_views.viewevent, name="detail"),
    url(r'^pdf/(?P<ids>\d+(,\d+)*)?/?$', pdf_views.generate_event_pdf_multi,
        name="pdf-multi"),
    url(r'^bills-pdf/(?P<ids>\d+(,\d+)*)?/?$', pdf_views.generate_event_bill_pdf_multi,
        name="bill-pdf-multi"),
    url(r'^view/(?P<id>[0-9a-f]+)/pdf/$', pdf_views.generate_event_pdf, name="pdf"),
    # url(r'^db/events/mk/$', 'events.views.mkedrm.eventnew', name="event-new"),
    url(r'^mk/$', mkedrm_views.eventnew, name="new"),
    url(r'^edit/(?P<id>[0-9a-f]+)/$', mkedrm_views.eventnew, name="edit"),
    url(r'^approve/(?P<id>[0-9a-f]+)/$', flow_views.approval, name="approve"),
    url(r'^deny/(?P<id>[0-9a-f]+)/$', flow_views.denial, name="deny"),
    url(r'^review/(?P<id>[0-9a-f]+)/$', flow_views.review, name="review"),
    url(r'^review/(?P<id>[0-9a-f]+)/remind/(?P<uid>[0-9a-f]+)/$',
        flow_views.reviewremind, name="remind"),
    url(r'^review/(?P<id>[0-9a-f]+)/remind/$', flow_views.remindall, name="remindall"),
    url(r'^close/(?P<id>[0-9a-f]+)/$', flow_views.close, name="close"),
    url(r'^cancel/(?P<id>[0-9a-f]+)/$', flow_views.cancel, name="cancel"),
    url(r'^reopen/(?P<id>[0-9a-f]+)/$', flow_views.reopen, name="reopen"),
    url(r'^crew/(?P<id>[0-9a-f]+)/$', flow_views.assigncrew, name="add-crew"),
    url(r'^rmcrew/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$',
        flow_views.rmcrew, name="remove-crew"),
    url(r'^(?P<id>[0-9]+)/hours/bulk/$', flow_views.hours_bulk_admin,
        name="add-bulk-crew"),
    url(r'^selfcrew/(?P<id>[0-9]+)/$', flow_views.hours_prefill_self, name="selfcrew"),
    url(r'^crewchief/(?P<id>[0-9a-f]+)/$', flow_views.assigncc, name="chiefs"),
    url(r'^rmcc/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$', flow_views.rmcc, name="remove-chief"),
    url(r'^attachments/(?P<id>[0-9a-f]+)/$', flow_views.assignattach,
        name="files"),
    url(r'^extras/(?P<id>[0-9a-f]+)/$', flow_views.extras, name="extras"),
    url(r'^oneoff/(?P<id>[0-9a-f]+)/$', flow_views.oneoff, name="oneoffs"),
    url(r'^enter-worktag/(?P<pk>[0-9a-f]+)/$', flow_views.WorkdayEntry.as_view(), name="worktag-form"),
    url(r'^workday-entered/(?P<id>[0-9a-f]+)/$', flow_views.mark_entered_into_workday, name="workday-entered"),

    # The nice url structure. TODO: fit the rest in here (with deprecation, of course)
    url(r'^view/(?P<event>[0-9]+)/', include([
        url(r'^billing/', view=include(([
            url(r'^mk/$', flow_views.BillingCreate.as_view(), name="new"),
            url(r'^update/(?P<pk>[0-9]+)/$', flow_views.BillingUpdate.as_view(),
                name="edit"),
            url(r'^email/(?P<billing>[0-9]+)/$', flow_views.BillingEmailCreate.as_view(),
                name="email"),
            url(r'^pay/(?P<pk>[0-9]+)/$', flow_views.pay_bill,
                name="pay"),
            url(r'^rm/(?P<pk>[0-9]+)/$', flow_views.BillingDelete.as_view(),
                name="remove"),
            url(r'^pdf/$', pdf_views.generate_event_bill_pdf, name="pdf"),
        ], 'lnldb'), namespace="bills")),
        url(r'^report/', view=include(([
            url(r'^mk/$', flow_views.CCRCreate.as_view(), name="new"),
            url(r'^update/(?P<pk>[0-9]+)/$', flow_views.CCRUpdate.as_view(),
                name="edit"),
            url(r'^rm/(?P<pk>[0-9]+)/$', flow_views.CCRDelete.as_view(), name="remove")
        ], 'lnldb'), namespace="reports")),
    ])),
    url(r'^multibills/', include(([
        url(r'^$', list_views.multibillings, name="list"),
        url(r'^mk/$', flow_views.MultiBillingCreate.as_view(), name="new"),
        url(r'^update/(?P<pk>[0-9]+)/$', flow_views.MultiBillingUpdate.as_view(), name="edit"),
        url(r'^rm/(?P<pk>[0-9]+)/$', flow_views.MultiBillingDelete.as_view(), name="remove"),
        url(r'^email/(?P<multibilling>[0-9]+)/$', flow_views.MultiBillingEmailCreate.as_view(), name="email"),
        url(r'^pdf/(?P<multibilling>[0-9]+)/$', pdf_views.generate_multibill_pdf, name="pdf"),
    ], 'lnldb'), namespace="multibillings")),
]

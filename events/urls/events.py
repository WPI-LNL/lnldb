from django.conf.urls import include
from django.urls import re_path

from ..views import list as list_views, flow as flow_views, mkedrm as mkedrm_views, indices
from pdfs import views as pdf_views


def generate_date_patterns(func, name):
    return include([
        re_path(r'^$', func, name=name),
        re_path(r'^(?P<start>\d{4}-\d{2}-\d{2})/$', func, name=name),
        re_path(r'^(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$', func, name=name),
    ])

app_name = 'lnldb'

# prefix: /db/events
urlpatterns = [
    # list views
    re_path(r'^findchief/', generate_date_patterns(list_views.findchief, name="findchief")),
    re_path(r'^prerequest/', generate_date_patterns(list_views.prerequest, name="prerequest")),
    re_path(r'^prospective/', generate_date_patterns(list_views.prospective, name="prospective")),
    re_path(r'^incoming/', generate_date_patterns(list_views.incoming, name="incoming")),
    re_path(r'^confirmed/', generate_date_patterns(list_views.confirmed, name="confirmed")),
    re_path(r'^open/', generate_date_patterns(list_views.openworkorders, name="open")),
    re_path(r'^unreviewed/', generate_date_patterns(list_views.unreviewed, name="unreviewed")),
    re_path(r'^unbilled/', generate_date_patterns(list_views.unbilled, name="unbilled")),
    re_path(r'^unbilledsemester/', generate_date_patterns(list_views.unbilled_semester, name="unbilled-semester")),
    re_path(r'^paid/', generate_date_patterns(list_views.paid, name="paid")),
    re_path(r'^unpaid/', generate_date_patterns(list_views.unpaid, name="unpaid")),
    re_path(r'^workday/', generate_date_patterns(list_views.awaitingworkday, name="awaitingworkday")),
    re_path(r'^unpaidworkday/', generate_date_patterns(list_views.unpaid_workday, name="unpaid-workday")),
    re_path(r'^closed/', generate_date_patterns(list_views.closed, name="closed")),
    re_path(r'^all/', generate_date_patterns(list_views.all, name="all")),
    re_path(r'^allfuture/', generate_date_patterns(list_views.allfuture, name="allfuture")),

    # calendar views corresponding to the list views
    re_path(r'^findchief/calendar/', generate_date_patterns(list_views.findchief_cal, name="findchief-cal")),
    re_path(r'^prerequest/calendar/', generate_date_patterns(list_views.prerequest_cal, name="prerequest-cal")),
    re_path(r'^prospective/calendar/', generate_date_patterns(list_views.prospective_cal, name="prospective-cal")),
    re_path(r'^incoming/calendar/', generate_date_patterns(list_views.incoming_cal, name="incoming-cal")),
    re_path(r'^confirmed/calendar/', generate_date_patterns(list_views.confirmed_cal, name="confirmed-cal")),
    re_path(r'^open/calendar/', generate_date_patterns(list_views.openworkorders_cal, name="open-cal")),
    re_path(r'^unreviewed/calendar/', generate_date_patterns(list_views.unreviewed_cal, name="unreviewed-cal")),
    re_path(r'^unbilled/calendar/', generate_date_patterns(list_views.unbilled_cal, name="unbilled-cal")),
    re_path(r'^unbilledsemester/calendar/', generate_date_patterns(list_views.unbilled_semester_cal,
                                                               name="unbilled-semester-cal")),
    re_path(r'^paid/calendar/', generate_date_patterns(list_views.paid_cal, name="paid-cal")),
    re_path(r'^unpaid/calendar/', generate_date_patterns(list_views.unpaid_cal, name="unpaid-cal")),
    re_path(r'^closed/calendar/', generate_date_patterns(list_views.closed_cal, name="closed-cal")),
    re_path(r'^all/calendar/', generate_date_patterns(list_views.all_cal, name="all-cal")),
    re_path(r'^allfuture/calendar/', generate_date_patterns(list_views.allfuture_cal, name="all-future-cal")),

    # Actual event pages

    re_path(r'^view/(?P<id>[0-9a-f]+)/$', flow_views.viewevent, name="detail"),
    re_path(r'^pdf/(?P<ids>\d+(,\d+)*)?/?$', pdf_views.generate_event_pdf_multi,
        name="pdf-multi"),
    re_path(r'^bills-pdf/(?P<ids>\d+(,\d+)*)?/?$', pdf_views.generate_event_bill_pdf_multi,
        name="bill-pdf-multi"),
    re_path(r'^view/(?P<id>[0-9a-f]+)/pdf/$', pdf_views.generate_event_pdf, name="pdf"),
    # re_path(r'^db/events/mk/$', 'events.views.mkedrm.eventnew', name="event-new"),
    re_path(r'^mk/$', mkedrm_views.eventnew, name="new"),
    re_path(r'^edit/(?P<id>[0-9a-f]+)/$', mkedrm_views.eventnew, name="edit"),
    re_path(r'^duplicate/(?P<id>[0-9a-f]+)/$', mkedrm_views.duplicate_event, name="duplicate"),
    re_path(r'^approve/(?P<id>[0-9a-f]+)/$', flow_views.approval, name="approve"),
    re_path(r'^deny/(?P<id>[0-9a-f]+)/$', flow_views.denial, name="deny"),
    re_path(r'^review/(?P<id>[0-9a-f]+)/$', flow_views.review, name="review"),
    re_path(r'^review/(?P<id>[0-9a-f]+)/remind/(?P<uid>[0-9a-f]+)/$',
        flow_views.reviewremind, name="remind"),
    re_path(r'^review/(?P<id>[0-9a-f]+)/remind/$', flow_views.remindall, name="remindall"),
    re_path(r'^close/(?P<id>[0-9a-f]+)/$', flow_views.close, name="close"),
    re_path(r'^cancel/(?P<id>[0-9a-f]+)/$', flow_views.cancel, name="cancel"),
    re_path(r'^reopen/(?P<id>[0-9a-f]+)/$', flow_views.reopen, name="reopen"),
    re_path(r'^crew/(?P<id>[0-9a-f]+)/$', flow_views.assigncrew, name="add-crew"),
    re_path(r'^rmcrew/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$',
        flow_views.rmcrew, name="remove-crew"),
    re_path(r'^(?P<id>[0-9]+)/hours/bulk/$', flow_views.hours_bulk_admin,
        name="add-bulk-crew"),
    re_path(r'^selfcrew/(?P<id>[0-9]+)/$', flow_views.hours_prefill_self, name="selfcrew"),
    re_path(r'^crewchief/(?P<id>[0-9a-f]+)/$', flow_views.assigncc, name="chiefs"),
    re_path(r'^rmcc/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$', flow_views.rmcc, name="remove-chief"),
    re_path(r'^attachments/(?P<id>[0-9a-f]+)/$', flow_views.assignattach, name="files"),
    re_path(r'^links/(?P<id>[0-9a-f]+)/$', flow_views.event_resources, name="resource-links"),
    re_path(r'^extras/(?P<id>[0-9a-f]+)/$', flow_views.extras, name="extras"),
    re_path(r'^oneoff/(?P<id>[0-9a-f]+)/$', flow_views.oneoff, name="oneoffs"),
    re_path(r'^enter-worktag/(?P<pk>[0-9a-f]+)/$', flow_views.WorkdayEntry.as_view(), name="worktag-form"),
    re_path(r'^workday-entered/(?P<id>[0-9a-f]+)/$', flow_views.mark_entered_into_workday, name="workday-entered"),

    re_path(r'^(?P<pk>[0-9a-f]+)/download/ics/$', flow_views.download_ics, name="ics"),

    # The nice url structure. TODO: fit the rest in here (with deprecation, of course)
    re_path(r'^view/(?P<event>[0-9]+)/', include([
        re_path(r'^billing/', view=include(([
            re_path(r'^mk/$', flow_views.BillingCreate.as_view(), name="new"),
            re_path(r'^update/(?P<pk>[0-9]+)/$', flow_views.BillingUpdate.as_view(),
                name="edit"),
            re_path(r'^email/(?P<billing>[0-9]+)/$', flow_views.BillingEmailCreate.as_view(),
                name="email"),
            re_path(r'^pay/(?P<pk>[0-9]+)/$', flow_views.pay_bill,
                name="pay"),
            re_path(r'^rm/(?P<pk>[0-9]+)/$', flow_views.BillingDelete.as_view(),
                name="remove"),
            re_path(r'^pdf/$', pdf_views.generate_event_bill_pdf, name="pdf"),
        ], 'lnldb'), namespace="bills")),
        re_path(r'^report/', view=include(([
            re_path(r'^mk/$', flow_views.CCRCreate.as_view(), name="new"),
            re_path(r'^update/(?P<pk>[0-9]+)/$', flow_views.CCRUpdate.as_view(), name="edit"),
            re_path(r'^rm/(?P<pk>[0-9]+)/$', flow_views.CCRDelete.as_view(), name="remove")
        ], 'lnldb'), namespace="reports")),
    ])),
    re_path(r'^multibills/', include(([
        re_path(r'^$', list_views.multibillings, name="list"),
        re_path(r'^mk/$', flow_views.MultiBillingCreate.as_view(), name="new"),
        re_path(r'^update/(?P<pk>[0-9]+)/$', flow_views.MultiBillingUpdate.as_view(), name="edit"),
        re_path(r'^rm/(?P<pk>[0-9]+)/$', flow_views.MultiBillingDelete.as_view(), name="remove"),
        re_path(r'^email/(?P<multibilling>[0-9]+)/$', flow_views.MultiBillingEmailCreate.as_view(), name="email"),
        re_path(r'^pdf/(?P<multibilling>[0-9]+)/$', pdf_views.generate_multibill_pdf, name="pdf"),
    ], 'lnldb'), namespace="multibillings")),

    re_path(r'^workshops/', include(([
        re_path(r'^manage/$', list_views.workshops_list, name="list"),
        re_path(r'^(?P<pk>[0-9]+)/edit/$', list_views.edit_workshop, name="edit"),
        re_path(r'^(?P<pk>[0-9]+)/dates/$', list_views.workshop_dates, name="dates"),
        re_path(r'^new/$', list_views.new_workshop, name="add"),
        re_path(r'^rm/(?P<pk>[0-9]+)/$', list_views.DeleteWorkshop.as_view(), name="delete")
    ], 'lnldb'), namespace="workshops")),

    re_path(r'^crew/self-service/$', flow_views.crew_tracker, name="crew-tracker"),
    re_path(r'^crew/checkin/$', flow_views.checkin, name="crew-checkin"),
    re_path(r'^crew/checkout/$', flow_views.checkout, name="crew-checkout"),
    re_path(r'^crew/bulk/$', flow_views.bulk_checkin, name="crew-bulk"),
]

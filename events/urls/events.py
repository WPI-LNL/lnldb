from django.conf.urls import include, url

from ..views import list as list_views, flow as flow_views, mkedrm as mkedrm_views
from pdfs import views as pdf_views


def generate_date_patterns(func, name):
    return include([
        url(r'^$', func, name=name),
        url(r'^(?P<start>\d{4}-\d{2}-\d{2})/$', func, name=name),
        url(r'^(?P<start>\d{4}-\d{2}-\d{2})/(?P<end>\d{4}-\d{2}-\d{2})/$', func, name=name),
    ])


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
    url(r'^closed/', generate_date_patterns(list_views.closed, name="closed")),

    # Actual event pages

    url(r'^view/(?P<id>[0-9a-f]+)/$', flow_views.viewevent, name="detail"),
    url(r'^pdf/(?P<ids>\d+(,\d+)*)?/?$', pdf_views.generate_event_pdf_multi,
        name="pdf-multi"),
    url(r'^view/(?P<id>[0-9a-f]+)/pdf/$', pdf_views.generate_event_pdf, name="pdf"),
    # url(r'^db/events/mk/$', 'events.views.mkedrm.eventnew', name="event-new"),
    url(r'^mk/$', mkedrm_views.eventnew, name="new"),
    url(r'^edit/(?P<id>[0-9a-f]+)/$', mkedrm_views.eventnew, name="edit"),
    url(r'^approve/(?P<id>[0-9a-f]+)/$', flow_views.approval, name="approve"),
    url(r'^deny/(?P<id>[0-9a-f]+)/$', flow_views.denial, name="deny"),
    url(r'^review/(?P<id>[0-9a-f]+)/$', flow_views.review, name="review"),
    url(r'^review/(?P<id>[0-9a-f]+)/remind/(?P<uid>[0-9a-f]+)/$',
        flow_views.reviewremind, name="remind"),
    url(r'^close/(?P<id>[0-9a-f]+)/$', flow_views.close, name="close"),
    url(r'^cancel/(?P<id>[0-9a-f]+)/$', flow_views.cancel, name="cancel"),
    url(r'^reopen/(?P<id>[0-9a-f]+)/$', flow_views.reopen, name="reopen"),
    url(r'^crew/(?P<id>[0-9a-f]+)/$', flow_views.assigncrew, name="add-crew"),
    url(r'^rmcrew/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$',
        flow_views.rmcrew, name="remove-crew"),
    url(r'^(?P<id>[0-9]+)/hours/bulk/$', flow_views.hours_bulk_admin,
        name="add-bulk-crew"),
    url(r'^crewchief/(?P<id>[0-9a-f]+)/$', flow_views.assigncc, name="chiefs"),
    url(r'^rmcc/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$', flow_views.rmcc, name="remove-chief"),

    # The nice url structure. TODO: fit the rest in here (with deprecation, of course)
    url(r'^view/(?P<event>[0-9]+)/', include([
        url(r'^billing/', view=include([
            url(r'^mk/$', flow_views.BillingCreate.as_view(), name="new"),
            url(r'^update/(?P<pk>[0-9]+)/$', flow_views.BillingUpdate.as_view(),
                name="edit"),
            url(r'^rm/(?P<pk>[0-9]+)/$', flow_views.BillingDelete.as_view(),
                name="remove"),
            url(r'^pdf/$', pdf_views.generate_event_bill_pdf, name="pdf"),
        ], namespace="bills")),
        url(r'^report/', view=include([
            url(r'^mk/$', flow_views.CCRCreate.as_view(), name="new"),
            url(r'^update/(?P<pk>[0-9]+)/$', flow_views.CCRUpdate.as_view(),
                name="edit"),
            url(r'^rm/(?P<pk>[0-9]+)/$', flow_views.CCRDelete.as_view(), name="remove")
        ], namespace="reports")),
    ]))
]

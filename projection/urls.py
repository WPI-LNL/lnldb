from django.conf.urls import url

from pdfs import views as pdf_views

from . import views

app_name = 'projection'

urlpatterns = [
    url(r'^list/$', views.plist_detail, name="grid"),
    url(r'^list/other/$', views.plist, name="list"),
    url(r'^list/detail/pdf/$', pdf_views.generate_projection_pdf,
        name="pdf"),

    url(r'^mk/$', views.ProjectionCreate.as_view(), name="new"),
    url(r'^bulk/$', views.BulkUpdateView.as_view(), name="bulk-edit"),
    url(r'^update/(?P<id>[0-9a-f]+)/$', views.projection_update, name="edit"),
    url(r'^rm/(?P<pk>[0-9a-f]+)/$', views.ProjectionistDelete.as_view(), name="remove"),

    url(r'^bulkevents/$', views.bulk_projection, name="add-movies"),

    url(r'^training/request/$', views.PITRequest.as_view(), name="pit-request"),
    url(r'^training/schedule/$', views.pit_schedule, name="pit-schedule"),
    url(r'^training/(?P<id>[0-9a-f]+)/update/$', views.pit_request_update, name="edit-request"),
    url(r'^training/manage/(?P<id>[0-9a-f]+)/$', views.manage_pit_request, name="manage-request"),
    url(r'^training/(?P<pk>[0-9a-f]+)/cancel/$', views.CancelPITRequest.as_view(), name="cancel-request"),
]

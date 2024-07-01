from django.urls import re_path

from pdfs import views as pdf_views

from . import views

app_name = 'projection'

urlpatterns = [
    re_path(r'^list/$', views.plist_detail, name="grid"),
    re_path(r'^list/other/$', views.plist, name="list"),
    re_path(r'^list/detail/pdf/$', pdf_views.generate_projection_pdf,
        name="pdf"),

    re_path(r'^mk/$', views.ProjectionCreate.as_view(), name="new"),
    re_path(r'^bulk/$', views.BulkUpdateView.as_view(), name="bulk-edit"),
    re_path(r'^update/(?P<id>[0-9a-f]+)/$', views.projection_update, name="edit"),
    re_path(r'^rm/(?P<pk>[0-9a-f]+)/$', views.ProjectionistDelete.as_view(), name="remove"),

    re_path(r'^bulkevents/$', views.bulk_projection, name="add-movies"),

    re_path(r'^training/request/$', views.PITRequest.as_view(), name="pit-request"),
    re_path(r'^training/schedule/$', views.pit_schedule, name="pit-schedule"),
    re_path(r'^training/(?P<id>[0-9a-f]+)/update/$', views.pit_request_update, name="edit-request"),
    re_path(r'^training/manage/(?P<id>[0-9a-f]+)/$', views.manage_pit_request, name="manage-request"),
    re_path(r'^training/(?P<pk>[0-9a-f]+)/cancel/$', views.CancelPITRequest.as_view(), name="cancel-request"),
    re_path(r'^training/(?P<id>[0-9a-f]+)/done/$', views.pit_complete, name="pit-complete")
]

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
]

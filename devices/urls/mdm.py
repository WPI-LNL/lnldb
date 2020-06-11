from django.conf.urls import url

from .. import views

app_name = 'mdm'

urlpatterns = [
    url(r'^$', views.mdm_list, name='list'),
    url(r'^enroll/$', views.mdm_enroll, name='start-enrollment'),
    url(r'^enrollment/(?P<pk>[0-9]+)/$', views.complete_enrollment, name="enroll"),
    url(r'^client/$', views.install_client, name="install-client"),
    url(r'^devices/(?P<pk>[0-9]+)/rm/$', views.remove_device, name="remove"),
]

from django.conf.urls import url

from .. import views

app_name = 'mdm'

urlpatterns = [
    url(r'^$', views.mdm_list, name='list'),
    url(r'^enroll/$', views.mdm_enroll, name='start-enrollment'),
    url(r'^enrollment/(?P<pk>[0-9]+)/$', views.complete_enrollment, name="enroll"),
    url(r'^checkin/$', views.mdm_checkin, name='checkin'),
    url(r'^confirm-install/$', views.install_confirmation, name="confirm-install"),
    url(r'^profiles/$', views.list_profiles, name="profiles"),
    url(r'^profile/(?P<profile_id>[0-9]+)/install/$', views.mobile_config, name='install'),
    url(r'^profile/(?P<profile_id>[0-9]+)/uninstall/$', views.mobile_config, {'action': 'Uninstall'}, name='uninstall'),
    url(r'^profile/(?P<pk>[0-9]+)/edit/$', views.generate_profile, name="edit"),
    url(r'^profile/(?P<profile>[0-9]+)/rm/$', views.remove_profile, name='delete'),
    url(r'^profile/(?P<pk>[0-9]+)/devices/$', views.profile_devices, name="assignments"),
    url(r'^profile/(?P<profile>[0-9]+)/devices/add/$', views.link_profiles, name="profile-add-devices"),
    url(r'^profile/generate/$', views.generate_profile, name='generate'),
    url(r'^profile/password/$', views.removal_password, name='password'),
    url(r'^client/$', views.install_client, name="install-client"),
    url(r'^devices/(?P<pk>[0-9]+)/rm/$', views.remove_device, name="remove"),
    url(r'^devices/(?P<pk>[0-9]+)/profiles/$', views.list_profiles, name="device-profiles"),
    url(r'^devices/(?P<device>[0-9]+)/profiles/add/$', views.link_profiles, name="add-profiles"),
    url(r'^devices/(?P<device>[0-9]+)/rm-profile/(?P<profile>[0-9]+)/$', views.remove_profile, name="disassociate")
]

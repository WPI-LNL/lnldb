from django.urls import re_path

from .. import views

app_name = 'mdm'

urlpatterns = [
    re_path(r'^$', views.mdm_list, name='list'),
    re_path(r'^enroll/$', views.mdm_enroll, name='start-enrollment'),
    re_path(r'^enrollment/(?P<pk>[0-9]+)/$', views.complete_enrollment, name="enroll"),
    re_path(r'^checkin/$', views.mdm_checkin, name='checkin'),
    re_path(r'^confirm-install/$', views.install_confirmation, name="confirm-install"),
    re_path(r'^apps/$', views.list_apps, name="apps"),
    re_path(r'^apps/list/$', views.app_list, name='app-list'),
    re_path(r'^apps/new/$', views.add_app, name="add-app"),
    re_path(r'^app/(?P<pk>[0-9]+)/$', views.view_app, name="app-detail"),
    re_path(r'^app/(?P<pk>[0-9]+)/edit/$', views.update_app_info, name="edit-app"),
    re_path(r'^app/(?P<pk>[0-9]+)/refresh/$', views.reload_from_munki, name="app-refresh"),
    re_path(r'^app/(?P<pk>[0-9]+)/merge/$', views.merge_app, name="merge-app"),
    re_path(r'^app/(?P<app>[0-9]+)/rm/$', views.remove_app, name="remove-app"),
    re_path(r'^app/(?P<pk>[0-9]+)/devices/$', views.list_app_devices, name="app-devices"),
    re_path(r'^app/(?P<app>[0-9]+)/devices/add/$', views.link_apps, name="app-link-devices"),
    re_path(r'^profiles/$', views.list_profiles, name="profiles"),
    re_path(r'^profile/(?P<profile_id>[0-9]+)/install/$', views.mobile_config, name='install'),
    re_path(r'^profile/(?P<profile_id>[0-9]+)/uninstall/$', views.mobile_config, {'action': 'Uninstall'}, name='uninstall'),
    re_path(r'^profile/(?P<pk>[0-9]+)/edit/$', views.generate_profile, name="edit"),
    re_path(r'^profile/(?P<profile>[0-9]+)/rm/$', views.remove_profile, name='delete'),
    re_path(r'^profile/(?P<pk>[0-9]+)/devices/$', views.profile_devices, name="assignments"),
    re_path(r'^profile/(?P<profile>[0-9]+)/devices/add/$', views.link_profiles, name="profile-add-devices"),
    re_path(r'^profile/generate/$', views.generate_profile, name='generate'),
    re_path(r'^profile/password/$', views.removal_password, name='password'),
    re_path(r'^client/$', views.install_client, name="install-client"),
    re_path(r'^devices/(?P<pk>[0-9]+)/rm/$', views.remove_device, name="remove"),
    re_path(r'^devices/(?P<pk>[0-9]+)/apps/$', views.list_apps, name="device-apps"),
    re_path(r'^devices/(?P<pk>[0-9]+)/profiles/$', views.list_profiles, name="device-profiles"),
    re_path(r'^devices/(?P<device>[0-9]+)/apps/add/$', views.link_apps, name="assign-apps"),
    re_path(r'^devices/(?P<device>[0-9]+)/profiles/add/$', views.link_profiles, name="add-profiles"),
    re_path(r'^devices/(?P<device>[0-9]+)/rm-app/(?P<app>[0-9]+)/$', views.remove_app, name="uninstall-app"),
    re_path(r'^devices/(?P<device>[0-9]+)/rm-profile/(?P<profile>[0-9]+)/$', views.remove_profile, name="disassociate"),
    re_path(r'^logs/$', views.logs, name="install-logs")
]

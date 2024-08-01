from django.urls import re_path

from .. import views

app_name = 'laptops'

urlpatterns = [
    re_path(r'^$', views.laptops_list, name='list'),
    re_path(r'^history/(?P<id>[0-9]+)/$', views.laptop_history, name='history'),
    re_path(r'^password/(?P<id>[0-9]+)/$', views.laptop_user_password, name='user-password'),
    re_path(r'^admin-password/(?P<id>[0-9]+)/$', views.laptop_admin_password, name='admin-password'),
    re_path(r'^rotate-passwords/$', views.rotate_passwords, name='rotate-passwords'),
]

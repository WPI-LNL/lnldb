from django.conf.urls import url

from .. import views

app_name = 'laptops'

urlpatterns = [
    url(r'^$', views.laptops_list, name='list'),
    url(r'^history/(?P<id>[0-9]+)/$', views.laptop_history, name='history'),
    url(r'^password/(?P<id>[0-9]+)/$', views.laptop_user_password, name='user-password'),
    url(r'^admin-password/(?P<id>[0-9]+)/$', views.laptop_admin_password, name='admin-password'),
    url(r'^rotate-passwords/$', views.rotate_passwords, name='rotate-passwords'),
]

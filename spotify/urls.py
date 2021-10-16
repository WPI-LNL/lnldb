from django.conf.urls import url

from . import views

app_name = 'spotify'

urlpatterns = [
    url(r'^auth/signin/$', views.auth, name="signin"),
    url(r'^auth/callback/$', views.auth_callback, name="callback"),
    url(r'^auth/refresh/$', views.refresh_token, name="refresh"),
    url(r'^auth/token/$', views.obtain_token, name="auth"),
    url(r'^request/$', views.song_request, name="request"),
    url(r'^session/(?P<session>[0-9a-f]+)/manager/$', views.queue_manager, name="list"),
    url(r'^approve/(?P<pk>[0-9a-f]+)/$', views.approve_request, name="approve-request"),
    url(r'^cancel/(?P<pk>[0-9a-f]+)/$', views.cancel_request, name="cancel-request"),
    url(r'^paid/(?P<pk>[0-9a-f]+)/$', views.paid, name="mark-paid")
]

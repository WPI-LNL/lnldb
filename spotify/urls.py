from django.urls import re_path

from . import views

app_name = 'spotify'

urlpatterns = [
    re_path(r'^auth/signin/$', views.login, name="signin"),
    re_path(r'^auth/callback/$', views.auth_callback, name="callback"),
    re_path(r'^request/(?P<session_id>.+)/$', views.song_request, name="request"),
    re_path(r'^payment/(?P<session_id>[0-9a-f]+)/$', views.pay_fee, name="payment"),
    re_path(r'^event/(?P<event_id>[0-9a-f]+)/session/$', views.configure_session, name="event-session"),
    re_path(r'^session/(?P<session>[0-9a-f]+)/manage/$', views.queue_manager, name="list"),
    re_path(r'^session/(?P<session_id>[0-9a-f]+)/qr-code/$', views.generate_qr_code, name="qr"),
    re_path(r'^approve/(?P<pk>[0-9a-f]+)/$', views.approve_request, name="approve-request"),
    re_path(r'^cancel/(?P<pk>[0-9a-f]+)/$', views.cancel_request, name="cancel-request"),
    re_path(r'^paid/(?P<pk>[0-9a-f]+)/$', views.paid, name="mark-paid"),
    re_path(r'^queue/(?P<pk>[0-9a-f]+)/$', views.queue_song, name="queue")
]

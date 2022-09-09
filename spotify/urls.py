from django.conf.urls import url

from . import views

app_name = 'spotify'

urlpatterns = [
    url(r'^auth/signin/$', views.login, name="signin"),
    url(r'^auth/callback/$', views.auth_callback, name="callback"),
    url(r'^request/(?P<session_id>.+)/$', views.song_request, name="request"),
    url(r'^payment/(?P<session_id>[0-9a-f]+)/$', views.pay_fee, name="payment"),
    url(r'^event/(?P<event_id>[0-9a-f]+)/session/$', views.configure_session, name="event-session"),
    url(r'^session/(?P<session>[0-9a-f]+)/manage/$', views.queue_manager, name="list"),
    url(r'^session/(?P<session_id>[0-9a-f]+)/qr-code/$', views.generate_qr_code, name="qr"),
    url(r'^approve/(?P<pk>[0-9a-f]+)/$', views.approve_request, name="approve-request"),
    url(r'^cancel/(?P<pk>[0-9a-f]+)/$', views.cancel_request, name="cancel-request"),
    url(r'^paid/(?P<pk>[0-9a-f]+)/$', views.paid, name="mark-paid"),
    url(r'^queue/(?P<pk>[0-9a-f]+)/$', views.queue_song, name="queue")
]

from django.conf.urls import include
from django.urls import re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from . import views
from .routers import ReadOnlyRouter, WriteOnlyRouter, SpotifyRouter

router = ReadOnlyRouter()
router.register(r'officers', views.OfficerViewSet, basename='Officer')
router.register(r'office-hours', views.HourViewSet, basename='Hour')
router.register(r'notifications', views.NotificationViewSet, basename='Notification')
router.register(r'events', views.EventViewSet, basename="Event")
router.register(r'sitemap', views.SitemapViewSet, basename='Sitemap')

write_router = WriteOnlyRouter()
write_router.register(r'crew', views.AttendanceViewSet, basename="Crew")

spotify_router = SpotifyRouter()
spotify_router.register(r'sessions', views.SpotifySessionViewSet, basename="Spotify Session")
spotify_router.register(r'users', views.SpotifyUserViewSet, basename="Spotify User")
spotify_router.register(r'requests', views.SongRequestViewSet, basename="Song Request")

urlpatterns = [
    re_path(r'v1/', include(router.urls)),
    re_path(r'v1/', include(write_router.urls)),
    re_path(r'v1/spotify/', include(spotify_router.urls)),
    re_path(r'^token/request/(?P<client_id>.+)/$', views.request_token, name="request-token"),
    re_path(r'^token/fetch/$', views.fetch_token, name="fetch-token"),
    re_path(r'^schema/$', SpectacularAPIView.as_view(), name="schema"),
    re_path(r'^schema/swagger/$', SpectacularSwaggerView.as_view(url_name='api:schema'), name='swagger')
]

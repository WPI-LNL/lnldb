from django.conf.urls import include, url
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from . import views
from .routers import ReadOnlyRouter, WriteOnlyRouter, SpotifyRouter
from rest_framework import routers

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

sats_router = routers.DefaultRouter()
sats_router.register('assets', views.AssetViewSet, basename="Assets")
sats_router.register('asset-events', views.AssetEventViewSet, basename="Asset Events")

urlpatterns = [
    url(r'v1/', include(router.urls)),
    url(r'v1/', include(write_router.urls)),
    url(r'v1/spotify/', include(spotify_router.urls)),
    url(r'v1/sats', include(sats_router.urls)),
    url(r'^token/request/(?P<client_id>.+)/$', views.request_token, name="request-token"),
    url(r'^token/fetch/$', views.fetch_token, name="fetch-token"),
    url(r'^schema/$', SpectacularAPIView.as_view(), name="schema"),
    url(r'^schema/swagger/$', SpectacularSwaggerView.as_view(url_name='api:schema'), name='swagger')
]

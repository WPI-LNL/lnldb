from django.conf.urls import include, url
from . import views
from .routers import ReadOnlyRouter, WriteOnlyRouter

router = ReadOnlyRouter()
router.register(r'officers', views.OfficerViewSet, basename='Officer')
router.register(r'office-hours', views.HourViewSet, basename='Hour')
router.register(r'notifications', views.NotificationViewSet, basename='Notification')
router.register(r'events', views.EventViewSet, basename="Event")
router.register(r'sitemap', views.SitemapViewSet, basename='Sitemap')

write_router = WriteOnlyRouter()
write_router.register(r'crew', views.AttendanceViewSet, basename="Crew")

urlpatterns = [
    url(r'v1/', include(router.urls)),
    url(r'v1/', include(write_router.urls)),
    url(r'^docs/$', views.docs, name="documentation"),
    url(r'^token/request/$', views.request_token, name="request-token"),
    url(r'^token/fetch/$', views.fetch_token, name="fetch-token"),
]

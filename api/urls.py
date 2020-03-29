from django.conf.urls import include, url
from . import views
from .routers import ReadOnlyRouter

router = ReadOnlyRouter()
router.register(r'officers', views.OfficerViewSet, basename='Officer')
router.register(r'office-hours', views.HourViewSet, basename='Hour')
router.register(r'hours/updates', views.ChangeViewSet, basename='Change')
router.register(r'notifications', views.NotificationViewSet, basename='Notification')

urlpatterns = [
    url(r'v1/', include(router.urls)),
    url(r'^docs/$', views.docs, name="api-documentation"),
]

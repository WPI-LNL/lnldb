from django.urls import path

from . import views

app_name="positions"

urlpatterns = [
        path('create/', views.CreatePosition.as_view(), name="create"),
        path('list/', views.ListPositions.as_view(), name="list"),
        path('detail/<int:pk>', views.ViewPosition.as_view(), name="detail"),
        ]

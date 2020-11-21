from django.conf.urls import include, url

from . import views

urlpatterns = [
    url(r'^db/members/training/', include(([
        url(r'^list/$', views.training_list, name="list"),
        url(r'^enter/$', views.enter_training, name="entry"),
        url(r'^notes/(?P<pk>[0-9]+)/$', views.trainee_notes, name="traineenotes"),
        url(r'^revoke/(?P<pk>[0-9]+)/$', views.revoke_training, name="revoke"),
    ], 'members'), namespace="training")),
]

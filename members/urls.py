from django.conf.urls import include
from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r'^db/members/training/', include(([
        re_path(r'^list/$', views.training_list_active_only, name="list"),
        re_path(r'^listall/$', views.training_list_all, name="listall"),
        re_path(r'^enter/$', views.enter_training, name="entry"),
        re_path(r'^notes/(?P<pk>[0-9]+)/$', views.trainee_notes, name="traineenotes"),
        re_path(r'^revoke/(?P<pk>[0-9]+)/$', views.revoke_training, name="revoke"),
    ], 'members'), namespace="training")),
]

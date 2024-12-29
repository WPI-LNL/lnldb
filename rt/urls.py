from django.conf.urls import include
from django.urls import re_path
from . import views


app_name = "RT"

urlpatterns = [
    re_path(r'^tickets/', include([
        re_path(r'^new/$', views.new_ticket, name="new-ticket"),
    ])),
    re_path(r'^connect/rt/$', views.link_account, name="link-account")
]

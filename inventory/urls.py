from django.conf.urls import include
from django.urls import re_path

from . import views

app_name = 'inventory'

# Inventory Url Patterns
# Use include() liberally. A bit harder to read,
#   but encourages consistency and you never
#   have to rewrite a regex.
urlpatterns = [
    re_path(r'^$', views.view_all, name='view_all'),

    re_path(r'^cat/(?P<category_id>[0-9]+)/', include([
        re_path(r'^$', views.cat, name="cat"),
    ])),

    re_path(r'^class/(?P<type_id>[0-9]+)/', include([
        re_path(r'^$', views.type_detail, name="type_detail"),
    ])),

    re_path(r'^item/(?P<item_id>[0-9]+)/', include([
        re_path(r'^$', views.item_detail, name="item_detail"),
    ])),

    re_path(r'^checkout/$', views.snipe_checkout, name="snipe_checkout"),
    re_path(r'^checkin/$', views.snipe_checkin, name="snipe_checkin"),
    re_path(r'^checkout/legacy/$', views.old_snipe_checkout, name="legacy_checkout"),
    re_path(r'^checkin/legacy/$', views.old_snipe_checkin, name="legacy_checkin"),
    re_path(r'^snipe/$', views.snipe_credentials, name="snipe_password"),

]

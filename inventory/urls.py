from django.conf.urls import include, url

from . import views

app_name = 'inventory'

# Inventory Url Patterns
# Use include() liberally. A bit harder to read,
#   but encourages consistency and you never
#   have to rewrite a regex.
urlpatterns = [
    url(r'^$', views.view_all, name='view_all'),

    url(r'^cat/(?P<category_id>[0-9]+)/', include([
        url(r'^$', views.cat, name="cat"),
    ])),

    url(r'^class/(?P<type_id>[0-9]+)/', include([
        url(r'^$', views.type_detail, name="type_detail"),
    ])),

    url(r'^item/(?P<item_id>[0-9]+)/', include([
        url(r'^$', views.item_detail, name="item_detail"),
    ])),

    url(r'^checkout/$', views.snipe_checkout, name="snipe_checkout"),
    url(r'^checkin/$', views.snipe_checkin, name="snipe_checkin"),
    url(r'^checkout/legacy/$', views.old_snipe_checkout, name="legacy_checkout"),
    url(r'^checkin/legacy/$', views.old_snipe_checkin, name="legacy_checkin"),
    url(r'^snipe/$', views.snipe_credentials, name="snipe_password"),

]

from django.conf.urls import include, url

from . import views

# Inventory Url Patterns
# Use include() liberally. A bit harder to read,
#   but encourages consistency and you never
#   have to rewrite a regex.
urlpatterns = [
    url(r'^$', views.view_all, name='view_all'),

    url(r'^new/$', views.fast_mk, name="fast_mk"),

    url(r'^cat/mk/$', views.cat_mk, name="cat_mk"),
    url(r'^cat/(?P<category_id>[0-9]+)/', include([
        url(r'^$', views.cat, name="cat"),
        url(r'edit/$', views.cat_edit, name="cat_edit"),
        url(r'rm/$', views.cat_rm, name="cat_rm"),
    ])),

    url(r'^class/new/$', views.type_mk, name="type_mk"),
    url(r'^class/(?P<type_id>[0-9]+)/', include([
        url(r'^$', views.type_detail, name="type_detail"),
        url(r'^edit/$', views.type_edit, name="type_edit"),
        url(r'^rm/$', views.type_rm, name="type_rm"),
        url(r'^add/bulk/$', views.quick_bulk_add, name="bulk_add"),
        url(r'^edit/bulk/$', views.quick_bulk_edit, name="bulk_edit"),
    ])),

    url(r'^item/(?P<item_id>[0-9]+)/', include([
        url(r'^$', views.item_detail, name="item_detail"),
        url(r'^edit/$', views.item_edit, name="item_edit"),
        url(r'^rm/$', views.item_rm, name="item_rm"),
        # url(r'^ticket/$', views.ticket_add, name='ticket_add')
    ])),

    # url(r'^tickets/', include([
    #     url(r'^(?P<ticket_id>[0-9]+)/', include([
    #         url(r'^$', views.ticket_view, name='ticket_detail'),
    #         url(r'^edit/$', views.ticket_edit, name='ticket_edit'),
    #     ]))
    # ]))

]

from django.conf.urls import include, url

from .. import views

# prefix: /my/
urlpatterns = [
    url(r'^workorders/$', views.my.mywo, name="workorders"),
    url(r'^workorders/attach/(?P<id>[0-9]+)/$', views.flow.assignattach_external, name="event-attach"),

    url(r'^orgs/', include([
        url(r'^$', views.my.myorgs, name="orgs"),
        url(r'^form/$', views.my.myorgform, name="org-request"),
        url(r'^(?P<id>[0-9a-f]+)/$', views.orgs.orgedit, name="org-edit"),
    ])),

]

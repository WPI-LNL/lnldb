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
        url(r'^transfer/(?P<id>[0-9]+)/$', views.orgs.org_mkxfer, name="org-transfer"),
        # ..... TODO: don't guess whether we're transfering or accepting
        url(r'^transfer/(?P<idstr>[0-9a-f]+)/$', views.orgs.org_acceptxfer,
            name="org-accept"),
    ])),

    url(r'^events/', include([
        url(r'^$', views.my.myevents, name="events"),
    ]))

]

from .. import views
from django.conf.urls import url, include

#prefix: /my/
urlpatterns = [
   url(r'^workorders/$', views.my.mywo, name="workorders"),
   url(r'^workorders/attach/(?P<id>[0-9]+)/$', views.flow.assignattach_external, name="event-attach"),

   url(r'^orgs/', include([
       url(r'^$', views.my.myorgs, name="orgs"),
   ])),

]

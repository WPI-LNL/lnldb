from django.conf.urls import include, url
from .. import views

urlpatterns = [
   url(r'^$', views.orgs.vieworgs, name="list"),
   url(r'^add/$', views.orgs.addeditorgs, name="add"),
   url(r'^(?P<org_id>[0-9]+)/$', include([
       url(r'^$', views.orgs.orgdetail, name="detail"),
   ])),


]

from .. import views
from django.conf.urls import url, include

#prefix: /my/
urlpatterns = [
   url(r'^workorders/$', views.my.mywo, name="workorders"),

]

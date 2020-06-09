from django.conf.urls import url

from .. import views

app_name = 'mdm'

urlpatterns = [
    url(r'^$', views.mdm_list, name='list'),
]

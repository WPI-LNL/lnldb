from django.conf.urls import url

from . import views

urlpatterns = [
    url(r'^me/', views.MeDirectView.as_view(permanent=False, pattern_name='accounts:detail')),
    url(r'^my/', views.MeDirectView.as_view(permanent=False, pattern_name='accounts:detail')),

    url(r'^db/members/add', views.UserAddView.as_view(), name='add'),
    url(r'^db/members/officers/$', views.OfficerList.as_view(), name='officers'),
    url(r'^db/members/active/$', views.ActiveList.as_view(), name='active'),
    url(r'^db/members/associate/$', views.AssociateList.as_view(), name='associate'),
    url(r'^db/members/alum/$', views.AlumniList.as_view(), name='alumni'),
    url(r'^db/members/away/$', views.AwayList.as_view(), name='away'),
    url(r'^db/members/inactive/$', views.InactiveList.as_view(), name='inactive'),
    url(r'^db/members/unsorted/$', views.LimboList.as_view(), name="limbo"),

    url(r'^list/mdc/raw/$', views.mdc_raw, name='mdc_raw'),
    url(r'^list/mdc/$', views.mdc, name='mdc'),

    url(r'^db/members/(?P<pk>[0-9a-f]+)/edit/$', views.UserUpdateView.as_view(), name="update"),
    url(r'^db/members/(?P<pk>[0-9a-f]+)/set_password/$', views.PasswordSetView.as_view(), name="password"),
    url(r'^db/members/(?P<pk>[0-9a-f]+)/detail/$', views.UserDetailView.as_view(), name="detail"),
]

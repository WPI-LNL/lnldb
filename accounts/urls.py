from django.conf import settings
from django.conf.urls import include, url
from django.contrib.auth import views as auth_views

import django_cas_ng.views

from . import views, forms

each_member_pattern = [
    url(r'^edit/$', views.UserUpdateView.as_view(), name="update"),
    url(r'^detail/$', views.UserDetailView.as_view(), name="detail"),
]

# Usually use CAS for logout, since it's guaranteed to log the user out
#  (without immediately signing them back in), and will ignore our
#  local users.
# But when we're doing development, we can't use cas, as there's 
#  no server to send login info to.
if settings.CAS_SERVER_URL:
    best_logout_url = url(r'^logout/$', django_cas_ng.views.logout, name="logout")
else:
    best_logout_url = url(r'^logout/$', auth_views.logout, {'template_name': 'registration/logout.html'},
            name="logout")

urlpatterns = [
    url(r'^me/$', views.MeDirectView.as_view(permanent=False, pattern_name='accounts:detail'), name="me"),
    url(r'^my/$', views.MeDirectView.as_view(permanent=False, pattern_name='accounts:detail')),

    url(r'^db/members/add/$', views.UserAddView.as_view(), name='add'),
    url(r'^db/members/officers/$', views.OfficerList.as_view(), name='officers'),
    url(r'^db/members/active/$', views.ActiveList.as_view(), name='active'),
    url(r'^db/members/associate/$', views.AssociateList.as_view(), name='associate'),
    url(r'^db/members/alum/$', views.AlumniList.as_view(), name='alumni'),
    url(r'^db/members/away/$', views.AwayList.as_view(), name='away'),
    url(r'^db/members/inactive/$', views.InactiveList.as_view(), name='inactive'),
    url(r'^db/members/unsorted/$', views.LimboList.as_view(), name="limbo"),

    url(r'^list/mdc/raw/$', views.mdc_raw, name='mdc_raw'),
    url(r'^list/mdc/$', views.mdc, name='mdc'),
    url(r'^db/members/(?P<pk>[0-9]+)/set_password/$', views.PasswordSetView.as_view(), name="password"),

    url(r'^db/members/(?P<pk>[0-9]+)/', include(each_member_pattern)),
    url(r'^db/members/(?P<username>[A-Za-z][A-Za-z0-9]*)/', include(each_member_pattern, namespace='by-name')),

    # AUTH
    # use the nice redirector for login
    url(r'^login/$', views.smart_login, name="login"),
    best_logout_url,

    # now for logical separation of the two auth portals
    url(r'^cas/', include([
        url(r'^login/$', django_cas_ng.views.login, name="login"),
        url(r'^logout/$', django_cas_ng.views.logout, name="logout"),
    ], namespace="cas")),

    url(r'^local/', include([
        url(r'^login/$', auth_views.login,
            {'template_name': 'registration/login.html',
             'authentication_form': forms.LoginForm},
            name="login"),

        url(r'^logout/$', auth_views.logout,
            {'template_name': 'registration/logout.html'},
            name="logout"),
    ], namespace="local")),

    # and keep password resets separate from either (though technically local)
    url(r'^local/reset/', include([
        url(r'^$', auth_views.password_reset,
            {'template_name': 'registration/reset_password.html',
             'post_reset_redirect': 'accounts:reset:sent',
             'from_email': settings.DEFAULT_FROM_ADDR},
            name='start'),
        url(r'^confirm/(?P<uidb64>[0-9A-Za-z]+)-(?P<token>.+)/$',
            auth_views.password_reset_confirm,
            {'template_name': 'registration/reset_password_form.html'},
            name='confirm'),
        url(r'^sent/$', auth_views.password_reset_done,
            {'template_name': 'registration/reset_password_sent.html'},
            name='sent'),
        url(r'^done/$', auth_views.password_reset_complete,
            {'template_name': 'registration/reset_password_finished.html'},
            name='done'),
    ], namespace="reset")),

]

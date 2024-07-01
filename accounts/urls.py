from django.conf import settings
from django.conf.urls import include
from django.urls import re_path
from django.contrib.auth import views as auth_views
from django.urls.base import reverse_lazy
from django_saml2_auth.views import signout as saml_logout

from . import views, forms

app_name = 'accounts'

each_member_pattern = [
    re_path(r'^edit/$', views.UserUpdateView.as_view(), name="update"),
    re_path(r'^detail/$', views.UserDetailView.as_view(), name="detail"),
]

# Usually use Microsoft SSO for logout, since it's guaranteed to log the user out
#  (without immediately signing them back in), and will ignore our
#  local users.
# But when we're doing development, we can't use SSO, as there's
#  no server to send login info to.
if settings.SAML2_ENABLED:
    best_logout_url = re_path(r'^logout/$', saml_logout, name="logout")
else:
    best_logout_url = re_path(r'^logout/$', auth_views.LogoutView.as_view(template_name='registration/logout.html'),
                          name="logout")

urlpatterns = [
    re_path(r'^me/$', views.MeDirectView.as_view(permanent=False, pattern_name='accounts:detail'), name="me"),
    re_path(r'^my/$', views.MeDirectView.as_view(permanent=False, pattern_name='accounts:detail')),
    re_path(r'^my/preferences/$', views.user_preferences, name='preferences'),
    re_path(r'^my/profile/photo/$', views.officer_photos, name='photo'),
    re_path(r'^auth/scopes/$', views.application_scope_request, name='scope-request'),

    re_path(r'^db/members/add/$', views.UserAddView.as_view(), name='add'),
    re_path(r'^db/members/officers/$', views.OfficerList.as_view(), name='officers'),
    re_path(r'^db/members/active/$', views.ActiveList.as_view(), name='active'),
    re_path(r'^db/members/associate/$', views.AssociateList.as_view(), name='associate'),
    re_path(r'^db/members/alum/$', views.AlumniList.as_view(), name='alumni'),
    re_path(r'^db/members/away/$', views.AwayList.as_view(), name='away'),
    re_path(r'^db/members/inactive/$', views.InactiveList.as_view(), name='inactive'),
    re_path(r'^db/members/all/$', views.AllMembersList.as_view(), name="allmembers"),
    re_path(r'^db/members/unsorted/$', views.LimboList.as_view(), name="limbo"),

    re_path(r'^db/members/mdc/raw/$', views.mdc_raw, name='mdc_raw'),
    re_path(r'^db/members/mdc/$', views.mdc, name='mdc'),
    re_path(r'^db/members/secretary/$', views.secretary_dashboard, name='secretary_dashboard'),
    re_path(r'^db/members/shame/$', views.shame, name='shame'),
    re_path(r'^db/members/(?P<pk>[0-9]+)/set_password/$', views.PasswordSetView.as_view(), name="password"),

    re_path(r'^db/members/(?P<pk>[0-9]+)/', include(each_member_pattern)),
    re_path(r'^db/members/(?P<pk>[0-9]+)/profile/photo/$', views.officer_photos, name="officer-photo"),
    re_path(r'^db/members/(?P<username>[A-Za-z][A-Za-z0-9]*)/',
        include((each_member_pattern, 'accounts'), namespace='by-name')),

    # AUTH
    # use the nice redirector for login
    re_path(r'^login/$', views.smart_login, name="login"),
    best_logout_url,

    # now for logical separation of the two auth portals
    # re_path(r'^cas/', include(([
    #     re_path(r'^login/$', django_cas_ng.views.login, name="login"),
    #     re_path(r'^logout/$', django_cas_ng.views.logout, name="logout"),
    # ], 'accounts'), namespace="cas")),

    re_path(r'^local/', include(([
        re_path(r'^login/$', auth_views.LoginView.as_view(template_name='registration/login.html',
                                                      authentication_form=forms.LoginForm), name="login"),

        re_path(r'^logout/$', auth_views.LogoutView.as_view(template_name='registration/logout.html'), name="logout"),
    ], 'accounts'), namespace="local")),

    # and keep password resets separate from either (though technically local)
    re_path(r'^local/reset/', include(([
        re_path(r'^$', auth_views.PasswordResetView.as_view(
            success_url=reverse_lazy('accounts:reset:sent'),
            from_email=settings.DEFAULT_FROM_ADDR,
            email_template_name='registration/password_reset_email.txt'
        ), {'template_name': 'registration/reset_password.html'}, name='start'),

        re_path(r'^confirm/(?P<uidb64>[0-9A-Za-z]+)-(?P<token>.+)/$', auth_views.PasswordResetConfirmView.as_view(
            success_url=reverse_lazy('accounts:reset:done')),
            {'template_name': 'registration/reset_password_form.html'}, name='confirm'),

        re_path(r'^sent/$', auth_views.PasswordResetDoneView.as_view(),
            {'template_name': 'registration/reset_password_sent.html'}, name='sent'),

        re_path(r'^done/$', auth_views.PasswordResetCompleteView.as_view(),
            {'template_name': 'registration/reset_password_finished.html'}, name='done'),
    ], 'accounts'), namespace="reset")),

]

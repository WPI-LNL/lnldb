from django.urls import re_path
from . import views

app_name = 'pages'

urlpatterns = [
    # join page moved to the static site
    #re_path(r'^join/$', views.recruitment_page, name='recruitment-page'),
    re_path(r'^onboarding/$', views.new_member_welcome, name="new-member"),
    re_path(r'^onboarding/wizard/$', views.OnboardingWizard.as_view(), name="onboarding-wizard"),
    re_path(r'^onboarding/(?P<slug>[-\w]+)/$', views.onboarding_screen, name="onboarding-screen"),
]

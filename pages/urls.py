from django.conf.urls import url
from . import views

app_name = 'pages'

urlpatterns = [
    url(r'^join/$', views.recruitment_page, name='recruitment-page'),
    url(r'^onboarding/$', views.new_member_welcome, name="new-member"),
    url(r'^onboarding/wizard/$', views.OnboardingWizard.as_view(), name="onboarding-wizard"),
    url(r'^onboarding/(?P<slug>[-\w]+)/$', views.onboarding_screen, name="onboarding-screen"),
]

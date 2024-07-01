from django.conf.urls import include
from django.urls import re_path
from django.views.generic import RedirectView

from .. import views

app_name = 'lnldb'

urlpatterns = [
    re_path(r'^$', views.orgs.vieworgs, name="list"),
    re_path(r'^add/$', views.orgs.addeditorgs, name="add"),
    re_path(r'^(?P<org_id>[0-9]+)/', include([
        re_path(r'^$', views.orgs.orgdetail, name="detail"),
        re_path(r'^edit/$', views.orgs.addeditorgs, name="edit"),
        re_path(r'^verify/$', views.orgs.OrgVerificationCreate.as_view(), name="verify"),
    ])),

    # redirects {{{
    # At some point, a better style for a url format may become apparant.
    #  BUT COOL URLS DON'T CHANGE
    # So, put the old urls down here:
    #  - Use a redirect view with permanent=True
    #  - Don't put a name. We don't want any new links here
    #  - For every batch include the date, so we can remove it in ~3yrs

    # Oct 2016
    re_path(r'^edit/(\d+)/$', RedirectView.as_view(pattern_name="orgs:edit", permanent=True))

    # }}}
]

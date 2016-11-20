from django.conf.urls import include, url
from django.views.generic import RedirectView

from .. import views

urlpatterns = [
    url(r'^$', views.orgs.vieworgs, name="list"),
    url(r'^add/$', views.orgs.addeditorgs, name="add"),
    url(r'^(?P<org_id>[0-9]+)/', include([
        url(r'^$', views.orgs.orgdetail, name="detail"),
        url(r'^edit/$', views.orgs.addeditorgs, name="edit"),
        url(r'^verify/$', views.orgs.OrgVerificationCreate.as_view(), name="verify"),
    ])),
    url(r'^funds/edit/(?P<fund_id>[0-9]+)/$', views.orgs.fund_edit, name="fundedit"),
    url(r'^funds/add/$', views.orgs.fund_edit, name="fundaddraw"),
    url(r'^funds/add/(?P<org>[0-9]+)/$', views.orgs.fund_edit, name="fundadd"),

    # redirects {{{
    # At some point, a better style for a url format may become apparant.
    #  BUT COOL URLS DON'T CHANGE
    # So, put the old urls down here:
    #  - Use a redirect view with permanent=True
    #  - Don't put a name. We don't want any new links here
    #  - For every batch include the date, so we can remove it in ~3yrs

    # Oct 2016
    url(r'^edit/(\d+)/$', RedirectView.as_view(pattern_name="orgs:edit", permanent=True))

    # }}}
]

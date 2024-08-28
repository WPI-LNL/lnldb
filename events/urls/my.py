from django.conf.urls import include
from django.urls import re_path
from django.contrib.auth.decorators import login_required

from .. import views

app_name = 'lnldb'

# prefix: /my/
urlpatterns = [
    re_path(r'^workorders/$', views.my.mywo, name="workorders"),
    re_path(r'^workorders/attach/(?P<id>[0-9]+)/$', views.flow.assignattach_external, name="event-attach"),

    re_path(r'^office-hours/$', views.my.office_hours, name="office-hours"),

    re_path(r'^orgs/', include([
        re_path(r'^$', views.my.myorgs, name="orgs"),
        re_path(r'^form/$', views.my.myorgform, name="org-request"),
        re_path(r'^(?P<id>[0-9a-f]+)/$', views.orgs.orgedit, name="org-edit"),
        re_path(r'^transfer/(?P<id>[0-9]+)/$', views.orgs.org_mkxfer, name="org-transfer"),
        re_path(r'^transfer/(?P<idstr>[0-9a-f]+)/accept/$', views.orgs.org_acceptxfer,
            name="org-accept"),
    ])),

    re_path(r'^events/', include([
        re_path(r'^$', views.my.myevents, name="events"),

        # TODO: merge these with their events equivalents.
        re_path(r'^(?P<eventid>[0-9]+)/files/$', views.my.eventfiles, name="event-files"),
        re_path(r'^(?P<eventid>[0-9]+)/report/$', views.my.ccreport, name="report"),
        re_path(r'^(?P<eventid>[0-9]+)/hours/$', views.my.hours_list, name="hours-list"),
        re_path(r'^(?P<eventid>[0-9]+)/hours/bulk/$', views.my.hours_bulk,
            name="hours-bulk"),
        re_path(r'^(?P<eventid>[0-9]+)/hours/mk/$', views.my.hours_mk,
            name="hours-new"),
        re_path(r'^(?P<eventid>[0-9]+)/hours/(?P<userid>[0-9]+)$', views.my.hours_edit,
            name="hours-edit"),
        re_path(r'^(?P<eventid>[0-9]+)/survey/$', login_required(views.my.PostEventSurveyCreate.as_view()),
            name="post-event-survey"),
        re_path(r'^survey/success/$', views.my.survey_success, name="survey-success"),
    ])),

]

from django.conf.urls import include, url
from django.contrib.auth.decorators import login_required

from .. import views

app_name = 'lnldb'

# prefix: /my/
urlpatterns = [
    url(r'^workorders/$', views.my.mywo, name="workorders"),
    url(r'^workorders/attach/(?P<id>[0-9]+)/$', views.flow.assignattach_external, name="event-attach"),

    url(r'^office-hours/$', views.my.office_hours, name="office-hours"),
    url(r'^office-hours/update/$', views.my.hours_update, name="hours-update"),

    url(r'^orgs/', include([
        url(r'^$', views.my.myorgs, name="orgs"),
        url(r'^form/$', views.my.myorgform, name="org-request"),
        url(r'^(?P<id>[0-9a-f]+)/$', views.orgs.orgedit, name="org-edit"),
        url(r'^transfer/(?P<id>[0-9]+)/$', views.orgs.org_mkxfer, name="org-transfer"),
        url(r'^transfer/(?P<idstr>[0-9a-f]+)/accept/$', views.orgs.org_acceptxfer,
            name="org-accept"),
    ])),

    url(r'^events/', include([
        url(r'^$', views.my.myevents, name="events"),

        # TODO: merge these with their events equivalents.
        url(r'^(?P<eventid>[0-9]+)/files/$', views.my.eventfiles, name="event-files"),
        url(r'^(?P<eventid>[0-9]+)/report/$', views.my.ccreport, name="report"),
        url(r'^(?P<eventid>[0-9]+)/hours/$', views.my.hours_list, name="hours-list"),
        url(r'^(?P<eventid>[0-9]+)/hours/bulk/$', views.my.hours_bulk,
            name="hours-bulk"),
        url(r'^(?P<eventid>[0-9]+)/hours/mk/$', views.my.hours_mk,
            name="hours-new"),
        url(r'^(?P<eventid>[0-9]+)/hours/(?P<userid>[0-9]+)$', views.my.hours_edit,
            name="hours-edit"),
        url(r'^(?P<eventid>[0-9]+)/survey/$', login_required(views.my.PostEventSurveyCreate.as_view()),
            name="post-event-survey"),
        url(r'^survey/success/$', views.my.survey_success, name="survey-success"),
    ])),

]

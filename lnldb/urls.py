from django.conf.urls import patterns, include, url

from events.forms import OrgForm,ContactForm,LightingForm,SoundForm,ProjectionForm
from events.forms import named_event_forms
from events.views.wizard import EventWizard
from events.views.wizard import show_lighting_form_condition,show_sound_form_condition,show_projection_form_condition

from ajax_select import urls as ajax_select_urls

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

#cbv imports
from acct.views import AcctUpdate,LNLUpdate

#event wizard form defenitions



event_wizard = EventWizard.as_view(
    named_event_forms,
    url_name = 'event_step',
    done_step_name = 'finished',
    condition_dict = {
            'lighting':show_lighting_form_condition,
            'sound':show_sound_form_condition,
            'projection':show_projection_form_condition
        }
    )

#generics
from django.views.generic.base import RedirectView

urlpatterns = patterns('',
    # Examples:
    # url(r'^$', 'lnldb.views.home', name='home'),
    # url(r'^lnldb/', include('lnldb.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^jsi18n', 'django.views.i18n.javascript_catalog'),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
    #
    url(r'^$', 'pages.views.page', {'slug':'index'}),
    url(r'^db/$', 'events.views.indices.index'),
        
    #static
    
    #user facing shit
    url(r'^my/$', 'events.views.my.my', name="my"),
    url(r'^my/lnl/$', LNLUpdate.as_view(), name="my-lnl"),
    url(r'^my/workorders/$', 'events.views.my.mywo'),
    url(r'^my/orgs/$', 'events.views.my.myorgs'),
    url(r'^my/acct/$', AcctUpdate.as_view(), name="my-acct"),
    url(r'^my/events/$', 'events.views.my.myevents'),
    url(r'^my/events/(?P<id>[0-9a-f]+)$', 'events.views.my.myeventdetail',name="my-event-detail"),
    #workorders
    url(r'^workorder2/$', 'events.views.indices.workorder'),
    url(r'^workorder/(?P<step>.+)/$', event_wizard, name='event_step'),
    url(r'^workorder/$', event_wizard, name='event'),
    #
    url(r'^lnadmin/$', 'events.views.indices.admin'),
    url(r'^lnadmin/lookups/', include(ajax_select_urls)),
    
    #events
    url(r'^lnadmin/events/view/(?P<id>[0-9a-f]+)/$', 'events.views.flow.viewevent'),        
    url(r'^lnadmin/events/mk/', 'events.views.mkedrm.eventnew'),
    url(r'^lnadmin/events/edit/(?P<id>[0-9a-f]+)/$','events.views.mkedrm.eventnew'),
    url(r'^lnadmin/events/upcoming/$', 'events.views.list.upcoming'),
    url(r'^lnadmin/events/incoming/$', 'events.views.list.incoming'),
    url(r'^lnadmin/events/approve/(?P<id>[0-9a-f]+)/$', 'events.views.flow.approval'), 
    url(r'^lnadmin/events/open/$', 'events.views.list.openworkorders'),
    url(r'^lnadmin/events/paid/$', 'events.views.list.paid'),
    url(r'^lnadmin/events/unpaid/$', 'events.views.list.unpaid'),
    url(r'^lnadmin/events/closed/$', 'events.views.list.closed'),                
    url(r'^lnadmin/events/crew/(?P<id>[0-9a-f]+)/$', 'events.views.flow.assigncrew'),
    url(r'^lnadmin/events/rmcrew/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$', 'events.views.flow.rmcrew'),
    url(r'^lnadmin/events/crewchief/(?P<id>[0-9a-f]+)/$', 'events.views.flow.assigncc'),
    url(r'^lnadmin/events/rmcc/(?P<id>[0-9a-f]+)/(?P<user>[0-9a-f]+)/$', 'events.views.flow.rmcc'),
    
    #orgs (clients)
    url(r'^lnadmin/clients/$', 'events.views.orgs.vieworgs'),
    url(r'^lnadmin/clients/(\d+)/$', 'events.views.orgs.orgdetail'),
    url(r'^lnadmin/clients/add/$', 'events.views.orgs.addeditorgs'),
    url(r'^lnadmin/clients/edit/(\d+)/$', 'events.views.orgs.addeditorgs'),
        
    #inventory 
    url(r'^lnadmin/inventory/view/$', 'inventory.views.view'),
    url(r'^lnadmin/inventory/add/$', 'inventory.views.add'),        
    url(r'^lnadmin/inventory/categories/$', 'inventory.views.categories'),
    url(r'^lnadmin/inventory/cat/(?P<category>[a-zA-Z0-9_.-]+)/$', 'inventory.views.cat'),
    url(r'^lnadmin/inventory/cat/(?P<category>[a-zA-Z0-9_.-]+)/(?P<subcategory>[a-zA-Z0-9_.-]+)$', 'inventory.views.subcat'),
        
    url(r'^lnadmin/inventory/d/(?P<id>[0-9a-f]+)/$', 'inventory.views.detail'),
        
    #members
    url(r'^lnadmin/members/officers/$', 'members.views.officers'),
    url(r'^lnadmin/members/active/$', 'members.views.active'),
    url(r'^lnadmin/members/associate/$', 'members.views.associate'),
    url(r'^lnadmin/members/alum/$', 'members.views.alum'),
    url(r'^lnadmin/members/away/$', 'members.views.away'),
    url(r'^lnadmin/members/detail/(?P<id>[0-9a-f]+)/$', 'members.views.detail'),
        
    #meetings
    url(r'^lnadmin/meetings/new/$', 'meetings.views.newattendance'),
    url(r'^lnadmin/meetings/list/$', 'meetings.views.listattendance'),
    url(r'^lnadmin/meetings/list/(\d+)/$', 'meetings.views.listattendance'),
    url(r'^lnadmin/meetings/view/(\d+)/$', 'meetings.views.viewattendance'),
    url(r'^lnadmin/meetings/edit/(\d+)/$', 'meetings.views.editattendance'),
    #projection
    url(r'^lnadmin/projection/list/$', 'projection.views.plist'),

    url(r'^NOTOUCHING/$', 'data.views.fuckoffkitty'),
    url(r'^lnldb/fuckoffkitty/', RedirectView.as_view(url="/NOTOUCHING/")),
    url(r'^(?P<slug>[-\w]+)/$', 'pages.views.page'),
        
    url(r'^lnadmin/(?P<msg>\w+)/$', 'events.views.indices.admin'),
)

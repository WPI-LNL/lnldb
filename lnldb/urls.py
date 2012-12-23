from django.conf.urls import patterns, include, url

from events.forms import OrgForm,ContactForm,LightingForm,SoundForm,ProjectionForm
from events.forms import named_event_forms
from events.views.wizard import EventWizard

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()
#event wizard form defenitions



event_wizard = EventWizard.as_view(
    named_event_forms,
    url_name = 'event_step',
    done_step_name = 'finished',
    )

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
    url(r'^$', 'events.views.indices.index'),
    #user facing shit
    url(r'^my/$', 'events.views.my.my'),
    url(r'^my/workorders/$', 'events.views.my.mywo'),
    url(r'^my/orgs/$', 'events.views.my.myorgs'),
    url(r'^my/acct/$', 'events.views.my.myacct'),
    url(r'^my/events/$', 'events.views.my.myevents'),
    #workorders
    url(r'^workorder/$', 'events.views.indices.workorder'),
    url(r'^WO/(?P<step>.+)/$', event_wizard, name='event_step'),
    url(r'^WO/$', event_wizard, name='event'),
    #
    url(r'^lnadmin/$', 'events.views.indices.admin'),
    url(r'^lnadmin/(?P<msg>\w+)/$', 'events.views.indices.admin'),
    #events
    url(r'^lnadmin/events/view/(?P<id>[0-9a-f]+)/$', 'events.views.list.viewevent'),        
            
    url(r'^lnadmin/events/upcoming/$', 'events.views.list.upcoming'),
    url(r'^lnadmin/events/incoming/$', 'events.views.list.incoming'),
    url(r'^lnadmin/events/open/$', 'events.views.list.openworkorders'),
    url(r'^lnadmin/events/paid/$', 'events.views.list.paid'),
    url(r'^lnadmin/events/unpaid/$', 'events.views.list.unpaid'),
    url(r'^lnadmin/events/closed/$', 'events.views.list.closed'),                
    url(r'^lnadmin/events/crew/(?P<id>[0-9a-f]+)/$', 'events.views.list.assigncrew'),
    
    #orgs (clients)
    url(r'^lnadmin/clients/view/$', 'events.views.orgs.vieworgs'),
    url(r'^lnadmin/clients/add/$', 'events.views.orgs.addorgs'),
        
    #inventory 
    url(r'^lnadmin/inventory/view/$', 'inventory.views.view'),
    url(r'^lnadmin/inventory/view/(?P<cat>[0-9a-f]+)/$', 'inventory.views.catview'),
    url(r'^lnadmin/inventory/add/$', 'inventory.views.add'),        
    url(r'^lnadmin/inventory/categories/$', 'inventory.views.categories'),

    url(r'^fuckoffkitty/$', 'data.views.fuckoffkitty'),
)

# Create your views here.

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from events.forms import WorkorderSubmit,CrewAssign,OrgForm
from events.forms import named_event_tmpls
from events.models import Event,Organization


from django.contrib.formtools.wizard.views import NamedUrlSessionWizardView

import datetime,time

SUCCESS_MSG_ORG = "Successfully added a new client"

### FRONT 3 PAGES
def index(request):
    context = RequestContext(request)
    return render_to_response('index.html', context) 

def workorder(request):
    context = RequestContext(request)
    
    if request.method == 'POST':
        formset = WorkorderSubmit(request.POST)
        if formset.is_valid():
            neworder = formset.save(commit=False)
            neworder.submitted_by = request.user
            neworder.submitted_ip = request.META['REMOTE_ADDR']
            neworder.save()
            
        else:
            context['formset'] = formset
            #todo: BITCH
            
    else:
        formset = WorkorderSubmit()
        
        context['formset'] = formset
        
    return render_to_response('workorder.html', context) 

def admin(request,msg=None):
    context = RequestContext(request)
    context['msg'] = msg
    return render_to_response('admin.html', context) 


### EVENT VIEWS

def add(request):
    pass


def upcoming(request,limit=True):
    """if limit = False, then it'll show all upcoming events that are more than a week away."""
    context = RequestContext(request)
    
    today = datetime.date.today()
    weekfromnow = today + datetime.timedelta(weeks=1)
    
    events = Event.objects.filter(approved=True).filter(closed=False).filter(paid=False).filter(datetime_start__gte=today)
    if limit:
        events = events.filter(datetime_start__lte=weekfromnow)
    
    context['events'] = events
    
    return render_to_response('events.html', context)


def incoming(request):
    context = RequestContext(request)
    
    events = Event.objects.filter(approved=False).filter(closed=False).filter(paid=False)
    
    context['events'] = events
    return render_to_response('events.html', context)
    
def openworkorders(request):
    context = RequestContext(request)
    
    events = Event.objects.filter(closed=False)
    
    context['events'] = events
    return render_to_response('events.html', context)

def paid(request):
    context = RequestContext(request)
    
    events = Event.objects.filter(approved=True).filter(paid=True)
    
    context['events'] = events
    return render_to_response('events.html', context)

def unpaid(request):
    context = RequestContext(request)
    
    today = datetime.date.today()
    now = time.time()
    events = Event.objects.filter(approved=True).filter(time_setup_start__lte=datetime.datetime.now()).filter(date_setup_start__lte=today)
    
    context['events'] = events
    return render_to_response('events.html', context)    

def closed(request):
    context = RequestContext(request)
     
    events = Event.objects.filter(closed=True)
    
    context['events'] = events
    return render_to_response('events.html', context)       
   
def assigncrew(request,id):
    context = RequestContext(request)
    
    event = get_object_or_404(Event,pk=id)
    
    if request.method == 'POST':
        formset = CrewAssign(request.POST)
        if formset.is_valid():
            formset.save()
            
        else:
            context['formset'] = formset
            
    else:
        formset = CrewAssign
        
        context['formset'] = formset
        
    return render_to_response('form_master.html', context)
    
    
def viewevent(request,id):
    context = RequestContext(request)
    event = get_object_or_404(Event,pk=id)
    
    context['event'] = event
    
    return render_to_response('uglydetail.html', context)
    
### ORGANIZATION VIEWS

def vieworgs(request):
    context = RequestContext(request)
    
    orgs = Organization.objects.all()
    
    context['orgs'] = orgs
    
    return render_to_response('orgs.html', context)
    
    
def addorgs(request):
    context = RequestContext(request)
    
    if request.method == 'POST': 
        formset = OrgForm(request.POST)
        if formset.is_valid():
            formset.save()
            #return HttpResponseRedirect(reverse('events.views.admin', kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('events.views.admin'))
        
        else:
            context['formset'] = formset
    else:
        msg = "New Client"
        formset = OrgForm
        
        context['formset'] = formset
        context['msg'] = msg
    
    return render_to_response('form_master.html', context)


### USER FACING SHIT
def my(request):
    context = RequestContext(request)
    return render_to_response('my.html', context)

def myacct(request):
    context = RequestContext(request)
    return render_to_response('myacct.html', context)

def myevents(request):
    context = RequestContext(request)
    
    user = request.user
    orgs = user.orgusers.get_query_set()
    
    events = Event.objects.filter(group__in=orgs)
    
    context['events'] = events
    return render_to_response('myevents.html', context)
    
def myorgs(request):
    context = RequestContext(request)
    
    user = request.user
    orgs = user.orgusers.get_query_set()
        
    context['orgs'] = orgs
    return render_to_response('myorgs.html', context)

    
#CBV NuEventForm
class EventWizard(NamedUrlSessionWizardView):
    def done(self, form_list, **kwargs):
        pass
    def get_template_names(self):
        return [named_event_tmpls[self.steps.current]]

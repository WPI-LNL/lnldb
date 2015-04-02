# Create your views here.

import datetime
import time

from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.template import RequestContext
from events.forms import WorkorderSubmit, CrewAssign, OrgForm
from events.forms import named_event_tmpls
from events.models import Event, Organization
from django.contrib.formtools.wizard.views import NamedUrlSessionWizardView


SUCCESS_MSG_ORG = "Successfully added a new client"


### FRONT 3 PAGES
def index(request):
    context = {}
    return render(request, 'index.html', context)


def workorder(request):
    context = {}

    if request.method == 'POST':
        formset = WorkorderSubmit(request.POST)
        if formset.is_valid():
            neworder = formset.save(commit=False)
            neworder.submitted_by = request.user
            neworder.submitted_ip = request.META['REMOTE_ADDR']
            neworder.save()

        else:
            context['formset'] = formset
            # todo: BITCH

    else:
        formset = WorkorderSubmit()

        context['formset'] = formset

    return render(request, 'workorder.html', context)


def admin(request, msg=None):
    context = {}
    context['msg'] = msg
    return render(request, 'admin.html', context)


### EVENT VIEWS

def add(request):
    pass


def upcoming(request, limit=True):
    """if limit = False, then it'll show all upcoming events that are more than a week away."""
    context = {}

    today = datetime.date.today()
    weekfromnow = today + datetime.timedelta(weeks=1)

    events = Event.objects.filter(approved=True).filter(closed=False).filter(paid=False).filter(
        datetime_start__gte=today)
    if limit:
        events = events.filter(datetime_start__lte=weekfromnow)

    context['events'] = events

    return render(request, 'events.html', context)


def incoming(request):
    context = {}

    events = Event.objects.filter(approved=False).filter(closed=False).filter(paid=False)

    context['events'] = events
    return render(request, 'events.html', context)


def openworkorders(request):
    context = {}

    events = Event.objects.filter(closed=False)

    context['events'] = events
    return render(request, 'events.html', context)


def paid(request):
    context = {}

    events = Event.objects.filter(approved=True).filter(paid=True)

    context['events'] = events
    return render(request, 'events.html', context)


def unpaid(request):
    context = {}

    today = datetime.date.today()
    now = time.time()
    events = Event.objects.filter(approved=True).filter(time_setup_start__lte=datetime.datetime.now()).filter(
        date_setup_start__lte=today)

    context['events'] = events
    return render(request, 'events.html', context)


def closed(request):
    context = {}

    events = Event.objects.filter(closed=True)

    context['events'] = events
    return render(request, 'events.html', context)


def assigncrew(request, id):
    context = {}

    event = get_object_or_404(Event, pk=id)

    if request.method == 'POST':
        formset = CrewAssign(request.POST)
        if formset.is_valid():
            formset.save()

        else:
            context['formset'] = formset

    else:
        formset = CrewAssign

        context['formset'] = formset

    return render(request, 'form_master.html', context)


def viewevent(request, id):
    context = {}
    event = get_object_or_404(Event, pk=id)

    context['event'] = event

    return render(request, 'uglydetail.html', context)


### ORGANIZATION VIEWS

def vieworgs(request):
    context = {}

    orgs = Organization.objects.all()

    context['orgs'] = orgs

    return render(request, 'orgs.html', context)


def addorgs(request):
    context = {}

    if request.method == 'POST':
        formset = OrgForm(request.POST)
        if formset.is_valid():
            formset.save()
            # return HttpResponseRedirect(reverse('events.views.admin', kwargs={'msg':SUCCESS_MSG_ORG}))
            return HttpResponseRedirect(reverse('events.views.admin'))

        else:
            context['formset'] = formset
    else:
        msg = "New Client"
        formset = OrgForm

        context['formset'] = formset
        context['msg'] = msg

    return render(request, 'form_master.html', context)


### USER FACING SHIT
def my(request):
    context = {}
    return render(request, 'my.html', context)


def myacct(request):
    context = {}
    return render(request, 'myacct.html', context)


def myevents(request):
    context = {}

    user = request.user
    orgs = user.orgusers.get_queryset()

    events = Event.objects.filter(group__in=orgs)

    context['events'] = events
    return render(request, 'myevents.html', context)


def myorgs(request):
    context = {}

    user = request.user
    orgs = user.orgusers.get_queryset()

    context['orgs'] = orgs
    return render(request, 'myorgs.html', context)


# CBV NuEventForm
class EventWizard(NamedUrlSessionWizardView):
    def done(self, form_list, **kwargs):
        pass

    def get_template_names(self):
        return [named_event_tmpls[self.steps.current]]

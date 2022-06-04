from __future__ import unicode_literals
import datetime
from itertools import chain

from django.contrib.auth.decorators import login_required
from django.db.models.aggregates import Sum
from django.forms.models import modelformset_factory
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls.base import reverse
from django.utils import timezone
from django.views.generic import CreateView
from django.template import loader

from emails.generators import generate_selfservice_notice_email
from events.forms import (SelfServiceOrgRequestForm, PostEventSurveyForm, OfficeHoursForm)
from events.models import CCReport, BaseEvent, PostEventSurvey, OfficeHour
from helpers.mixins import LoginRequiredMixin
from helpers.revision import set_revision_comment


@login_required
def mywo(request):
    """ List Events (if LNL member will list their events)"""
    context = {}

    user = request.user
    orgs = user.orgusers.get_queryset()
    ic_orgs = user.orgowner.get_queryset()

    # combined = orgs|ic_orgs
    # combined = ic_orgs
    # values = orgs.distinct().values_list('id', flat=True)

    # events = Event.objects.filter(org__in=values)
    l = {}
    for org in chain(orgs, ic_orgs):
        l[org.name] = BaseEvent.objects.filter(org=org)
    l["Submitted by Me"] = BaseEvent.objects.filter(submitted_by=user)

    # context['events'] = events
    context['events'] = l
    owned = ic_orgs.values_list('name', flat=True)
    assoc = orgs.values_list('name', flat=True)
    context['owned'] = list(set(list(owned) + list(assoc)))
    return render(request, 'mywo.html', context)


@login_required
def myorgs(request):
    """ List of associated organizations """
    context = {}

    user = request.user
    context['ownedorgs'] = user.orgowner.get_queryset()
    context['memberorgs'] = user.orgusers.get_queryset()

    return render(request, 'myorgs.html', context)


@login_required
def myorgform(request):
    """ Organization Creation Request Form"""
    context = {'msg': "Client Request",
               'extra_text': 'Note: The information being requested here is not your personal information.'
                             ' This information should relate to the client account that is being requested '
                             'and should only mirror your personal information if you are requesting that a '
                             'personal account be made.'}
    if request.method == "POST":
        form = SelfServiceOrgRequestForm(request.POST)
        if form.is_valid():
            email_context = {'client_name': form.cleaned_data['client_name'], 'email': form.cleaned_data['email'],
                             'address': form.cleaned_data['address'], 'phone': form.cleaned_data['phone'],
                             'user': request.user, 'submitted_ip': request.META['REMOTE_ADDR']}
            email = generate_selfservice_notice_email(email_context)
            email.send()
            return render(request, 'org.service.html', context)
    else:
        form = SelfServiceOrgRequestForm()
    context['formset'] = form
    return render(request, 'mycrispy.html', context)


# LNL facing
@login_required
def myevents(request):
    """ Lists events that a user has CC'd or been involved with """
    context = {'user': request.user, 'now': datetime.datetime.now(timezone.get_current_timezone()),
               'ccinstances': request.user.ccinstances.select_related('event__location').all(),
               'orgs': request.user.all_orgs.prefetch_related('events__location'),
               'submitted_events': request.user.submitter.select_related('location').all(),
               'hours': request.user.hours.select_related('event__location').all()}

    context.update(request.user.hours.aggregate(totalhours=Sum('hours')))

    return render(request, 'myevents.html', context)

@login_required
def ccreport(request, eventid):
    if BaseEvent.objects.get(pk=eventid).closed:
        return redirect('/db/events/view/' + str(eventid) + '/#reports')
    elif (my_ccreports:= CCReport.objects.filter(event=eventid, crew_chief=request.user)).exists():
        return redirect('/db/events/view/' + str(eventid) + '/report/update/' + str(my_ccreports.last().id) + '/')
    else:
        return redirect('/db/events/view/' + str(eventid) + '/report/mk/')

class PostEventSurveyCreate(LoginRequiredMixin, CreateView):
    model = PostEventSurvey
    form_class = PostEventSurveyForm
    template_name = 'form_crispy_survey.html'

    def get_form_kwargs(self):
        kwargs = super(PostEventSurveyCreate, self).get_form_kwargs()
        now = timezone.now()
        kwargs['event'] = get_object_or_404(
            BaseEvent.objects.exclude(closed=True).filter(approved=True, datetime_end__lt=now),
            pk=self.kwargs['eventid']
        )
        return kwargs

    def get_context_data(self, **kwargs):
        context = super(PostEventSurveyCreate, self).get_context_data(**kwargs)
        now = timezone.now()
        context['CCSS'] = 'survey'
        context['NO_FOOT'] = True
        context['event'] = get_object_or_404(
            BaseEvent.objects.exclude(closed=True).filter(approved=True, datetime_end__lt=now),
            pk=self.kwargs['eventid']
        )
        return context

    def dispatch(self, request, *args, **kwargs):
        if PostEventSurvey.objects.filter(event__id=kwargs['eventid'], person=request.user).exists():
            # return HttpResponse('You have already taken this survey.', status=403)
            template = loader.get_template('default.html')
            return HttpResponse(template.render({
                'title': "You have already taken this survey",
                'message': "If you believe that you are receiving this message in error, please ",
                'link': "mailto:lnl-vp@wpi.edu",
                'link_desc': "contact us",
                'NO_FOOT': True
            }, request))
        event = get_object_or_404(
            BaseEvent.objects.exclude(closed=True).filter(approved=True, datetime_end__lt=timezone.now()),
            pk=kwargs['eventid']
        )
        if event.datetime_end <= (timezone.now() - timezone.timedelta(days=60)):
            template = loader.get_template('default.html')
            return HttpResponse(template.render({
                'title': "Sorry, this link has expired",
                'message': "Unfortunately the survey for this event is no longer available. If you would still like to "
                           "share your feedback with us, email ",
                'link': "mailto:lnl@wpi.edu",
                'link_desc': "lnl@wpi.edu",
                'NO_FOOT': True
            }, request))
        return super(PostEventSurveyCreate, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.person = self.request.user
        result = super(PostEventSurveyCreate, self).form_valid(form)
        # Automatically add the survey-taker to the client (if the event has only one client)
        if obj.event.org.count() == 1 and obj.person not in obj.event.org.get().associated_users.all():
            set_revision_comment('Took post-event survey for {}. User automatically added to client.'.format(
                self.object.event.event_name), None)
            obj.event.org.get().associated_users.add(obj.person)
        return result

    def get_success_url(self):
        return reverse("my:survey-success")


def survey_success(request):
    """ Displayed to the user after successfully completing a survey """
    template = loader.get_template('default.html')
    return HttpResponse(template.render({
        'title': "Thank you!",
        'message': "Your response has been recorded. If you have any further comments, feel free to email us at ",
        'link': "mailto:lnl@wpi.edu",
        'link_desc': "lnl@wpi.edu",
        'NO_FOOT': True,
        'EXIT_BTN': True
    }, request))


@login_required
def office_hours(request):
    """ Form for updating a user's office hours (Officers only) """
    context = {}
    user = request.user

    context['msg'] = "Office Hours"

    hours = OfficeHour.objects.filter(officer=user)

    hour_formset = modelformset_factory(OfficeHour, exclude=[], extra=2, can_delete=True, form=OfficeHoursForm)
    formset = hour_formset(queryset=hours)

    if request.method == 'POST':
        formset = hour_formset(request.POST)
        if formset.is_valid():
            for form in formset.forms:
                form.instance.officer = user
            formset.save()
            return HttpResponseRedirect(reverse("accounts:detail", args=[user.id]))
    context['formset'] = formset

    return render(request, 'formset_generic.html', context)

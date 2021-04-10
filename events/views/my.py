from __future__ import unicode_literals
import datetime
from itertools import chain

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models.aggregates import Sum
from django.forms.models import inlineformset_factory, modelformset_factory
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls.base import reverse
from django.utils import timezone
from django.views.generic import CreateView
from django.template import loader

from emails.generators import generate_selfservice_notice_email
from events.forms import (EditHoursForm, InternalReportForm, MKHoursForm,
                          SelfServiceOrgRequestForm, PostEventSurveyForm, OfficeHoursForm, OfficeHourUpdateForm)
from events.models import CCReport, BaseEvent, Event, Hours, PostEventSurvey, CCR_DELTA, OfficeHour, HourChange
from helpers.mixins import LoginRequiredMixin
from helpers.revision import set_revision_comment
from helpers.util import curry_class


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
def eventfiles(request, eventid):
    return redirect('/db/events/view/' + eventid + '/#files')


# Views Relating to Crew Chiefs
@login_required
def ccreport(request, eventid):
    """ Submits a crew chief report """
    context = {}

    user = request.user

    uevent = user.ccinstances.filter(event__pk=eventid)
    # check that the event in question belongs to the user
    if not uevent:
        return HttpResponse("This event must not have been yours, or is closed")

    event = uevent[0].event
    if not event.reports_editable:
        return render(request, 'too_late.html', {'days': CCR_DELTA, 'event': event})

    # get event
    x = event.ccinstances.filter(crew_chief=user)
    context['msg'] = "Crew Chief Report for '<em>%s</em>' (%s)" % (event, ",".join([str(i.category) for i in x]))

    # create report
    try:
        report = CCReport.objects.get(event=event, crew_chief=user)
    except CCReport.DoesNotExist:
        report = None

    # standard save flow
    if request.method == 'POST':
        formset = InternalReportForm(data=request.POST, event=event, request_user=user, instance=report)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse("my:events"))
        else:
            context['formset'] = formset

    else:
        formset = InternalReportForm(event=event, request_user=user, instance=report)

        context['formset'] = formset

    return render(request, 'mycrispy.html', context)


@login_required
def hours_list(request, eventid):
    """ Lists a user's work hours """
    context = {}
    user = request.user

    event = user.ccinstances.filter(event__pk=eventid)

    if not event:
        return HttpResponse("You must not have cc'd this event, or it's closed")
    event = event[0].event
    context['event'] = event

    hours = event.hours.all()
    context['hours'] = hours

    return render(request, 'myhours.html', context)


@login_required
def hours_mk(request, eventid):
    """ Hour Entry Form for CC """
    context = {}

    user = request.user
    uevent = user.ccinstances.filter(event__pk=eventid)

    if not uevent:
        return HttpResponse("This event must not have been yours, or is closed")

    event = uevent[0].event

    if not isinstance(event, Event):
        # New event - redirect to bulk update tool instead
        return HttpResponseRedirect(reverse("my:hours-bulk", args=(event.id,)))

    if not event.reports_editable:
        return render(request, 'too_late.html', {'days': CCR_DELTA, 'event': event})

    context['msg'] = "Hours for '%s'" % event.event_name
    if request.method == 'POST':
        formset = MKHoursForm(event, request.POST)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse("my:hours-list", args=(event.id,)))
    else:
        formset = MKHoursForm(event)

    context['formset'] = formset

    return render(request, 'mycrispy.html', context)


@login_required
def hours_edit(request, eventid, userid):
    """ Hour Entry Form for CC (editing)"""
    context = {}
    user = request.user
    uevent = user.ccinstances.filter(event__pk=eventid)

    if not uevent:
        return HttpResponse("You must not have cc'd this event, or it's closed")

    event = uevent[0].event
    if not event.reports_editable:
        return render(request, 'too_late.html', {'days': CCR_DELTA, 'event': event})

    hours = get_object_or_404(Hours, event=event, user_id=userid)
    u = get_object_or_404(get_user_model(), pk=userid)
    context['msg'] = "Hours for '%s' on '%s'" % (u, event.event_name)
    if request.method == 'POST':
        formset = EditHoursForm(request.POST, instance=hours)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse("my:hours-list", args=(event.id,)))
    else:
        formset = EditHoursForm(instance=hours)

    context['formset'] = formset

    return render(request, 'mycrispy.html', context)


@login_required
def hours_bulk(request, eventid):
    """ Bulk Hours Entry Form """
    context = {}
    user = request.user
    uevent = user.ccinstances.filter(event__pk=eventid)

    if not uevent:
        return HttpResponse("You must not have cc'd this event, or it's closed")

    event = uevent[0].event
    if not event.reports_editable:
        return render(request, 'too_late.html', {'days': CCR_DELTA, 'event': event})

    context['msg'] = "Bulk Hours Entry"

    context['event'] = event

    mk_event_formset = inlineformset_factory(Event, Hours, extra=15, exclude=[])
    mk_event_formset.form = curry_class(MKHoursForm, event=event)

    if request.method == 'POST':
        formset = mk_event_formset(request.POST, instance=event)
        if formset.is_valid():
            formset.save()
            return HttpResponseRedirect(reverse("my:hours-list", args=(event.id,)))
    else:
        formset = mk_event_formset(instance=event)

    context['formset'] = formset

    return render(request, 'formset_hours_bulk.html', context)


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

    return render(request, 'formset_office_hours.html', context)


@login_required
def hours_update(request):
    """ Form for posting an announcement regarding a temporary adjustment to a user's office hours (Officers only) """
    context = {}
    user = request.user

    context['msg'] = "Temporary Office Hours Update"

    updates = HourChange.objects.filter(officer=user)

    update_formset = modelformset_factory(HourChange, exclude=[], extra=2, can_delete=True, form=OfficeHourUpdateForm)
    formset = update_formset(queryset=updates)

    if request.method == "POST":
        formset = update_formset(request.POST)
        if formset.is_valid():
            for form in formset.forms:
                form.instance.officer = user
            formset.save()
            return HttpResponseRedirect(reverse("accounts:detail", args=[user.id]))
    context['formset'] = formset

    return render(request, 'formset_office_hour_updates.html', context)

# Create your views here.

import datetime

from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.forms.models import inlineformset_factory
from django.utils.functional import curry
from events.forms import CCIForm
from events.models import Event, EventCCInstance
from meetings.forms import MeetingAdditionForm
from meetings.models import Meeting
from meetings.forms import AnnounceSendForm
from meetings.forms import AnnounceCCSendForm
from meetings.models import AnnounceSend
from django.core.paginator import Paginator, InvalidPage
from django.contrib.auth.decorators import login_required, user_passes_test
from helpers.challenges import is_officer
from emails.generators import generate_notice_email
from emails.generators import generate_notice_cc_email


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def viewattendance(request, id):
    context = RequestContext(request)
    m = get_object_or_404(Meeting, pk=id)
    context['m'] = m

    now = m.datetime
    yest = now + datetime.timedelta(days=-1)
    morethanaweek = now + datetime.timedelta(days=7, hours=12)

    upcoming = Event.objects.filter(datetime_start__gte=yest, datetime_start__lte=morethanaweek)
    context['events'] = upcoming

    lessthantwoweeks = morethanaweek + datetime.timedelta(days=7)
    future = Event.objects.filter(datetime_start__gte=morethanaweek, datetime_start__lte=lessthantwoweeks).order_by(
        'datetime_start')
    context['future'] = future
    return render_to_response('meeting_view.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def updateevent(request, meetingid, eventid):
    context = RequestContext(request)
    context['msg'] = "Update Event"
    event = get_object_or_404(Event, pk=eventid)
    context['event'] = event.event_name

    cc_formset = inlineformset_factory(Event, EventCCInstance, extra=3)
    cc_formset.form = staticmethod(curry(CCIForm, event=event))

    if request.method == 'POST':
        formset = cc_formset(request.POST, instance=event, prefix="main")
        if formset.is_valid():
            formset.save()
            url = reverse('meetings.views.viewattendance', args=(meetingid,)) + "#events"
            return HttpResponseRedirect(url)
        else:
            context['formset'] = formset
    else:
        formset = cc_formset(instance=event, prefix="main")
        context['formset'] = formset
    return render_to_response('formset_crispy_helpers.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def editattendance(request, id):
    context = RequestContext(request)
    context['msg'] = "Edit Meeting"
    m = get_object_or_404(Meeting, pk=id)
    if request.method == 'POST':
        formset = MeetingAdditionForm(request.POST, instance=m)
        if formset.is_valid():
            m = formset.save()
            url = reverse('meetings.views.viewattendance', args=(m.id,)) + "#attendance"
            return HttpResponseRedirect(url)
        else:
            context['formset'] = formset
    else:
        formset = MeetingAdditionForm(instance=m)
        context['formset'] = formset
    return render_to_response('form_crispy.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def listattendance(request, page=1):
    context = RequestContext(request)
    attend = Meeting.objects.all()
    paginated = Paginator(attend, 10)

    try:
        attend = paginated.page(page)
    except InvalidPage:
        attend = paginated.page(1)

    context['attend'] = attend
    return render_to_response('meeting_list.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def newattendance(request):
    context = RequestContext(request)
    if request.method == 'POST':
        formset = MeetingAdditionForm(request.POST)
        if formset.is_valid():
            m = formset.save()
            return HttpResponseRedirect(reverse('meetings.views.viewattendance', args=(m.id,)))
        else:
            context['formset'] = formset
            context['msg'] = "New Meeting (Errors In Form)"
    else:
        formset = MeetingAdditionForm()
        context['formset'] = formset
        context['msg'] = "New Meeting"
    return render_to_response('form_crispy.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def mknotice(request, id):
    context = RequestContext(request)

    meeting = get_object_or_404(Meeting, pk=id)

    if request.method == 'POST':
        formset = AnnounceSendForm(meeting, request.POST)
        if formset.is_valid():
            notice = formset.save()
            email = generate_notice_email(notice)
            res = email.send()
            if res == 1:
                success = True
            else:
                success = False
            AnnounceSend.objects.create(announce=notice, sent_success=success)
            url = reverse('meetings.views.viewattendance', args=(meeting.id,)) + "#emails"
            return HttpResponseRedirect(url)
        else:
            context['formset'] = formset

    else:
        formset = AnnounceSendForm(meeting)
        context['formset'] = formset
        context['msg'] = "New Meeting Notice"
    return render_to_response('form_crispy.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING/')
def mkccnotice(request, id):
    context = RequestContext(request)

    meeting = get_object_or_404(Meeting, pk=id)

    if request.method == 'POST':
        formset = AnnounceCCSendForm(meeting, request.POST)
        if formset.is_valid():
            notice = formset.save()
            email = generate_notice_cc_email(notice)
            res = email.send()
            if res == 1:
                notice.sent_success = True
            else:
                notice.sent_success = False

            notice.save()

            url = reverse('meetings.views.viewattendance', args=(meeting.id,)) + "#emails"
            return HttpResponseRedirect(url)
        else:
            context['formset'] = formset

    else:
        formset = AnnounceCCSendForm(meeting)
        context['formset'] = formset
        context['msg'] = "CC Meeting Notice"
    return render_to_response('form_crispy.html', context)
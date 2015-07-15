# Create your views here.

import datetime
from data.views import serve_file
from django.core.exceptions import PermissionDenied

from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.http.response import Http404
from django.template import RequestContext
from django.forms.models import inlineformset_factory, ModelForm
from django.utils.functional import curry
from events.forms import CCIForm
from events.models import Event, EventCCInstance
from meetings.forms import MeetingAdditionForm, MtgAttachmentEditForm
from meetings.models import Meeting, MtgAttachment
from meetings.forms import AnnounceSendForm
from meetings.forms import AnnounceCCSendForm
from meetings.models import AnnounceSend
from django.core.paginator import Paginator, InvalidPage
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from helpers.challenges import is_officer
from emails.generators import generate_notice_email
from emails.generators import generate_notice_cc_email
from django.db.models.aggregates import Count


@login_required
def download_att(request, mtg_id, att_id):
    mtg = get_object_or_404(Meeting, pk=mtg_id)
    if not request.user.has_perm('meetings.view_mtg', mtg):
        raise PermissionDenied
    att = get_object_or_404(MtgAttachment, pk=att_id)
    if not att.meeting or att.meeting.pk != mtg.pk:
        raise PermissionDenied
    elif att.private and not request.user.has_perm('meetings.view_mtg_closed', mtg):
        raise PermissionDenied
    return serve_file(request, att.file)


@login_required
def rm_att(request, mtg_id, att_id):
    mtg = get_object_or_404(Meeting, pk=mtg_id)
    if not request.user.has_perm('meetings.edit_mtg', mtg):
        raise PermissionDenied
    att = get_object_or_404(MtgAttachment, pk=att_id)
    if not att.meeting or att.meeting.pk != mtg.pk:
        raise PermissionDenied
    mtg.attachments.remove(att)
    return HttpResponseRedirect(reverse('meetings.views.viewattendance', args=(mtg.pk,)))


@login_required
def modify_att(request, mtg_id, att_id):
    context = {}
    mtg_perms = ('meetings.edit_mtg',)
    att_perms = []
    context['msg'] = "Update Attachment"
    mtg = get_object_or_404(Meeting, pk=mtg_id)
    att = get_object_or_404(MtgAttachment, pk=att_id)
    if not (request.user.has_perms(mtg_perms, mtg) and
                request.user.has_perms(att_perms, att) and
                att.meeting and
                    att.meeting.pk == mtg.pk):
        raise PermissionDenied

    if request.method == 'POST':
        form = MtgAttachmentEditForm(instance=att, data=request.POST, files=request.FILES)
        if form.is_valid():
            form.save()
            url = reverse('meetings.views.viewattendance', args=(mtg_id,)) + "#minutes"
            return HttpResponseRedirect(url)
        else:
            context['formset'] = form
    else:
        form = MtgAttachmentEditForm(instance=att)
        context['formset'] = form
    return render(request, 'form_crispy.html', context)


@login_required
def viewattendance(request, id):
    context = {}
    perms = ('meetings.view_mtg_attendance',)
    try:
        m = Meeting.objects.prefetch_related('attendance').get(pk=id)
    except Meeting.DoesNotExist:
        raise Http404(0)
    if not (request.user.has_perms(perms) or
                request.user.has_perms(perms, m)):
        raise PermissionDenied
    context['m'] = m

    now = m.datetime
    yest = now + datetime.timedelta(days=-1)
    morethanaweek = now + datetime.timedelta(days=7, hours=12)

    upcoming = Event.objects.filter(datetime_start__gte=yest, datetime_start__lte=morethanaweek)
    context['events'] = upcoming.prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('ccinstances__service')

    lessthantwoweeks = morethanaweek + datetime.timedelta(days=7)
    future = Event.objects.filter(datetime_start__gte=morethanaweek, datetime_start__lte=lessthantwoweeks).order_by(
        'datetime_start').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('ccinstances__service')
    context['future'] = future
    return render(request, 'meeting_view.html', context)


@login_required
def updateevent(request, meetingid, eventid):
    context = {}
    perms = ('meetings.edit_mtg',)
    context['msg'] = "Update Event"
    event = get_object_or_404(Event, pk=eventid)
    if not (request.user.has_perms(perms) or
                request.user.has_perms(perms, event)):
        raise PermissionDenied
    context['event'] = event.event_name

    cc_formset = inlineformset_factory(Event, EventCCInstance, extra=3, exclude=[])
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
    return render(request, 'formset_crispy_helpers.html', context)


@login_required
def editattendance(request, id):
    context = {}
    perms = ('meetings.edit_mtg',)
    context['msg'] = "Edit Meeting"
    m = get_object_or_404(Meeting, pk=id)
    if not (request.user.has_perms(perms) or
                request.user.has_perms(perms, m)):
        raise PermissionDenied
    if request.method == 'POST':
        formset = MeetingAdditionForm(request.POST, request.FILES, instance=m)
        if formset.is_valid():
            for each in formset.cleaned_data['attachments']:
                MtgAttachment.objects.create(file=each, name=each.name, author=request.user, meeting=m, private=False)
            for each in formset.cleaned_data['attachments_private']:
                MtgAttachment.objects.create(file=each, name=each.name, author=request.user, meeting=m, private=True)
            m = formset.save()
            url = reverse('meetings.views.viewattendance', args=(m.id,)) + "#attendance"
            return HttpResponseRedirect(url)
        else:
            context['formset'] = formset
    else:
        formset = MeetingAdditionForm(instance=m)
        context['formset'] = formset
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('meetings.list_mtgs', raise_exception=True)
def listattendance(request, page=1):
    context = {}
    attend = Meeting.objects \
        .select_related('meeting_type__name') \
        .annotate(num_attendees=Count('attendance')) \
        .all()
    paginated = Paginator(attend, 10)

    try:
        attend = paginated.page(page)
    except InvalidPage:
        attend = paginated.page(1)

    context['attend'] = attend
    return render(request, 'meeting_list.html', context)


@login_required
@permission_required('meetings.create_mtg', raise_exception=True)
def newattendance(request):
    context = {}
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
    return render(request, 'form_crispy.html', context)


@login_required
def mknotice(request, id):
    context = {}
    perms = ('meetings.send_mtg_notice',)
    meeting = get_object_or_404(Meeting, pk=id)
    if not (request.user.has_perms(perms) or
                request.user.has_perms(perms, meeting)):
        raise PermissionDenied
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
    return render(request, 'form_crispy.html', context)


@login_required
def mkccnotice(request, id):
    context = {}
    perms = ('meetings.send_mtg_notice',)
    meeting = get_object_or_404(Meeting, pk=id)
    if not (request.user.has_perms(perms) or
                request.user.has_perms(perms, meeting)):
        raise PermissionDenied

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
    return render(request, 'form_crispy.html', context)

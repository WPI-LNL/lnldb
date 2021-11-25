import datetime

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import InvalidPage, Paginator
from django.db.models.aggregates import Count
from django.db.models import F
from django.views.generic.edit import DeleteView
from django.forms.models import inlineformset_factory
from django.http import HttpResponseRedirect, HttpResponse
from django.http.response import Http404
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils import timezone
from email.mime.base import MIMEBase
from email.encoders import encode_base64
from helpers.util import curry_class

from helpers.mixins import HasPermMixin, LoginRequiredMixin
from data.views import serve_file
from emails.generators import generate_notice_cc_email, generate_notice_email
from events.forms import CCIForm
from events.models import BaseEvent, EventCCInstance
from events.cal import generate_ics

from .forms import (AnnounceCCSendForm, AnnounceSendForm, MeetingAdditionForm,
                    MtgAttachmentEditForm)
from .models import AnnounceSend, Meeting, MtgAttachment


@login_required
def download_att(request, mtg_id, att_id):
    """
    Download a meeting attachment

    :param mtg_id: The primary key value of the meeting
    :param att_id: The primary key value of the attachment
    """
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
    """
    Remove an attachment from a meeting

    :param mtg_id: The primary key value of the meeting
    :param att_id: The primary key value of the attachment
    """
    mtg = get_object_or_404(Meeting, pk=mtg_id)
    if not request.user.has_perm('meetings.edit_mtg', mtg):
        raise PermissionDenied
    att = get_object_or_404(MtgAttachment, pk=att_id)
    if not att.meeting or att.meeting.pk != mtg.pk:
        raise PermissionDenied
    mtg.attachments.remove(att)
    return HttpResponseRedirect(reverse('meetings:detail', args=(mtg.pk,)))


@login_required
def modify_att(request, mtg_id, att_id):
    """
    Update an attachment

    :param mtg_id: The primary key value of the meeting
    :param att_id: The primary key value of the attachment
    """
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
            url = reverse('meetings:detail', args=(mtg_id,)) + "#minutes"
            return HttpResponseRedirect(url)
    else:
        form = MtgAttachmentEditForm(instance=att)
    context['form'] = form
    return render(request, 'form_crispy_meetings.html', context)


@login_required
def viewattendance(request, mtg_id):
    """ View event details """
    context = {}
    perms = ('meetings.view_mtg_attendance',)
    try:
        m = Meeting.objects.prefetch_related('attendance').get(pk=mtg_id)
    except Meeting.DoesNotExist:
        raise Http404(0)
    if not (request.user.has_perms(perms) or
            request.user.has_perms(perms, m)):
        raise PermissionDenied
    context['m'] = m

    now = m.datetime
    yest = now + datetime.timedelta(days=-1)
    morethanaweek = now + datetime.timedelta(days=7, hours=12)

    upcoming = BaseEvent.objects.filter(datetime_start__gte=yest, datetime_start__lte=morethanaweek)
    context['events'] = upcoming.prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('ccinstances__service')

    lessthantwoweeks = morethanaweek + datetime.timedelta(days=7)
    future = BaseEvent.objects.filter(datetime_start__gte=morethanaweek, datetime_start__lte=lessthantwoweeks).order_by(
        'datetime_start').prefetch_related('ccinstances__crew_chief') \
        .prefetch_related('ccinstances__service')
    context['future'] = future
    return render(request, 'meeting_view.html', context)


@login_required
def updateevent(request, mtg_id, event_id):
    """
    Update crew chief assignments for an event

    :param mtg_id: The primary key value of the meeting (redirects to meeting detail page)
    :param event_id: The primary key value of the event (pre-2019 events only)
    """
    context = {}
    perms = ('meetings.edit_mtg',)
    event = get_object_or_404(BaseEvent, pk=event_id)
    if not (request.user.has_perms(perms) or request.user.has_perms(perms, event)):
        raise PermissionDenied
    context['event'] = event.event_name

    cc_formset = inlineformset_factory(BaseEvent, EventCCInstance, extra=3, exclude=[])
    cc_formset.form = curry_class(CCIForm, event=event)

    if request.method == 'POST':
        formset = cc_formset(request.POST, instance=event, prefix="main")
        if formset.is_valid():
            formset.save()
            url = reverse('meetings:detail', args=(mtg_id,)) + "#events"
            return HttpResponseRedirect(url)
    else:
        formset = cc_formset(instance=event, prefix="main")
    context['formset'] = formset
    return render(request, 'formset_crispy_helpers.html', context)


@login_required
def editattendance(request, mtg_id):
    """ Update event details """
    context = {}
    perms = ('meetings.edit_mtg',)
    context['msg'] = "Edit Meeting"
    m = get_object_or_404(Meeting, pk=mtg_id)
    if not (request.user.has_perms(perms) or
            request.user.has_perms(perms, m)):
        raise PermissionDenied
    if request.method == 'POST':
        form = MeetingAdditionForm(data=request.POST, files=request.FILES, instance=m, request_user=request.user)
        if form.is_valid():
            for each in form.cleaned_data.get('attachments', []):
                MtgAttachment.objects.create(file=each, name=each.name, author=request.user, meeting=m, private=False)
            for each in form.cleaned_data.get('attachments_private', []):
                MtgAttachment.objects.create(file=each, name=each.name, author=request.user, meeting=m, private=True)
            m = form.save()
            url = reverse('meetings:detail', args=(m.id,)) + "#attendance"
            return HttpResponseRedirect(url)
    else:
        form = MeetingAdditionForm(instance=m, request_user=request.user)
    context['form'] = form
    return render(request, 'form_crispy_meetings.html', context)


@login_required
@permission_required('meetings.list_mtgs', raise_exception=True)
def listattendance(request, page=1):
    """ List all meetings """
    context = {}
    mtgs = Meeting.objects \
        .select_related('meeting_type') \
        .annotate(num_attendsees=Count('attendance'))
    inprogress_mtgs = mtgs.filter(datetime__lte=timezone.now()) \
        .filter(datetime__gte=timezone.now() - F('duration') - datetime.timedelta(minutes=5)) \
        .order_by('-datetime')
    past_mtgs = mtgs.filter(datetime__lte=timezone.now() - F('duration') - datetime.timedelta(minutes=5)) \
        .order_by('-datetime')
    future_mtgs = mtgs.filter(datetime__gte=timezone.now()) \
        .order_by('datetime')

    paginated = Paginator(past_mtgs, 10)
    try:
        past_mtgs = paginated.page(page)
    except InvalidPage:
        past_mtgs = paginated.page(1)

    paginated = Paginator(future_mtgs, 10)
    try:
        future_mtgs = paginated.page(page)
    except InvalidPage:
        future_mtgs = paginated.page(1)

    context['lists'] = [("Past Meetings", past_mtgs),
                        ("Future Meetings", future_mtgs)]
    if len(inprogress_mtgs) > 0:
        context['lists'].insert(0, ("Meetings In Progress", inprogress_mtgs))
    return render(request, 'meeting_list.html', context)


@login_required
@permission_required('meetings.create_mtg', raise_exception=True)
def newattendance(request):
    """ Create a new meeting """
    context = {}
    if request.method == 'POST':
        form = MeetingAdditionForm(request.user, request.POST, request.FILES)
        if form.is_valid():
            mtg = form.save()
            for attachment in form.cleaned_data.get('attachments', []):
                MtgAttachment.objects.create(file=attachment, name=attachment.name, author=request.user, private=False,
                                             meeting=mtg)
            for attachment in form.cleaned_data.get('attachments_private', []):
                MtgAttachment.objects.create(file=attachment, name=attachment.name, author=request.user, private=True,
                                             meeting=mtg)
            return HttpResponseRedirect(reverse('meetings:detail', args=(mtg.id,)))
    else:
        form = MeetingAdditionForm(request.user)
    context['form'] = form
    context['msg'] = "New Meeting"
    return render(request, 'form_crispy_meetings.html', context)


class DeleteMeeting(LoginRequiredMixin, HasPermMixin, DeleteView):
    """ Delete a meeting """
    model = Meeting
    template_name = "form_delete_cbv.html"
    msg = "Delete Meeting"
    perms = 'meetings.edit_mtg'
    pk_url_kwarg = "mtg_id"

    def get_success_url(self):
        return reverse("meetings:list")


@login_required
def mknotice(request, mtg_id):
    """ Send a meeting notice """
    context = {}
    perms = ('meetings.send_mtg_notice',)
    meeting = get_object_or_404(Meeting, pk=mtg_id)
    if not (request.user.has_perms(perms) or
            request.user.has_perms(perms, meeting)):
        raise PermissionDenied
    if request.method == 'POST':
        form = AnnounceSendForm(meeting, request.POST)
        if form.is_valid():
            notice = form.save()
            email = generate_notice_email(notice)

            # Generate calendar invite
            invite_filename = 'meeting.ics'
            invite = MIMEBase('text', "calendar", method="PUBLISH", name=invite_filename)
            invite.set_payload(generate_ics([meeting], None))
            encode_base64(invite)
            invite.add_header('Content-Description', 'Add to Calendar')
            invite.add_header('Content-Class', "urn:content-classes:calendarmessage")
            invite.add_header('Filename', invite_filename)
            invite.add_header('Path', invite_filename)
            email.attach(invite)

            res = email.send()
            if res == 1:
                success = True
            else:
                success = False
            AnnounceSend.objects.create(announce=notice, sent_success=success)
            url = reverse('meetings:detail', args=(meeting.id,)) + "#emails"
            return HttpResponseRedirect(url)
    else:
        form = AnnounceSendForm(meeting)
    context['form'] = form
    context['msg'] = "New Meeting Notice"
    return render(request, 'form_crispy_meetings.html', context)


@login_required
def mkccnotice(request, mtg_id):
    """ Send a CC meeting notice """
    context = {}
    perms = ('meetings.send_mtg_notice',)
    meeting = get_object_or_404(Meeting, pk=mtg_id)
    if not (request.user.has_perms(perms) or
            request.user.has_perms(perms, meeting)):
        raise PermissionDenied

    if request.method == 'POST':
        form = AnnounceCCSendForm(meeting, request.POST)
        if form.is_valid():
            notice = form.save()
            email = generate_notice_cc_email(notice)
            res = email.send()
            if res == 1:
                notice.sent_success = True
            else:
                notice.sent_success = False

            notice.save()

            url = reverse('meetings:detail', args=(meeting.id,)) + "#emails"
            return HttpResponseRedirect(url)
    else:
        form = AnnounceCCSendForm(meeting)
    context['form'] = form
    context['msg'] = "CC Meeting Notice"
    return render(request, 'form_crispy_meetings.html', context)


@login_required
def download_invite(request, mtg_id):
    """ Generate and download an ics file """
    meeting = get_object_or_404(Meeting, pk=mtg_id)
    invite = generate_ics([meeting], None)

    response = HttpResponse(invite, content_type="text/calendar")
    response['Content-Disposition'] = "attachment; filename=invite.ics"
    return response

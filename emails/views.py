from django.views.generic.detail import DetailView

from meetings.models import CCNoticeSend, MeetingAnnounce
from .forms import SrvAnnounceSendForm, TargetedSMSForm, SMSForm, PokeCCForm
from .generators import generate_web_service_email, generate_sms_email, generate_poke_cc_email_content, \
    BasicEmailGenerator, GenericEmailGenerator
from slack.api import slack_post
from events.models import BaseEvent
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, reverse
from django.http import HttpResponseRedirect
from django.db.models import Q
from django.utils import timezone
from django.template import loader
from django.http.response import HttpResponse


class MeetingAnnounceView(DetailView):
    model = MeetingAnnounce
    slug_field = "uuid"
    template_name = "emails/email_notice.html"

    # def get_context_data(self, **kwargs):
    # context = super(ArticleDetailView, self).get_context_data(**kwargs)
    # context['now'] = timezone.now()
    # return context


class MeetingAnnounceCCView(DetailView):
    model = CCNoticeSend
    slug_field = "uuid"
    template_name = "emails/email_notice_cc.html"

    # def get_context_data(self, **kwargs):
    # context = super(ArticleDetailView, self).get_context_data(**kwargs)
    # context['now'] = timezone.now()
    # return context


@login_required
def mk_srv_announce(request):
    """ Send out a web service announcement """
    context = {}
    perms = ('meetings.send_mtg_notice',)
    if not (request.user.has_perms(perms)):
        raise PermissionDenied
    if request.method == 'POST':
        form = SrvAnnounceSendForm(request.POST)
        if form.is_valid():
            notice = form.cleaned_data
            email = generate_web_service_email(notice)
            email.send()
            if notice['slack_channel'] not in ['', None]:
                if not request.user.has_perm('slack.post_officer'):
                    messages.add_message(request, messages.WARNING, 'Failed to post to Slack: Permission denied')
                    return HttpResponseRedirect(reverse('home'))
                message = notice['message'].replace('**', '&&').replace('* ', '*&').replace('*', '_')\
                    .replace('_&', '- ').replace('&&', '*').replace('~~', '~')
                response = slack_post(notice['slack_channel'], message, username='LNL Webmaster')
                if not response['ok']:
                    messages.add_message(request, messages.WARNING,
                                         'There was an error posting to Slack: %s' % response['error'])
            return HttpResponseRedirect(reverse('home'))
        else:
            context['form'] = form

    else:
        form = SrvAnnounceSendForm()
        context['form'] = form
        context['msg'] = "Service Announcement"
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('emails.send', raise_exception=True)
def send_sms(request):
    """ Send a text message to a specific user (must have opted-in to receive messages) """
    context = {}
    if request.method == 'POST':
        form = TargetedSMSForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            email = generate_sms_email(data)
            if email is None:
                template = loader.get_template('default.html')
                return HttpResponse(template.render({
                    'title': "Error 403: User Opted Out",
                    'message': "This user has not agreed to receiving text messages through this service, or has not "
                               "provided the required information",
                    'NO_FOOT': True
                }, request))
            email.send()
            return HttpResponseRedirect(reverse('home'))
    else:
        form = TargetedSMSForm()
    context['form'] = form
    context['msg'] = "Send Text Message"
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('emails.send', raise_exception=True)
def send_active_sms(request):
    """ Send a text message to all active members (must have opted-in to receive text messages) """
    context = {}
    if request.method == 'POST':
        form = SMSForm(request.POST)
        if form.is_valid():
            users = get_user_model().objects.filter(Q(groups__name='Active') | Q(groups__name='Officer'),
                                                    phone__isnull=False, carrier__isnull=False).exclude(carrier="")
            if users.count() == 0:
                template = loader.get_template('default.html')
                return HttpResponse(template.render({
                    'title': "Error 204: No contacts found",
                    'message': "Your message could not be sent. 0 active members have opted in to receiving text "
                               "messages.",
                    'NO_FOOT': True
                }, request))
            to_addrs = []
            for user in users:
                to_addrs.append(''.join(e for e in user.phone if e.isalnum()) + "@" + user.carrier)
            email = BasicEmailGenerator(to_emails=None, bcc=to_addrs, body=form.instance.message)
            email.send()
            return HttpResponseRedirect(reverse('home'))
    else:
        form = SMSForm()
    context['form'] = form
    context['msg'] = "Send Text Message to Active Members"
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('events.edit_event_hours', raise_exception=True)
def poke_cc(request):
    """ Send a "Poke for CC" email (searching for crew chiefs) """
    context = {}
    events = BaseEvent.objects.filter(approved=True, closed=False, cancelled=False, test_event=False) \
        .filter(datetime_start__gt=timezone.now()).exclude().distinct()
    if events.count() == 0:
        return render(request, 'default.html',
                      {'title': 'Error 404: No events found', 'NO_FOOT': True,
                       'message': 'It appears there are no events in need of a crew chief'}, status=404)
    if request.method == "POST":
        form = PokeCCForm(request.POST)
        if form.is_valid():
            preview = generate_poke_cc_email_content(form.cleaned_data['events'], form.cleaned_data['message'])
            if request.POST['save'] == "Preview":
                form = PokeCCForm(request.POST, preview=preview)
            else:
                email = GenericEmailGenerator(
                    "Crew Chiefs Needed", request.POST['email_to'], body=preview, reply_to=[settings.EMAIL_TARGET_VP],
                    context={'CUSTOM_URL': True, 'UNSUB': True}
                )
                email.send()
                if form.cleaned_data['slack'] is True:
                    if not request.user.has_perm('slack.post_officer'):
                        messages.add_message(request, messages.WARNING, 'Failed to post to Slack: Permission denied')
                        return HttpResponseRedirect(reverse('home'))
                    body = preview.replace('<strong>', '>*').replace('</strong>', '*').replace("a href='", '')\
                        .replace("'>", '|').replace('</a', '')
                    message = body.split('<hr>')[0]
                    details = body.split('<hr>')[1]
                    blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": message
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": details
                            }
                        },
                    ]
                    response = slack_post(settings.SLACK_TARGET_ACTIVE, message, blocks, username='LNL Vice President')
                    if not response['ok']:
                        messages.add_message(request, messages.WARNING,
                                             'There was an error posting to Slack: %s' % response['error'])
                return HttpResponseRedirect(reverse("home"))
    else:
        form = PokeCCForm()
    context['form'] = form
    context['msg'] = "Poke for Crew Chief"
    return render(request, 'form_crispy.html', context)


@login_required
def dispatch_console(request):
    """ Menu for email tools """
    if not request.user.has_perm('emails.send') and not request.user.has_perm('events.edit_event_hours'):
        raise PermissionDenied
    return render(request, 'email_tools.html', {})

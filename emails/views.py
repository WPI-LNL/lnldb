from django.views.generic import TemplateView
from django.views.generic.detail import DetailView

from meetings.models import CCNoticeSend, MeetingAnnounce
from .models import ServiceAnnounce
from .forms import SrvAnnounceSendForm, TargetedSMSForm, SMSForm
from emails.generators import generate_web_service_email, generate_sms_email, BasicEmailGenerator

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render, reverse
from django.http import HttpResponseRedirect
from django.db.models import Q
from django.template import loader
from django.http.response import Http404, HttpResponse

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
def mkSrvAnnounce(request):
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
                    'message': "This user has not agreed to receiving text messages through this service, or has not provided the required information",
                    'NO_FOOT': True
                }, request))
            email.send()
            return HttpResponseRedirect(reverse('home'))
        else:
            context['form'] = form
            context['msg'] = "Send Text Message"
    else:
        form = TargetedSMSForm()
        context['form'] = form
        context['msg'] = "Send Text Message"
    return render(request, 'form_crispy.html', context)


@login_required
@permission_required('emails.send', raise_exception=True)
def sendActiveSMS(request):
    context = {}
    if request.method == 'POST':
        form = SMSForm(request.POST)
        if form.is_valid():
            users = get_user_model().objects.filter(Q(groups__name='Active') | Q(groups__name='Officer'), phone__isnull=False, carrier__isnull=False)\
                .exclude(carrier="")
            if users.count() == 0:
                template = loader.get_template('default.html')
                return HttpResponse(template.render({
                    'title': "Error 204: No contacts found",
                    'message': "Your message could not be sent. 0 active members have opted in to receiving text messages.",
                    'NO_FOOT': True
                }, request))
            to_addrs = []
            for user in users:
                to_addrs.append(''.join(e for e in user.phone if e.isalnum()) + "@" + user.carrier)
            email = BasicEmailGenerator(to_emails=to_addrs, body=form.instance.message)
            email.send()
            return HttpResponseRedirect(reverse('home'))
        else:
            context['msg'] = "Send Text Message to Active Members"
            context['form'] = form
    else:
        form = SMSForm()
        context['form'] = form
        context['msg'] = "Send Text Message to Active Members"
    return render(request, 'form_crispy.html', context)
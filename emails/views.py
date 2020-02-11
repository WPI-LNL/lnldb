from django.views.generic import TemplateView
from django.views.generic.detail import DetailView

from meetings.models import CCNoticeSend, MeetingAnnounce
from .models import ServiceAnnounce
from .forms import SrvAnnounceSendForm
from emails.generators import generate_web_service_email

from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect
from django.http.response import Http404

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
            res = email.send()
            if res == 1:
                success = True
            else:
                success = False
            return HttpResponseRedirect(r'../../../db/')
        else:
            context['form'] = form

    else:
        form = SrvAnnounceSendForm()
        context['form'] = form
        context['msg'] = "Service Announcement"
    return render(request, 'form_crispy.html', context)

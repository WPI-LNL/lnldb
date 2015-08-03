# Create your views here.
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages

from django.core.urlresolvers import reverse
from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils.safestring import mark_safe

from django.views.generic import UpdateView, CreateView

from acct.forms import UserAcct, ProfileAcct
from acct.forms import UserAddForm
from acct.models import Profile

from emails.generators import generate_selfmember_notice_email

from helpers.mixins import LoginRequiredMixin, SetFormMsgMixin, HasPermMixin
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


class AcctUpdate(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserAcct
    template_name = 'myacct.html'

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Account Info Saved!", extra_tags='success')
        return super(AcctUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse('my-acct')


class LNLUpdate(LoginRequiredMixin, UpdateView):
    model = Profile
    form_class = ProfileAcct
    template_name = 'myacct.html'

    def get_object(self, queryset=None):
        return self.request.user.profile

    def form_valid(self, form):
        messages.success(self.request, "Account Info Saved!", extra_tags='success')
        return super(LNLUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse('my-lnl')


@login_required
def send_member_request(request):
    if not request.user.profile.is_lnl:
        context = {'user': request.user, 'submitted_ip': request.META.get('REMOTE_ADDR')}
        e = generate_selfmember_notice_email(context)
        e.send()
        messages.success(request, "LNL Member Request Sent", extra_tags='success')

        return HttpResponseRedirect(reverse("my-acct"))
    else:
        messages.success(request, "You're already an LNL Member", extra_tags='warning')
        return HttpResponseRedirect(reverse("my-acct"))


class LNLAdd(SetFormMsgMixin, HasPermMixin, LoginRequiredMixin, CreateView):
    model = User
    form_class = UserAddForm
    template_name = "form_master_cbv.html"
    msg = 'New User Addition'
    perms = 'acct.add_user'

    def form_valid(self, form):
        messages.success(self.request, "User Added", extra_tags='success')
        return super(LNLAdd, self).form_valid(form)

    def get_success_url(self):
        return reverse('db')


def smart_login(request):
    pref_cas = request.COOKIES.get('prefer_cas', None)

    if pref_cas == "true":
        return HttpResponseRedirect(reverse('cas-login'))
    else:
        return HttpResponseRedirect(reverse('local-login'))


@receiver(user_logged_in)
def nag_for_contact_info(sender, request, user, **kwargs):
    if not (user.first_name and user.last_name) and not settings.TESTING:
        nagtext = mark_safe('Please visit <a href="' +
                            reverse('my-acct') +
                            '">My Account</a> and update your information')
        messages.warning(request, nagtext)

# Create your views here.
from django.contrib.auth.models import User
from django.contrib import messages

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect

from django.views.generic import UpdateView

from django.forms.models import inlineformset_factory

from acct.forms import UserAcct,ProfileAcct,UserProfileFormSet
from acct.models import Profile

from emails.generators import generate_selfmember_notice_email


class AcctUpdate(UpdateView):
    model = User
    form_class = UserAcct
    template_name = 'myacct.html'
    
    def get_object(self,queryset=None):
        return self.request.user
    
    def form_valid(self,form):
        messages.success(self.request,"Account Info Saved!", extra_tags='success')
        return super(AcctUpdate,self).form_valid(form)
        
    def get_success_url(self):
        return reverse('my')
    
class LNLUpdate(UpdateView):
    model = Profile
    form_class = ProfileAcct
    template_name = 'myacct.html'
    
    def get_object(self,queryset=None):
        return self.request.user.get_profile()
    
    def form_valid(self,form):
        messages.success(self.request,"Account Info Saved!", extra_tags='success')
        return super(LNLUpdate,self).form_valid(form)
        
    def get_success_url(self):
        return reverse('my-lnl')
    
    
def send_member_request(request):
    if request.user.profile.is_lnl:
        context = {}
        context['user'] = request.user
        context['submitted_ip'] = request.META.get('REMOTE_ADDR')
        e = generate_selfmember_notice_email(context)
        e.send()
        messages.success(request,"LNL Member Request Sent", extra_tags='success')
        
        return HttpResponseRedirect(reverse("my-acct"))
    else:
        messages.success(request,"You're already an LNL Member", extra_tags='warning')
        return HttpResponseRedirect(reverse("my-acct"))
    
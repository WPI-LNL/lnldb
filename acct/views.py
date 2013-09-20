# Create your views here.
from django.contrib.auth.models import User
from django.contrib import messages

from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect

from django.views.generic import UpdateView

from django.forms.models import inlineformset_factory

from acct.forms import UserAcct,ProfileAcct,UserProfileFormSet
from acct.models import Profile


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
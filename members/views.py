# Create your views here.
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import Context,RequestContext

from django.views.generic import UpdateView

from members.forms import MemberForm
from members.forms import MemberContact
from members.models import StatusChange

from acct.models import Profile

from django.contrib.auth.models import User
from django.contrib.auth.decorators import permission_required
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages

from helpers.challenges import is_officer
from helpers.mixins import LoginRequiredMixin, OfficerMixin

from events.models import Event,Projection,EventCCInstance 

@login_required
def mdc(request):
    context = RequestContext(request)
    users = User.objects.exclude(profile__mdc__isnull=True).exclude(profile__mdc='').order_by('last_name')


    context['users'] = users
    context['h2'] = "Member MDC List"

    return render_to_response('users_mdc.html', context)

@login_required
def mdc_raw(request):
    context = RequestContext(request)
    users = User.objects.exclude(profile__mdc__isnull=True).exclude(profile__mdc='').order_by('last_name')


    context['users'] = users

    response = render_to_response('users_mdc_raw.csv', context)
    response['Content-Disposition'] = 'attachment; filename="lnl_mdc.csv"'
    response['Content-Type'] = 'text/csv'
    return response


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def officers(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Officer').order_by('last_name')
    
    context['users'] = users
    context['h2'] = "Officer List"
    
    return render_to_response('users.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def active(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Active').order_by('last_name')
    
    context['users'] = users
    context['h2'] = "Active Members"
    
    return render_to_response('users.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def associate(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Associate').order_by('last_name')
    
    context['users'] = users
    context['h2'] = "Associate Members"
    
    return render_to_response('users.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def alum(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Alumni').order_by('last_name')
    
    context['users'] = users
    context['h2'] = "Alumni Members"
    
    return render_to_response('users.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def away(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Away').order_by('last_name')
    
    context['users'] = users
    context['h2'] = "Away Members"
    
    return render_to_response('users.html', context)

@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def inactive(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Inactive').order_by('last_name')
    
    context['users'] = users
    context['h2'] = "Inactive Members"
    
    return render_to_response('users.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def contactusers(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__name='Contact').order_by('last_name')
    
    context['users'] = users
    context['h2'] = "Contact Users"
    
    return render_to_response('users.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def limbousers(request):
    context = RequestContext(request)
    users = User.objects.filter(groups__isnull=True)
    
    context['users'] = users
    context['h2'] = "Users Without Association"
    
    return render_to_response('users.html', context)


@login_required
@user_passes_test(is_officer, login_url='/NOTOUCHING')
def detail(request,id):
    context = RequestContext(request)
    user = get_object_or_404(User,pk=id)
    
    context['u'] = user
    
    moviesccd = Event.objects.filter(crew_chief__id=id,projection__isnull=False)
    
    # for the new style too
    p = Projection.objects.all()
    p_ids = [i.id for i in p]
    moviesccd2 = EventCCInstance.objects.filter(service__in=p_ids,crew_chief=user)
    
    context['moviesccd'] = moviesccd.count() + moviesccd2.count()
    return render_to_response('userdetail.html', context)



class UserUpdate(OfficerMixin,LoginRequiredMixin,UpdateView):
    model = User
    form_class = MemberForm
    template_name = "form_crispy_cbv.html"
    
    def form_valid(self,form):
        user = self.get_object()
        
        # if the groups have changed,
        if 'groups' in form.changed_data:
            newgroups = form.cleaned_data['groups']
            # create tracking instance
            s = StatusChange.objects.create(member=user)
            s.groups.add(*newgroups)
            s.save()
        #x= dir(newgroups)
        
        messages.success(self.request,"Account Info Saved!", extra_tags='success')
        return super(UserUpdate,self).form_valid(form)
    
    def get_success_url(self):
        return reverse('memberdetail',args=(self.object.id,))
    
class MemberUpdate(OfficerMixin,LoginRequiredMixin,UpdateView):
    model = Profile
    form_class = MemberContact
    template_name = "form_crispy_cbv.html"
    
    def form_valid(self,form):
        messages.success(self.request,"Account Info Saved!", extra_tags='success')
        return super(MemberUpdate,self).form_valid(form)
    
    def get_success_url(self):
        return reverse('memberdetail',args=(self.object.user.id,))

    
    
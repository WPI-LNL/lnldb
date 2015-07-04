# Create your views here.
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, render
from django.template import RequestContext

from django.views.generic import UpdateView

from members.forms import MemberForm
from members.forms import MemberContact
from members.models import StatusChange

from acct.models import Profile

from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required, user_passes_test, permission_required
from django.contrib import messages

from helpers.challenges import is_officer
from helpers.mixins import LoginRequiredMixin, HasPermMixin, ConditionalFormMixin

from events.models import Event, Projection, EventCCInstance


@login_required
@permission_required('acct.view_member', raise_exception=True)
def mdc(request):
    context = {}
    users = User.objects.exclude(profile__mdc__isnull=True).exclude(profile__mdc='').order_by('last_name')

    context['users'] = users
    context['h2'] = "Member MDC List"

    return render(request, 'users_mdc.html', context)


@login_required
@permission_required('acct.view_member', raise_exception=True)
def mdc_raw(request):
    context = {}
    users = User.objects.exclude(profile__mdc__isnull=True).exclude(profile__mdc='').order_by('last_name')

    context['users'] = users

    response = render(request, 'users_mdc_raw.csv', context)
    response['Content-Disposition'] = 'attachment; filename="lnl_mdc.csv"'
    response['Content-Type'] = 'text/csv'
    return response


@login_required
@permission_required('acct.view_member', raise_exception=True)
def officers(request):
    context = {}
    users = User.objects.filter(groups__name='Officer').order_by('last_name')

    context['users'] = users
    context['h2'] = "Officer List"

    return render(request, 'users.html', context)


@login_required
@permission_required('acct.view_member', raise_exception=True)
def active(request):
    context = {}
    users = User.objects.filter(groups__name='Active').order_by('last_name')

    context['users'] = users
    context['h2'] = "Active Members"

    return render(request, 'users.html', context)


@login_required
@permission_required('acct.view_member', raise_exception=True)
def associate(request):
    context = {}
    users = User.objects.filter(groups__name='Associate').order_by('last_name')

    context['users'] = users
    context['h2'] = "Associate Members"

    return render(request, 'users.html', context)


@login_required
@permission_required('acct.view_member', raise_exception=True)
def alum(request):
    context = {}
    users = User.objects.filter(groups__name='Alumni').order_by('last_name')

    context['users'] = users
    context['h2'] = "Alumni Members"

    return render(request, 'users.html', context)


@login_required
@permission_required('acct.view_member', raise_exception=True)
def away(request):
    context = {}
    users = User.objects.filter(groups__name='Away').order_by('last_name')

    context['users'] = users
    context['h2'] = "Away Members"

    return render(request, 'users.html', context)


@login_required
@permission_required('acct.view_member', raise_exception=True)
def inactive(request):
    context = {}
    users = User.objects.filter(groups__name='Inactive').order_by('last_name')

    context['users'] = users
    context['h2'] = "Inactive Members"

    return render(request, 'users.html', context)


@login_required
@permission_required('acct.view_user', raise_exception=True)
def contactusers(request):
    context = {}
    users = User.objects.filter(groups__name='Contact').order_by('last_name')

    context['users'] = users
    context['h2'] = "Contact Users"

    return render(request, 'users.html', context)


@login_required
@permission_required('acct.view_user', raise_exception=True)
def limbousers(request):
    context = {}
    users = User.objects.filter(groups__isnull=True)

    context['users'] = users
    context['h2'] = "Users Without Association"

    return render(request, 'users.html', context)


@login_required
def detail(request, id):
    context = {}
    user = get_object_or_404(User, pk=id)
    if not ((user.profile.is_lnl and request.user.has_perm('acct.view_member')) or
                request.user.has_perm('acct.view_user', user.profile)):
        raise PermissionDenied

    context['u'] = user

    moviesccd = Event.objects.filter(crew_chief__id=id, projection__isnull=False)

    # for the new style too
    p = Projection.objects.all()
    p_ids = [i.id for i in p]
    moviesccd2 = EventCCInstance.objects.filter(service__in=p_ids, crew_chief=user)

    context['moviesccd'] = moviesccd.count() + moviesccd2.count()
    return render(request, 'userdetail.html', context)


@login_required
def named_detail(request, username):
    user = get_object_or_404(User, username=username)
    return detail(request, user.pk)


class UserUpdate(LoginRequiredMixin, HasPermMixin, ConditionalFormMixin, UpdateView):
    model = User
    form_class = MemberForm
    template_name = "form_crispy_cbv.html"
    perms = 'acct.edit_user'

    def form_valid(self, form):
        user = self.get_object()

        # if the groups have changed,
        if 'groups' in form.changed_data and 'groups' in form.cleaned_data:
            newgroups = form.cleaned_data['groups']
            # create tracking instance
            s = StatusChange.objects.create(member=user)
            s.groups.add(*newgroups)
            s.save()
        # x= dir(newgroups)

        messages.success(self.request, "Account Info Saved!", extra_tags='success')
        return super(UserUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse('memberdetail', args=(self.object.id,))


class MemberUpdate(LoginRequiredMixin, HasPermMixin, ConditionalFormMixin, UpdateView):
    model = Profile
    form_class = MemberContact
    template_name = "form_crispy_cbv.html"
    perms = 'acct.edit_user'

    def form_valid(self, form):
        messages.success(self.request, "Account Info Saved!", extra_tags='success')
        return super(MemberUpdate, self).form_valid(form)

    def get_success_url(self):
        return reverse('memberdetail', args=(self.object.user.id,))
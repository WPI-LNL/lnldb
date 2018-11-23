from datetime import timedelta
import math

from crispy_forms.helper import FormHelper
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q, Count, Case, When
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils import timezone
from django.views import generic
from django_cas_ng.views import login as cas_login

from data.forms import form_footer
from events.models import Event
from helpers import mixins

from . import forms


class UserAddView(mixins.HasPermMixin, generic.CreateView):
    form_class = forms.UserAddForm
    model = get_user_model()
    perms = 'accounts.add_user'
    template_name = 'form_crispy.html'

    def get_success_url(self):
        return reverse('accounts:detail', args=(self.object.id,))


class UserUpdateView(mixins.HasPermOrTestMixin, mixins.ConditionalFormMixin, generic.UpdateView):
    slug_field = "username"
    slug_url_kwarg = "username"
    model = get_user_model()
    form_class = forms.UserEditForm
    template_name = "form_crispy_cbv.html"
    perms = 'accounts.change_user'

    def user_passes_test(self, request, *args, **kwargs):
        return request.user and request.user.pk == self.get_object().pk

    def get_context_data(self, **kwargs):
        context = super(UserUpdateView, self).get_context_data(**kwargs)
        context['msg'] = "Edit user '%s'" % self.object
        return context

    def form_valid(self, form):
        # if the groups have changed, make a new status change log entry.
        # if 'groups' in form.changed_data and 'groups' in form.cleaned_data:
        #     newgroups = form.cleaned_data['groups']
        #     # create tracking instance
        #     s = StatusChange.objects.create(member=user)
        #     s.groups.add(*newgroups)
        #     s.save()
        # x= dir(newgroups)

        messages.success(self.request, "Account Info Saved!",
                         extra_tags='success')
        return super(UserUpdateView, self).form_valid(form)

    def get_success_url(self):
        return reverse('accounts:detail', args=(self.object.id,))


class UserDetailView(mixins.HasPermOrTestMixin, generic.DetailView):
    slug_field = "username"
    slug_url_kwarg = "username"
    model = get_user_model()
    template_name = "userdetail.html"
    perms = ['accounts.view_user']

    def user_passes_test(self, request, *args, **kwargs):
        # members looking at other members is fine, and you should always be able to look at yourself.
        object = self.get_object()
        if request.user == object:
            return True
        if object.is_lnl:
            return request.user.has_perm('accounts.view_member')
        else:
            return request.user.has_perm('accounts.view_user', object)

    def get_context_data(self, **kwargs):
        context = super(UserDetailView, self).get_context_data(**kwargs)
        context['u'] = u = self.object
        context['hours'] = u.hours.select_related('event', 'service').all()
        context['ccs'] = u.ccinstances.select_related('event').all()

        moviesccd = Event.objects.filter(Q(crew_chief=self.get_object()) | Q(ccinstances__crew_chief=self.get_object()),
                                         projection__isnull=False).distinct()

        context['moviesccd'] = moviesccd.count()
        return context


class BaseUserList(mixins.HasPermMixin, generic.ListView):
    model = get_user_model()
    context_object_name = 'users'
    template_name = 'users.html'
    name = "User List"
    perms = ['accounts.view_user']

    def get_context_data(self, **kwargs):
        context = super(BaseUserList, self).get_context_data(**kwargs)
        context['h2'] = self.name
        return context


class OfficerList(BaseUserList):
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Officer")
    name = "Officer List"


class ActiveList(BaseUserList):
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Active")
    name = "Active List"


class AwayList(BaseUserList):
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Away")
    name = "Away List"


class AssociateList(BaseUserList):
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Associate")
    name = "Associate List"


class AlumniList(BaseUserList):
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Alumni")
    name = "Alumni List"


class InactiveList(BaseUserList):
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Inactive")
    name = "Inactive List"


class AllMembersList(BaseUserList):
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__isnull=False).distinct()
    name = "All Members List"


class LimboList(BaseUserList):
    queryset = get_user_model().objects.filter(groups__isnull=True)
    name = "Users without Association"


class MeDirectView(generic.RedirectView):
    def get_redirect_url(self, *args, **kwargs):
        return super(MeDirectView, self).get_redirect_url(self.request.user.pk, *args, **kwargs)


def smart_login(request):
    pref_cas = request.COOKIES.get('prefer_cas', None)
    use_cas = request.GET.get("force_cas", None)

    next_url = request.GET.get("next", reverse('home'))
    if request.user.is_authenticated:
        return HttpResponseRedirect(next_url)
    if pref_cas == "true" or use_cas == "true" or "ticket" in request.GET:
        return cas_login(request, next_url)
    else:
        return LoginView.as_view(template_name='registration/login.html', authentication_form=forms.LoginForm)(request)


@login_required
@permission_required('accounts.view_member', raise_exception=True)
def mdc(request):
    context = {}
    users_with_mdc = get_user_model().objects.exclude(mdc__isnull=True) \
        .exclude(mdc='').order_by('last_name', 'first_name', 'mdc')
    members_without_mdc = get_user_model().objects.exclude(mdc__isnull=False) \
        .filter(groups__name__in=['Officer', 'Active', 'Away'])

    context['users'] = users_with_mdc
    context['members_without_mdc'] = members_without_mdc
    context['h2'] = "Member MDC List"

    return render(request, 'users_mdc.html', context)


@login_required
@permission_required('accounts.view_member', raise_exception=True)
def mdc_raw(request):
    context = {}
    users = get_user_model().objects.exclude(mdc__isnull=True) \
        .exclude(mdc='').order_by('last_name')

    context['users'] = users

    response = render(request, 'users_mdc_raw.csv', context)
    response['Content-Disposition'] = 'attachment; filename="lnl_mdc.csv"'
    response['Content-Type'] = 'text/csv'
    return response


@login_required
@permission_required('accounts.change_group', raise_exception=True)
def secretary_dashboard(request):
    semester_ago = timezone.now() - timedelta(weeks=17)
    term_ago = timezone.now() - timedelta(weeks=8)

    context = {}
    num_active = get_user_model().objects.filter(groups__name='Active').count()
    simple_majority = int(math.ceil(num_active / 2.0))
    two_thirds_majority = int(math.ceil(num_active * 2 / 3.0))
    members_to_activate = get_user_model().objects.filter(groups__name='Associate') \
        .annotate(hours_count=Count(Case(When(hours__event__datetime_start__gte=semester_ago, then=F('hours'))), distinct=True)).filter(hours_count__gte=5) \
        .annotate(meeting_count=Count(Case(When(meeting__datetime__gte=semester_ago, then=F('meeting'))), distinct=True)).filter(meeting_count__gte=3)
    members_to_deactivate = get_user_model().objects.filter(groups__name='Active').exclude(groups__name='Away') \
        .annotate(hours_count=Count(Case(When(hours__event__datetime_start__gte=term_ago, then=F('hours'))), distinct=True)).filter(hours_count__lt=4) \
        .annotate(meeting_count=Count(Case(When(meeting__datetime__gte=term_ago, meeting__meeting_type__name='General', then=F('meeting'))), distinct=True)).filter(meeting_count__lt=4)

    context['num_active'] = num_active
    context['simple_majority'] = simple_majority
    context['two_thirds_majority'] = two_thirds_majority
    context['members_to_activate'] = members_to_activate
    context['members_to_deactivate'] = members_to_deactivate

    return render(request, 'users_secretary_dashboard.html', context)


@login_required
@permission_required('accounts.view_member', raise_exception=True)
def shame(request):
    context = {}
    worst_cc_report_forgetters = get_user_model().objects.annotate(Count('ccinstances', distinct=True)) \
        .annotate(did_ccreport_count=Count(Case(When(ccinstances__event__ccreport__crew_chief=F('pk'), then=F('ccinstances'))), distinct=True)) \
        .annotate(failed_to_do_ccreport_count=(F('ccinstances__count') - F('did_ccreport_count'))) \
        .annotate(failed_to_do_ccreport_percent=(F('failed_to_do_ccreport_count') * 100 / F('ccinstances__count'))) \
        .order_by('-failed_to_do_ccreport_count', '-failed_to_do_ccreport_percent')[:10]

    context['worst_cc_report_forgetters'] = worst_cc_report_forgetters

    return render(request, 'users_shame.html', context)


class PasswordSetView(generic.FormView):
    model = get_user_model()
    user = None
    template_name = 'form_crispy.html'

    def form_valid(self, form):
        form.save()
        return super(PasswordSetView, self).form_valid(form)

    def get_success_url(self):
        return reverse('accounts:detail', args=[self.user.pk])

    def get_context_data(self, form, **kwargs):
        context = super(PasswordSetView, self).get_context_data(**kwargs)
        context['form'] = form
        form.helper = FormHelper(form)
        form.helper.layout.fields.append(form_footer("Set Password"))
        return context

    def get_form_class(self):
        if self.request.user.is_superuser:
            return SetPasswordForm
        elif self.request.user == self.user:
            if self.user.has_usable_password():
                return PasswordChangeForm
            else:
                return SetPasswordForm
        else:
            raise PermissionDenied

    def get_form_kwargs(self):
        kwargs = super(PasswordSetView, self).get_form_kwargs()
        kwargs['user'] = self.user
        return kwargs

    def dispatch(self, request, pk, *args, **kwargs):
        self.user = get_object_or_404(get_user_model(), pk=int(pk))
        return super(PasswordSetView, self).dispatch(request, pk, *args, **kwargs)

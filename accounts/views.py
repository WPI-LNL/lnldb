from datetime import timedelta
import math

from crispy_forms.helper import FormHelper
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.models import Group
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q, Count, Case, When, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls.base import reverse
from django.utils import timezone
from django.views import generic
from django_saml2_auth.views import signin as saml_login

from data.forms import form_footer
from emails.generators import DefaultLNLEmailGenerator
from events.models import Event2019, OfficeHour, CCReport
from helpers import mixins, challenges
from slack.api import lookup_user, user_profile, check_presence, user_add, user_kick

from . import forms
from .models import OfficerImg, UserPreferences


class UserAddView(mixins.HasPermMixin, generic.CreateView):
    """Add a new user manually (should rarely be used - LDAP does this for us)"""
    form_class = forms.UserAddForm
    model = get_user_model()
    perms = 'accounts.add_user'
    template_name = 'form_crispy.html'

    def get_success_url(self):
        return reverse('accounts:detail', args=(self.object.id,))


class UserUpdateView(mixins.HasPermOrTestMixin, mixins.ConditionalFormMixin, generic.UpdateView):
    """Update user profile"""
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
        # if the person was just changed from unaffiliated to an associate member, send them an email.
        if 'groups' in form.changed_data and 'groups' in form.cleaned_data:
            oldgroups = form.initial['groups']
            newgroups = form.cleaned_data['groups']
            if not oldgroups and Group.objects.get(name='Associate') in newgroups:
                email = DefaultLNLEmailGenerator(
                    subject="Welcome to LNL!",
                    to_emails=[self.object.email],
                    bcc=[settings.EMAIL_TARGET_S],
                    reply_to=[settings.EMAIL_TARGET_S],
                    context={'new_member': self.object},
                    template_basename='emails/email_welcome'
                )
                email.send()
                messages.success(self.request, "Welcome email sent")

            exec_group = Group.objects.get(name="Officer")
            if exec_group not in newgroups:
                # Ensure that title is stripped when no longer an officer
                self.object.title = None
                self.object.save()

                # Kick user from exec chat in Slack (if applicable)
                slack_user = lookup_user(self.object.email)
                if slack_user and exec_group in oldgroups:
                    user_kick(settings.SLACK_TARGET_EXEC, slack_user)
            elif exec_group not in oldgroups:
                # Attempt to add user to exec chat in Slack
                slack_user = lookup_user(self.object.email)
                if slack_user:
                    user_add(settings.SLACK_TARGET_EXEC, slack_user)

            # TODO: Add new active members to the active channel in Slack (and remove inactive / alumni etc.)

        messages.success(self.request, "Account Info Saved!", extra_tags='success')
        return super(UserUpdateView, self).form_valid(form)

    def get_success_url(self):
        return reverse('accounts:detail', args=(self.object.id,))


class UserDetailView(mixins.HasPermOrTestMixin, generic.DetailView):
    """View user profile"""
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
        context['hours'] = u.hours.filter(hours__isnull=False).select_related('event', 'service', 'category')
        context['hour_total'] = u.hours.aggregate(hours=Sum('hours'))
        context['ccs'] = u.ccinstances.select_related('event').all()

        slack_id = lookup_user(u.email)
        slack_profile = user_profile(slack_id)
        if slack_profile['ok']:
            context['slack_id'] = slack_id
            context['slack_username'] = slack_profile['user']['name']
            context['slack_active'] = check_presence(slack_id)

        pending_reports = []
        for instance in context['ccs']:
            if not CCReport.objects.all().filter(crew_chief=u, event=instance.event).exists():
                event = instance.event
                if event.datetime_end < timezone.now() and not event.reviewed and not event.closed and \
                        not event.cancelled:
                    pending_reports.append(instance)
        context['pending_reports'] = pending_reports

        context['active'] = self.get_object().is_active

        moviesccd = Event2019.objects.filter(ccinstances__crew_chief=self.get_object(),
                                             serviceinstance__service__category__name="Projection").distinct()

        context['moviesccd'] = moviesccd.count()

        hours = OfficeHour.objects.filter(officer=u)
        output = []
        for hour in hours:
            output.append((hour.get_day, hour.hour_start, hour.hour_end))
        context['office_hours'] = output

        return context


class BaseUserList(mixins.HasPermMixin, generic.ListView):
    """Basic structure for user lists"""
    model = get_user_model()
    context_object_name = 'users'
    template_name = 'users.html'
    name = "User List"
    perms = ['accounts.view_user']

    def get_context_data(self, **kwargs):
        context = super(BaseUserList, self).get_context_data(**kwargs)
        context['h2'] = self.name
        context['accounts_disabled_column'] = self.accounts_disabled_column
        context['positions_column'] = self.positions
        return context


class OfficerList(BaseUserList):
    """Lists LNL officers"""
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Officer")
    name = "Officer List"
    accounts_disabled_column = False
    positions = True


class ActiveList(BaseUserList):
    """Lists active LNL members"""
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Active")
    name = "Active List"
    accounts_disabled_column = False
    positions = False


class AwayList(BaseUserList):
    """Lists LNL members on away status"""
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Away")
    name = "Away List"
    accounts_disabled_column = False
    positions = False


class AssociateList(BaseUserList):
    """Lists associate LNL members"""
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Associate")
    name = "Associate List"
    accounts_disabled_column = False
    positions = False


class AlumniList(BaseUserList):
    """Lists LNL alumni"""
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Alumni")
    name = "Alumni List"
    accounts_disabled_column = False
    positions = False


class InactiveList(BaseUserList):
    """Lists inactive LNL members"""
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__name="Inactive")
    name = "Inactive List"
    accounts_disabled_column = True
    positions = False


class AllMembersList(BaseUserList):
    """Lists all LNL members"""
    perms = ['accounts.view_member']
    queryset = get_user_model().objects.filter(groups__isnull=False).distinct()
    name = "All Members List"
    accounts_disabled_column = False
    positions = False


class LimboList(BaseUserList):
    """Lists unassociated users"""
    queryset = get_user_model().objects.filter(groups__isnull=True)
    name = "Users without Association"
    accounts_disabled_column = False
    positions = False


class MeDirectView(mixins.LoginRequiredMixin, generic.RedirectView):
    """Redirects to a user's profile page"""
    def get_redirect_url(self, *args, **kwargs):
        return super(MeDirectView, self).get_redirect_url(self.request.user.pk, *args, **kwargs)


def smart_login(request):
    """
    Intelligent signin handler. Presents the `Sign in with Microsoft` option if enabled. If already logged in,
    redirects to the requested page (can be used to check for an active session). Also checks for the `Prefer SAML`
    cookie and automatically attempts to log in via Microsoft SSO if present. Falls back on Django's native login form
    otherwise.
    """
    pref_saml = request.COOKIES.get('prefer_saml', None)
    use_saml = request.GET.get('force_saml', None)

    next_url = request.GET.get('next', reverse('home'))
    if request.user.is_authenticated:
        return HttpResponseRedirect(next_url)
    if settings.SAML2_ENABLED and use_saml == "true":
        return saml_login(request)
    if settings.SAML2_ENABLED and pref_saml == "true":
        return saml_login(request)
    else:
        return LoginView.as_view(template_name='registration/login.html', authentication_form=forms.LoginForm)(request)


@login_required
@permission_required('accounts.view_member', raise_exception=True)
def mdc(request):
    """Displays a list of radio MDCs for LNL members"""
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
    """Downloads a CSV file containing the radio MDCs of LNL members"""
    context = {}
    users = get_user_model().objects.exclude(mdc__isnull=True) \
        .exclude(mdc='').order_by('last_name')

    context['users'] = users

    response = render(request, 'users_mdc_raw.csv', context)
    response['Content-Disposition'] = 'attachment; filename="lnl_mdc.csv"'
    response['Content-Type'] = 'text/csv'
    return response


@login_required
@permission_required('accounts.change_membership', raise_exception=True)
def secretary_dashboard(request):
    """
    Dashboard for the secretary. Lists important member counts used in voting and suggests users to activate,
    deactivate, associate, or take off away status.
    """
    semester_ago = timezone.now() - timedelta(weeks=17)
    term_ago = timezone.now() - timedelta(weeks=8)

    context = {}
    num_active = get_user_model().objects.filter(groups__name='Active').count()
    simple_majority = int(math.ceil(num_active / 2.0))
    two_thirds_majority = int(math.ceil(num_active * 2 / 3.0))
    members_to_activate = get_user_model().objects.filter(groups__name='Associate') \
        .annotate(hours_count=Count(Case(When(hours__event__datetime_start__gte=semester_ago, then=F('hours'))),
                                    distinct=True)).filter(hours_count__gte=5) \
        .annotate(
        meeting_count=Count(Case(When(meeting__datetime__gte=semester_ago, then=F('meeting'))), distinct=True)).filter(
        meeting_count__gte=3)
    members_to_deactivate = get_user_model().objects.filter(groups__name='Active').exclude(groups__name='Away') \
        .annotate(hours_count=Count(Case(When(hours__event__datetime_start__gte=term_ago, then=F('hours'))),
                                    distinct=True)).filter(hours_count__lt=4) \
        .annotate(meeting_count=Count(
        Case(When(meeting__datetime__gte=term_ago, meeting__meeting_type__name='General', then=F('meeting'))),
        distinct=True)).filter(meeting_count__lt=4)
    members_to_associate = get_user_model().objects.filter(groups=None).filter(
        Q(meeting__datetime__gte=term_ago) | Q(hours__event__datetime_start__gte=term_ago)).distinct()
    members_on_away = get_user_model().objects.filter(groups__name='Away', away_exp__isnull=False)

    context['num_active'] = num_active
    context['simple_majority'] = simple_majority
    context['two_thirds_majority'] = two_thirds_majority
    context['members_to_activate'] = members_to_activate
    context['members_to_deactivate'] = members_to_deactivate
    context['members_to_associate'] = members_to_associate
    context['members_on_away'] = members_on_away

    return render(request, 'users_secretary_dashboard.html', context)


@login_required
@permission_required('accounts.view_member', raise_exception=True)
def shame(request):
    """
    The LNL Crew Chief Report Hall of Shame. Tracks members who fail to complete event reports and lists the top 10
    on a leaderboard.
    """
    context = {}
    worst_cc_report_forgetters = get_user_model().objects.annotate(Count('ccinstances', distinct=True)).annotate(
        did_ccreport_count=Count(Case(When(ccinstances__event__ccreport__crew_chief=F('pk'), then=F('ccinstances'))),
                                 distinct=True)).annotate(
        failed_to_do_ccreport_count=(F('ccinstances__count') - F('did_ccreport_count'))).annotate(
        failed_to_do_ccreport_percent=(F('failed_to_do_ccreport_count') * 100 / F('ccinstances__count'))).order_by(
        '-failed_to_do_ccreport_count', '-failed_to_do_ccreport_percent')[:10]

    context['worst_cc_report_forgetters'] = worst_cc_report_forgetters

    return render(request, 'users_shame.html', context)


class PasswordSetView(generic.FormView):
    """Set a non-SSO login password"""
    model = get_user_model()
    user = None
    template_name = 'form_crispy.html'

    def form_valid(self, form):
        form.save()
        return super(PasswordSetView, self).form_valid(form)

    def get_success_url(self):
        return reverse('accounts:detail', args=[self.user.pk])

    def get_context_data(self, **kwargs):
        context = super(PasswordSetView, self).get_context_data(**kwargs)
        form = self.get_form()
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


@login_required
def user_preferences(request):
    """Update a user's account preferences (only visible to the user)"""
    context = {'title': 'My Preferences', 'submit_btn': {'text': 'Save'}}
    user = request.user
    user_inactive = 'Inactive' in user.group_str or 'Unclassified' in user.group_str

    context['user'] = user
    prefs, created = UserPreferences.objects.get_or_create(user=request.user)
    form = forms.UserPreferencesForm(instance=prefs)
    if request.POST:
        form = forms.UserPreferencesForm(request.POST, instance=prefs)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.event_edited_field_subscriptions += ['location', 'datetime_setup_complete', 'datetime_start', 'datetime_end']
            if not user_inactive:
                obj.cc_needed_subscriptions = ['email', 'slack']
            if request.POST.get('submit', None) == 'rt-delete':
                obj.rt_token = None
                obj.save()
                return HttpResponseRedirect(reverse("accounts:preferences"))
            obj.save()
            messages.success(request, "Your preferences have been updated successfully!")
            return HttpResponseRedirect(reverse("accounts:detail", args=[user.pk]))
        else:
            form_data = form.cleaned_data
            form_data['srv'] = ['email', 'slack', 'sms']
            if not user_inactive:
                form_data['cc_needed_subscriptions'] = ['email', 'slack']
            form.data = form_data
    context['form'] = form
    return render(request, 'form_semanticui.html', context)


@login_required
@permission_required('accounts.change_membership', raise_exception=True)
def officer_photos(request, pk=None):
    """Update officer headshot (displayed on the main LNL website about page)"""
    context = {}
    if pk is None:
        pk = request.user.pk
    officer = get_object_or_404(get_user_model(), pk=pk)
    if not challenges.is_officer(officer):
        messages.add_message(request, messages.ERROR, 'This feature is not available for this user.')
        return HttpResponseRedirect(reverse("home"))

    context['officer'] = officer
    img = OfficerImg.objects.filter(officer=officer).first()
    form = forms.OfficerPhotoForm(instance=img)

    if request.method == "POST":
        form = forms.OfficerPhotoForm(request.POST, request.FILES, instance=img)
        if request.POST['save'] == "Remove":
            img = OfficerImg.objects.filter(officer=officer).first()
            if img is not None:
                img.delete()
                messages.success(request, "Your profile photo was removed successfully!", extra_tags='success')
            return HttpResponseRedirect(reverse("accounts:detail", args=[officer.pk]))
        if form.is_valid():
            form.instance.officer = officer
            form.save()
            messages.success(request, "Your profile photo was updated successfully!", extra_tags='success')
            return HttpResponseRedirect(reverse("accounts:detail", args=[officer.pk]))
        else:
            context['form'] = form
    else:
        context['form'] = form
    return render(request, 'form_crispy.html', context)


@login_required
def application_scope_request(request):
    """
    Prompt the user to allow applications connected to the LNLDB to interact with one another. Redirects to the
    application's callback uri.
    """

    context = {}
    app_parameters = request.session
    try:
        context['app'] = app_parameters['app']
        context['resource'] = app_parameters['resource']
        context['icon'] = app_parameters['icon']
        context['scopes'] = app_parameters['scopes']
        context['callback_uri'] = app_parameters['callback_uri']
        inverted = app_parameters['inverted']
    except KeyError:
        return HttpResponseRedirect(reverse("home"))

    del request.session['app']
    del request.session['resource']
    del request.session['icon']
    del request.session['scopes']
    del request.session['callback_uri']
    del request.session['inverted']

    invert = False
    prefs = UserPreferences.objects.get_or_create(user=request.user)
    if inverted:
        invert = True
    elif inverted is None:
        invert = prefs.theme == "dark"
    context['inverted'] = invert
    return render(request, 'scope_request.html', context)

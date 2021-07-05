import datetime
from random import randint

from django.shortcuts import get_object_or_404, render, reverse
from django.utils import timezone
from django.http import HttpResponseRedirect
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from formtools.wizard.views import SessionWizardView

from events.models import BaseEvent
from emails.generators import generate_sms_email
from pages.models import Page, OnboardingScreen
from pages.forms import OnboardingContactInfoForm, OnboardingUserInfoForm, SMSVerificationForm
from accounts.models import PhoneVerificationCode
from accounts.ldap import get_student_id
from processors import navs
from helpers.mixins import LoginRequiredMixin


def page(request, slug):
    """ Generate custom page """
    context = {}
    page_obj = get_object_or_404(Page, slug=slug)
    nav = navs(request)
    context['page'] = page_obj
    context['title'] = page_obj.title
    context['description'] = page_obj.description
    context['styles'] = page_obj.css
    context['noindex'] = page_obj.noindex
    # the processors are on crack :-\
    context['navs'] = nav
    return render(request, 'static_page.html', context, )
    # context_instance=context)


@require_GET
@login_required
def onboarding_screen(request, slug):
    """ Generate and display an onboarding screen """
    context = {}
    screen_obj = get_object_or_404(OnboardingScreen, slug=slug)
    if request.user not in screen_obj.users.all() and \
            len(set(request.user.groups.all()).intersection(screen_obj.groups.all())) == 0:
        raise PermissionDenied
    context['page'] = screen_obj
    context['title'] = screen_obj.title
    context['noindex'] = True
    context['next_href'] = request.GET.get('next', reverse('home'))
    return render(request, 'onboarding.html', context)


@login_required
def new_member_welcome(request):
    """ Welcome message for new members that kicks off the onboarding process """
    context = {
        'format': 'title',
        'page': {
            'inverted': True,
            'title': 'Welcome to Lens&nbsp;and&nbsp;Lights!',
            'subtitle': 'Let\'s finish getting you set up',
            'btn_color': 'yellow',
            'btn_txt': 'Get Started',
            'skip_btn': True,
            'skip_color': '#999',
            'skip_href': reverse('home')
        },
        'next_href': reverse('pages:onboarding-wizard')
    }
    return render(request, 'onboarding.html', context)


class OnboardingWizard(SessionWizardView, LoginRequiredMixin):
    """ Onboarding wizard which helps guide new LNL members through setting up their accounts """
    template_name = 'onboarding.html'
    form_list = [OnboardingUserInfoForm, OnboardingContactInfoForm]

    def get_form_instance(self, step):
        self.instance_dict = {'0': self.request.user}
        return super().get_form_instance(step)

    def get_form_initial(self, step):
        if settings.SYNC_STUDENT_ID:
            self.initial_dict = {
                '0': {'student_id': get_student_id(self.request.user.username)},
                '1': {'phone': self.request.user.phone}
            }
        else:
            self.initial_dict = {'1': {'phone': self.request.user.phone}}
        return super().get_form_initial(step)

    def get_form_kwargs(self, step=None):
        if self.request.user.addr and step == '1':
            return {'has_address': True}
        elif step == '1':
            return {'has_address': False}
        if step == '2':
            return {'user': self.request.user}
        return {}

    def process_step(self, form):
        if self.steps.current == '1':
            # Process contact info step
            sms_enabled = form.cleaned_data['sms']
            self.request.user.phone = form.cleaned_data['phone']

            # If phone number has not been provided the user cannot enroll in SMS messaging
            if form.cleaned_data['phone'] in [None, '']:
                sms_enabled = 'False'
            if sms_enabled == 'True':
                self.request.user.carrier = form.cleaned_data['carrier']
            else:
                self.request.user.carrier = ''
            self.request.user.save()

            # Add or remove the SMS verification form based on whether or not the user opted in or out
            end = len(self.form_list)
            exists = False
            for i in range(end):
                if self.form_list[str(i)] == SMSVerificationForm:
                    exists = True
                    if sms_enabled == 'False':
                        del self.form_list[str(i)]
            if sms_enabled == 'True':
                if not exists:
                    self.form_list[str(end)] = SMSVerificationForm

                # Generate and send the user the verification code
                code = randint(100000, 999999)
                message = {
                    "user": self.request.user,
                    "message": str(code) + "\nUse this code for LNL verification"
                }
                email = generate_sms_email(message)
                email.send()
                existing_code = PhoneVerificationCode.objects.filter(user=self.request.user).first()
                if existing_code:
                    existing_code.delete()
                PhoneVerificationCode.objects.create(user=self.request.user, code=code)

                # Ensure carrier field is set to "Opt out" until the user has verified their phone number
                self.request.user.carrier = ''
                self.request.user.save()
        return self.get_form_step_data(form)

    def done(self, form_list, **kwargs):
        form_data = [form.cleaned_data for form in form_list]
        contact_info = form_data[1]
        for form in form_list:
            form.save()
        if contact_info['address'] or contact_info['city'] or contact_info['state']:
            if contact_info['address'] and contact_info['line_2']:
                line_1 = ', '.join([contact_info['address'], contact_info['line_2']])
            else:
                line_1 = contact_info['address'] + contact_info['line_2']
            if contact_info['city'] and contact_info['state']:
                line_2 = ', '.join([contact_info['city'], contact_info['state']])
            else:
                line_2 = contact_info['city'] + contact_info['state']
            address = '\n'.join([line_1, line_2]).strip('\n')
            self.request.user.addr = address
        if contact_info['sms'] == 'True' and contact_info['phone']:
            self.request.user.carrier = contact_info['carrier']
        self.request.user.onboarded = True
        self.request.user.save()
        messages.success(self.request, 'Success! Your profile has been updated.')
        return HttpResponseRedirect(reverse('home'))


@require_GET
def recruitment_page(request):
    """ Serve LNL's join page with list of upcoming or ongoing events """
    now = timezone.now()
    five_days_from_now = now + datetime.timedelta(days=5)
    events = BaseEvent.objects\
        .filter(approved=True, cancelled=False, sensitive=False, test_event=False, closed=False)\
        .filter(datetime_end__gte=now, ccinstances__setup_start__lte=five_days_from_now)\
        .order_by('datetime_start').distinct()
    return render(request, 'recruitment.html', {'events': events})

from django import forms
from django.forms.widgets import RadioSelect
from django.core.validators import MinLengthValidator, MaxLengthValidator
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone

from accounts.models import carrier_choices, PhoneVerificationCode
from accounts.ldap import get_student_id


class OnboardingUserInfoForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'_no_label': True,
                                                                               'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'_no_label': True,
                                                                              'placeholder': 'Last Name'}))
    nickname = forms.CharField(max_length=32, required=False, widget=forms.TextInput(attrs={'placeholder': 'Nickname'}))
    email = forms.EmailField(required=True)
    class_year = forms.CharField(validators=[MinLengthValidator(4), MaxLengthValidator(4)],
                                 widget=forms.NumberInput(attrs={'placeholder': 'Class Year',
                                                                 '_field_class': 'five wide field'}))
    student_id = forms.CharField(validators=[MinLengthValidator(9), MaxLengthValidator(9)], required=False,
                                 widget=forms.NumberInput(attrs={'_no_label': True, 'placeholder': 'Student ID'}))
    wpibox = forms.IntegerField(required=False, widget=forms.NumberInput(attrs={'_no_label': True,
                                                                                'placeholder': 'WPI Box Number'}))

    def clean_student_id(self):
        if settings.SYNC_STUDENT_ID:
            uid = get_student_id(self.instance.username)
            if uid and (self.cleaned_data['student_id'] == uid or not self.cleaned_data['student_id']):
                return int(uid)
        if self.cleaned_data['student_id'] not in ['', None]:
            return self.cleaned_data['student_id']
        return None

    class Meta:
        model = get_user_model()
        fields = ('first_name', 'last_name', 'nickname', 'email', 'class_year', 'student_id', 'wpibox')
        layout = [
            ("Text", "<h4 class=\"ui dividing header\">Personal Information</h4>"),
            ("Text", "<div class=\"field\"><label>Name <span style=\"color: red\">*</span></label>"),
            ("Two Fields",
             ("Field", "first_name"),
             ("Field", "last_name"),
             ),
            ("Text", "</div>"),
            ("Field", "nickname"),
            ("Field", "email"),
            ("Text", "<br><h4 class=\"ui dividing header\">Student Information</h4>"),
            ("Field", "class_year"),
            ("Two Fields",
             ("Text", "<div class=\"field\"><label>Student ID</label>"),
             ("Field", "student_id"),
             ("Text", "</div><div class=\"field\"><label>WPI Box Number</label>"),
             ("Field", "wpibox"),
             ("Text", "</div>"),
             )
        ]


class SUIRadio(RadioSelect):
    template_name = "semantic_ui/semantic-radio.html"
    option_template_name = "semantic_ui/semantic-option.html"


class OnboardingContactInfoForm(forms.Form):
    address = forms.CharField(max_length=128, required=False, widget=forms.TextInput(attrs={
        '_no_label': True, 'placeholder': 'Street Address / Office #', '_field_class': 'twelve wide field'
    }))
    line_2 = forms.CharField(max_length=32, required=False, widget=forms.TextInput(attrs={
        '_no_label': True, 'placeholder': 'Building, Apt. #, etc.', '_field_class': 'four wide field'
    }))
    city = forms.CharField(max_length=32, required=False, widget=forms.TextInput(attrs={
        '_no_label': True, 'placeholder': 'City'
    }))
    state = forms.CharField(max_length=32, required=False, widget=forms.TextInput(attrs={
        '_no_label': True, 'placeholder': 'State'
    }))
    phone = forms.CharField(required=False, widget=forms.NumberInput(attrs={'placeholder': '10-digit phone number'}),
                            validators=[MinLengthValidator(10), MaxLengthValidator(10)])
    sms = forms.ChoiceField(choices=((True, 'Yes, I consent to receiving text messages from LNL'),
                                     (False, 'No, I do not wish to receive text messages from LNL at this time')),
                            initial=True, required=False, widget=SUIRadio(attrs={'_no_label': True}))
    carrier = forms.ChoiceField(choices=(('', 'Please select your carrier...'),) + carrier_choices[1:], required=False)

    def __init__(self, has_address, *args, **kwargs):
        super(OnboardingContactInfoForm, self).__init__(*args, **kwargs)

        if has_address:
            self.fields['address'].widget.attrs['readonly'] = True
            self.fields['address'].widget.attrs['placeholder'] = 'Already Complete'
            self.fields['address'].widget.attrs['_icon'] = 'check circle outline'
            self.fields['line_2'].widget.attrs['_field_class'] = 'hidden'
            self.fields['city'].widget.attrs['_field_class'] = 'hidden'
            self.fields['state'].widget.attrs['_field_class'] = 'hidden'

    def save(self):
        pass

    def clean_carrier(self):
        sms = self.cleaned_data.get('sms')
        carrier = self.cleaned_data.get('carrier')
        if sms == 'True' and not carrier:
            raise ValidationError('Please select your cellular carrier')
        return carrier

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        sms = self.cleaned_data.get('sms')
        if sms == 'True' and phone in [None, '']:
            raise ValidationError('To receive SMS text messages from LNL you must provide your phone number')
        return phone

    class Meta:
        layout = [
            ("Text", "<h4 class=\"ui dividing header\">Contact Information</h4>"),
            ("Text", "<div class=\"field\"><label>Address / Office Location</label>"),
            ("Two Fields",
             ("Field", "address"),
             ("Field", "line_2"),
             ),
            ("Two Fields",
             ("Field", "city"),
             ("Field", "state"),
             ),
            ("Text", "</div>"),
            ("Field", "phone"),
            ("Text", "<br>"),
            ("Text", "<div class=\"field\"><label>Consent to receive text messages from LNL</label>"),
            ("Text", "<p style=\"color: black\">LNL may periodically send you SMS text messages containing information "
                     "about your business with us. This method of communication will never be used for marketing "
                     "purposes and you may opt out at any time.</p></div>"),
            ("Field", "sms"),
            ("Field", "carrier"),
            ("Text", "<p style=\"color: darkgrey; padding-top: 2%; padding-bottom: 1%\">By clicking next you agree to "
                     "our <a href='https://lnl.wpi.edu/legal/privacy/' target='_blank'>Privacy Policy</a></p>")
        ]


class SMSVerificationForm(forms.Form):
    code = forms.CharField(widget=forms.NumberInput(attrs={'_no_label': True}),
                           validators=[MinLengthValidator(6), MaxLengthValidator(6)])

    def __init__(self, user, *args, **kwargs):
        super(SMSVerificationForm, self).__init__(*args, **kwargs)
        self.user = user

    def clean_code(self):
        code = PhoneVerificationCode.objects.get(user=self.user)
        if int(self.cleaned_data.get('code')) != code.code:
            raise ValidationError('Invalid code')
        if code.timestamp < timezone.now() - timezone.timedelta(minutes=30):
            raise ValidationError('This code has expired. Please go back and try again.')
        return self.cleaned_data.get('code')

    def save(self):
        code = PhoneVerificationCode.objects.get(user=self.user)
        code.delete()

    class Meta:
        layout = [
            ("Text", "<br><h4 class=\"ui dividing header\">SMS Verification</h4>"),
            ("Text", "<p>A verification code was just sent to your phone. Check your messages and enter the "
                     "6-digit code below.</p>"),
            ("Field", "code"),
            ("Text", "<div class='ui tiny message'>Didn't get your code? It may take a few minutes, so be patient. If "
                     "after a few minutes you still haven't received your code, make sure you've entered your phone "
                     "number correctly then try again.</div>")
        ]

import re
from django import forms
from django.db.models import Q
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Submit, Layout, HTML, Row, Column, Hidden
from crispy_forms.bootstrap import FormActions

from . import models


class SpotifySessionForm(forms.ModelForm):
    def __init__(self, request_user, *args, **kwargs):
        super(SpotifySessionForm, self).__init__(*args, **kwargs)
        self.user = request_user
        self.helper = FormHelper()
        self.helper.form_class = 'container'
        self.helper.layout = Layout(
            HTML("<hr>"),
            Field('user'),
            Field('accepting_requests'),
            Field('allow_explicit'),
            Field('auto_approve'),
            Field('private'),
            HTML('<br><hr><h3>Payment Details</h3><br>'),
            Field('require_payment'),
            Field('allow_silence'),
            HTML('<br>'),
            Field('paypal'),
            Row(
                Column(
                    Field('venmo'),
                    css_class="col-md-6"
                ),
                Column(
                    Field('venmo_verification'),
                    css_class="col-md-6"
                )
            ),
            FormActions(
                Submit('save', 'Save Session')
            )
        )
        self.fields['user'].queryset = models.SpotifyUser.objects.filter(token_info__isnull=False)\
            .filter(Q(personal=False) | Q(user=request_user))
        self.fields['allow_silence'].label = "Can request silence ($5)"
    user = forms.ModelChoiceField(queryset=models.SpotifyUser.objects.filter(token_info__isnull=False, personal=False),
                                  label="Spotify Account")
    auto_approve = forms.BooleanField(required=False, label="Automatically approve requests")
    private = forms.BooleanField(required=False, label="Restrict to LNL members")

    paypal = forms.URLField(
        label="PayPal.Me Link", required=False,
        help_text="Don't have one? <a href='https://www.paypal.com/paypalme/' target='_blank'>Create one</a>"
    )

    venmo_verification = forms.CharField(help_text="Last 4 digits of your phone number", required=False)

    def clean_paypal(self):
        paypal = self.cleaned_data['paypal']
        if not re.match(r"^https://paypal.me/[0-9a-zA-Z-_]*", paypal) and paypal not in [None, '']:
            raise forms.ValidationError('Invalid PayPal.Me link')

        if paypal and paypal[-1] == "/":
            paypal = paypal[:-1]
        return paypal

    class Meta:
        fields = ('user', 'accepting_requests', 'allow_explicit', 'require_payment', 'auto_approve', 'private',
                  'allow_silence', 'paypal', 'venmo', 'venmo_verification')
        model = models.Session


class SongRequestForm(forms.ModelForm):
    def __init__(self, session, *args, **kwargs):
        super(SongRequestForm, self).__init__(*args, **kwargs)
        self.session = session
        self.helper = FormHelper()
        self.helper.form_tag = False
        if self.session.allow_silence:
            request_type = Field('request_type')
        else:
            request_type = Hidden('request_type', "track")
        self.helper.layout = Layout(
            HTML('<div class="row"><div class="col-md-6">'),
            Field('first_name'),
            HTML('</div><div class="col-md-6">'),
            Field('last_name'),
            HTML('</div></div><div class="row"><div class="col-md-6">'),
            Field('email', placeholder='Ex: rhgoddard@wpi.edu'),
            HTML('</div><div class="col-md-6">'),
            Field('phone', placeholder='(123) 456-7890'),
            HTML('</div></div><br>'),
            Row(
                Column(
                    request_type,
                    css_class="col-md-6"
                )
            )
        )

    first_name = forms.CharField(max_length=74, widget=forms.TextInput(attrs={'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=74, widget=forms.TextInput(attrs={'placeholder': 'Last Name'}))
    request_type = forms.ChoiceField(choices=(
        ("track", " Request a song ($1.00)"), ("silence", " Request 1 minute of silence ($5.00)")
    ), label="I would like to: ", widget=forms.RadioSelect(), initial="track")

    def clean(self):
        if self.cleaned_data['email'] in ['', None] and self.cleaned_data['phone'] in ['', None]:
            raise forms.ValidationError('Please supply an email address or phone number. We will only use this '
                                        'information to contact you if there is a problem with your request.')
        return self.cleaned_data

    class Meta:
        fields = ('email', 'phone')
        model = models.SongRequest

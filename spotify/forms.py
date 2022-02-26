from django import forms
from django.db.models import Q
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Field, Submit, Layout, HTML
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
            Field('require_payment'),
            FormActions(
                Submit('save', 'Save Session')
            )
        )
        self.fields['user'].queryset = models.SpotifyUser.objects.filter(token_info__isnull=False)\
            .filter(Q(personal=False) | Q(user=request_user))
    user = forms.ModelChoiceField(queryset=models.SpotifyUser.objects.filter(token_info__isnull=False, personal=False),
                                  label="Spotify Account")
    auto_approve = forms.BooleanField(required=False, label="Automatically approve requests")
    private = forms.BooleanField(required=False, label="Restrict to LNL members")

    class Meta:
        fields = ('user', 'accepting_requests', 'allow_explicit', 'require_payment', 'auto_approve', 'private',)
        model = models.Session


class SongRequestForm(forms.ModelForm):
    def __init__(self, session, *args, **kwargs):
        super(SongRequestForm, self).__init__(*args, **kwargs)
        self.session = session
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML('<div class="row"><div class="col-md-6">'),
            Field('first_name'),
            HTML('</div><div class="col-md-6">'),
            Field('last_name'),
            HTML('</div></div><div class="row"><div class="col-md-6">'),
            Field('email', placeholder='Ex: rhgoddard@wpi.edu'),
            HTML('</div><div class="col-md-6">'),
            Field('phone', placeholder='(123) 456-7890'),
            HTML('</div></div>')
        )

    first_name = forms.CharField(max_length=74, widget=forms.TextInput(attrs={'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=74, widget=forms.TextInput(attrs={'placeholder': 'Last Name'}))

    def clean(self):
        if self.cleaned_data['email'] in ['', None] and self.cleaned_data['phone'] in ['', None]:
            raise forms.ValidationError('Please supply an email address or phone number. We will only use this '
                                        'information to contact you if there is a problem with your request.')
        return self.cleaned_data

    class Meta:
        fields = ('email', 'phone')
        model = models.SongRequest

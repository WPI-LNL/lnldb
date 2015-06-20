from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django import forms
from django.core.urlresolvers import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Field, HTML
from crispy_forms.bootstrap import FormActions
from django.utils.translation import ugettext_lazy as _

from acct.models import Profile


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        super(LoginForm, self).__init__(*args, **kwargs)
        self.helper.add_input(Submit('submit', 'Log In Locally', css_class="btn btn-lg btn-block btn-info"))


class UserAcct(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_class = "form-horizontal"

        self.helper.layout = Layout(
            'first_name',
            'last_name',

            FormActions(
                Submit('save', 'Save Changes'),
                HTML(
                    'Click here to modify your <a href="%s">Contact Information</a>' % reverse('my-lnl')),
            )
        )
        super(UserAcct, self).__init__(*args, **kwargs)

    class Meta:
        model = User

        fields = ('first_name', 'last_name')

    first_name = forms.CharField(label="First Name")
    last_name = forms.CharField(label="Last Name")


class ProfileAcct(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(

            'wpibox',
            Field('phone', css_class="bfh-phone", data_format="(ddd) ddd dddd"),
            'addr',
            FormActions(
                Submit('save', 'Save Changes'),
                HTML(
                    'Click here to modify your <a href="%s">user information</a>' % reverse('my-acct')),
            )
        )
        super(ProfileAcct, self).__init__(*args, **kwargs)

    class Meta:
        model = Profile
        exclude = ("user", "locked")


## for adding new users
class UserAddForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_class = "form-horizontal"

        self.helper.layout = Layout(
            'username',
            'email',
            'first_name',
            'last_name',

            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(UserAddForm, self).__init__(*args, **kwargs)

    class Meta:
        model = User

        fields = ('username', 'email', 'first_name', 'last_name')

    first_name = forms.CharField(label="First Name")
    last_name = forms.CharField(label="Last Name")

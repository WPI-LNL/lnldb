from django.contrib.auth.models import User
from django import forms
from django.forms.models import inlineformset_factory

from django.core.urlresolvers import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Field, HTML
from crispy_forms.bootstrap import FormActions

from helpers.form_fields import django_msgs

from acct.models import Profile


class UserAcct(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_class = "form-horizontal"

        self.helper.layout = Layout(
            django_msgs,
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
            django_msgs,

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
            django_msgs,

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

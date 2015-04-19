from django import forms

from django.contrib.auth.models import User

from acct.models import Profile

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Submit, Field
from crispy_forms.bootstrap import FormActions


class MemberForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(

            'username',
            'first_name',
            'last_name',
            'groups',
            FormActions(
                Submit('save', 'Update Member and Return'),
            )
        )
        super(MemberForm, self).__init__(*args, **kwargs)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'groups']


class MemberContact(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            Fieldset(
                "Information",
                'wpibox',
                Field('phone', css_class="bfh-phone", data_format="(ddd) ddd dddd"),
                'addr',
                'mdc',
            ),
            Fieldset(
                "Settings",
                "locked"
            ),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(MemberContact, self).__init__(*args, **kwargs)

    class Meta:
        model = Profile
        exclude = ("user",)
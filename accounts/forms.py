from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Field, HTML, Row, Div, Fieldset
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from data.forms import FieldAccessForm, FieldAccessLevel


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        super(LoginForm, self).__init__(*args, **kwargs)
        self.helper.add_input(Submit('submit', 'Log In Locally', css_class="btn btn-lg btn-block btn-info"))


class UserEditForm(FieldAccessForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        self.helper.layout = Layout(

                Fieldset("User Info",
                         'first_name', 'last_name', 'username', 'email',
                         HTML("""
                     <div class="col-lg-offset-2 col-lg-8">
                         <a href="{% url 'accounts:password' object.pk %}">Set a password for non-CAS login</a>
                     </div>
                     """)),
                Fieldset("Contact Info",
                         'phone', Field('addr', rows=3)),
                Fieldset("Internal Info",
                         'mdc', 'wpibox', 'groups'),
                FormActions(
                        Submit('save', 'Update Member and Return'),
                )
        )
        super(UserEditForm, self).__init__(*args, **kwargs)

    class Meta:
        model = get_user_model()
        fields = ['username', 'email', 'first_name', 'last_name', 'groups', 'addr', 'wpibox', 'mdc', 'phone', ]

    class FieldAccess:
        def __init__(self):
            pass

        thisisme = FieldAccessLevel(
                lambda user, instance: user == instance,
                enable=('email', 'first_name', 'last_name', 'addr', 'wpibox', 'phone',)
        )
        hasperm = FieldAccessLevel(
                lambda user, instance: user.has_perm('auth.change_user', instance),
                enable=('username', 'email', 'first_name', 'last_name', 'addr', 'wpibox', 'phone',)
        )
        edit_groups = FieldAccessLevel(
                lambda user, instance: user.has_perm('auth.change_group', instance),
                enable=('groups',)
        )
        edit_mdc = FieldAccessLevel(
                lambda user, instance: user.has_perm('auth.edit_mdc', instance),
                enable=('mdc',)
        )


class UserAddForm(UserCreationForm):
    error_messages = {
        'password_mismatch': "The two password fields didn't match.",
    }

    class Meta:
        model = get_user_model()
        fields = ['username', 'email', 'first_name', 'last_name']

    def __init__(self, *args, **kwargs):
        self.base_fields['password1'].required = False
        self.base_fields['password2'].required = False
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_class = "form-horizontal"

        self.helper.layout = Layout(
                Row(Div('first_name', css_class='col-md-6'),
                    Div('last_name', css_class='col-md-6')),
                'username',
                'email',
                Row(Div('password1', css_class='col-md-6'),
                    Div('password2', css_class='col-md-6')),

                FormActions(
                        Submit('save', 'Save Changes'),
                )
        )
        super(UserAddForm, self).__init__(*args, **kwargs)

    # the rest is to make passwords optional.
    def clean_password2(self):
        if self.cleaned_data['password1'] or self.cleaned_data['password2']:
            return super(UserAddForm, self).clean_password2()
        else:
            return ""

    def save(self, commit=True):
        # we want to bypass UserCreationForm. Here's how:
        user = super(UserCreationForm, self).save(commit=False)

        # only set a pass if the form is filled
        if self.cleaned_data['password1']:
            user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user

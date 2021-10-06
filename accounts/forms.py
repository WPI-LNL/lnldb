from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Fieldset, Layout, Row, Submit, Hidden
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.conf import settings
from django import forms

from data.forms import FieldAccessForm, FieldAccessLevel
from .models import OfficerImg, carrier_choices
from .ldap import get_student_id


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Log In Locally', css_class="btn btn-lg btn-block btn-info"))


class UserEditForm(FieldAccessForm):
    def __init__(self, *args, **kwargs):
        request_user = kwargs['request_user']
        instance_user = kwargs['instance']
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        password = None
        if instance_user == request_user or request_user.is_superuser:
            password = HTML("""<div class="col-lg-offset-2 col-lg-8">
            <a href="{% url 'accounts:password' object.pk %}">Set a password for non-SSO login</a></div>""")
        layout = [
            Fieldset("User Info", 'first_name', 'last_name', 'username', 'email', 'nickname', password),
            Fieldset("Contact Info", 'phone', 'carrier', Field('addr', rows=3)),
        ]
        if request_user.is_lnl:
            layout.extend([
                Fieldset("Student Info",
                         'wpibox', 'class_year', 'student_id'),
                Fieldset("Internal Info",
                         'title', 'mdc', 'groups', 'away_exp'),
            ])
        layout.append(
            FormActions(
                Submit('save', 'Update Member and Return'),
            )
        )
        self.helper.layout = Layout(*layout)
        super(UserEditForm, self).__init__(*args, **kwargs)
        if request_user.is_lnl and instance_user.is_lnl:
            self.fields['class_year'].required = True

    def clean_student_id(self):
        student_id = self.cleaned_data.get('student_id', None)
        if not student_id and self.instance.is_lnl and settings.SYNC_STUDENT_ID:
            uid = get_student_id(self.instance.username)
            if uid:
                return int(uid)
        return student_id

    class Meta:
        model = get_user_model()
        fields = ['username', 'email', 'first_name', 'last_name', 'nickname', 'groups', 'addr',
                  'wpibox', 'mdc', 'phone', 'class_year', 'student_id', 'away_exp', 'carrier', 'title']

    class FieldAccess:
        def __init__(self):
            pass

        thisisme = FieldAccessLevel(
            lambda user, instance: (user == instance) and not user.locked,
            enable=('email', 'first_name', 'last_name', 'addr', 'wpibox', 'phone', 'class_year', 'nickname', 'carrier')
        )
        hasperm = FieldAccessLevel(
            lambda user, instance: (user != instance) and user.has_perm('accounts.change_user', instance),
            enable=('email', 'first_name', 'last_name', 'addr', 'wpibox', 'phone', 'class_year')
        )
        edit_groups = FieldAccessLevel(
            lambda user, instance: user.has_perm('accounts.change_membership', instance),
            enable=('groups', 'away_exp', 'title')
        )
        edit_mdc = FieldAccessLevel(
            lambda user, instance: user.has_perm('accounts.edit_mdc', instance),
            enable=('mdc',)
        )
        edit_student_id = FieldAccessLevel(
            lambda user, instance: (user == instance) and (not instance.student_id or not settings.SYNC_STUDENT_ID),
            enable=('student_id',)
        )
        unaffiliated = FieldAccessLevel(
            lambda user, instance: not user.is_lnl,
            exclude=('wpibox', 'class_year', 'student_id', 'mdc', 'groups',)
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
            HTML('<div class="alert alert-warning">\
                This form should not be used under normal circumstances. \
                When everything is working properly, an account will be created \
                automatically when someone logs into the DB with Microsoft SSO for the first time \
                or when crew hours or attendance are entered for the person. \
                This form should only be used when the automatic \
                account creation is broken (which has happened before).</div>'),
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
        # we want to bypass UserCreationForm's save.
        user = forms.ModelForm.save(self, commit=False)

        # only set a pass if the form is filled
        if self.cleaned_data['password1']:
            user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class OfficerPhotoForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.label_class = "col-lg-2"
        self.helper.field_class = "col-lg-8"
        self.helper.layout = Layout(
            Fieldset('Officer Photo - {{ officer.get_full_name }}', 'img'),
            FormActions(
                Submit('save', 'Save Changes'),
                HTML('<input type="submit" name="save" value="Remove" class="btn btn-danger"></input>'))
        )
        super(OfficerPhotoForm, self).__init__(*args, **kwargs)

    class Meta:
        model = OfficerImg
        fields = ['img']


class SMSOptInForm(forms.ModelForm):
    phone = forms.CharField(required=True, min_length=10, max_length=10)
    carrier = forms.ChoiceField(choices=carrier_choices[1:], required=True)

    def __init__(self, *args, **kwargs):
        exists = kwargs.pop('exists')
        request = kwargs.pop('request')
        self.helper = FormHelper()
        if not exists:
            self.helper.layout = Layout(
                Field('phone'),
                Field('carrier'),
                FormActions(
                    Submit('save', 'Continue')
                )
            )
        else:
            self.helper.layout = Layout(
                Hidden('phone', value=request.user.phone),
                Hidden('carrier', value=request.user.carrier),
                FormActions(
                    HTML('<a class="btn btn-secondary mr-2" '
                         'href="{% url \'accounts:detail\' request.user.pk %}">Edit</a>'),
                    Submit('save', 'Continue')
                )
            )
        super(SMSOptInForm, self).__init__(*args, **kwargs)

    class Meta:
        model = get_user_model()
        fields = ('phone', 'carrier')

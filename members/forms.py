from django import forms

from django.contrib.auth.models import User

from acct.models import Profile

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Submit, Field
from crispy_forms.bootstrap import FormActions

from data.forms import FieldAccessForm, FieldAccessLevel, DynamicFieldContainer


class MemberForm(FieldAccessForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            'username',
            'email',
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
        fields = ['username', 'email', 'first_name', 'last_name', 'groups']

    class FieldAccess:
        def __init__(self):
            pass

        thisisme = FieldAccessLevel(
            lambda user, instance: user == instance,
            enable=('email', 'first_name', 'last_name')
        )
        selfservice = FieldAccessLevel(
            lambda user, instance: user.has_perm('auth.change_user', instance),
            enable=('username', 'email', 'first_name', 'last_name')
        )
        edit_groups = FieldAccessLevel(
            lambda user, instance: user.has_perm('auth.change_group', instance),
            enable=('groups',)
        )


class MemberContact(FieldAccessForm):
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
            DynamicFieldContainer(Fieldset(
                "Settings",
                "locked"
            )),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(MemberContact, self).__init__(*args, **kwargs)

    class Meta:
        model = Profile
        exclude = ("user",)

    class FieldAccess:
        def __init__(self):
            pass

        thisisme = FieldAccessLevel(
            lambda user, instance: user.profile == instance,
            enable=('wpibox', 'phone', 'addr'),
        )
        selfservice = FieldAccessLevel(
            lambda user, instance: user.has_perm('acct.edit_user', instance),
            enable=('wpibox', 'phone', 'addr'),
        )
        edit_mdc = FieldAccessLevel(
            lambda user, instance: user.has_perm('acct.edit_mdc', instance),
            enable=('mdc',)
        )
        rev_lock = FieldAccessLevel(
            lambda user, instance: True,
            exclude=('locked',)
        )
        lock = FieldAccessLevel(
            lambda user, instance: user.has_perm('acct.change_group', instance),
            enable=('locked',)
        )

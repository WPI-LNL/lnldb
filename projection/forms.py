import datetime

from django import forms
from django.forms.models import inlineformset_factory
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Field, HTML
from crispy_forms.bootstrap import FormActions
from projection.models import Projectionist, PitInstance, PITLevel
from ajax_select.fields import AutoCompleteSelectField, AutoCompleteSelectMultipleField


class ProjectionistUpdateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_tag = False
        self.helper.layout = Layout(

            # 'pit_level',
            'license_number',
            HTML('<div class="pull-right"><a id="resetdate" class="btn btn-lg btn-warning">Reset Date</a></div>'),
            Field('license_expiry', css_class="datepick"),
        )
        super(ProjectionistUpdateForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Projectionist
        fields = ('license_number', 'license_expiry')


class ProjectionistForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
            'user',
            # 'pit_level',
            'license_number',
            Field('license_expiry', css_class="datepick"),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(ProjectionistForm, self).__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.exclude(projectionist__isnull=False)

    user = AutoCompleteSelectField('Users', required=True, plugin_options={
        'position': "{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})

    class Meta:
        model = Projectionist
        fields = ('user', 'license_number', 'license_expiry')


class InstanceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('pit_level'),
            Field('created_on', css_class="dtp"),
            Field('valid'),
            HTML('<hr>'),
        )
        super(InstanceForm, self).__init__(*args, **kwargs)

    class Meta:
        model = PitInstance
        fields = ('pit_level', 'created_on', 'valid')

    created_on = forms.SplitDateTimeField(initial=datetime.datetime.now())


class BulkUpdateForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('users'),
            Field('date', css_class="datepick"),
            Field('pit_level'),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(BulkUpdateForm, self).__init__(*args, **kwargs)

    users = AutoCompleteSelectMultipleField('Users', required=True, plugin_options={
        'position': "{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})
    date = forms.DateField()
    pit_level = forms.ModelChoiceField(queryset=PITLevel.objects.all(), empty_label=None)

    def create_updates(self):
        i = self.cleaned_data
        for user in i['users']:
            p, created = Projectionist.objects.get_or_create(user_id=user)
            PitInstance.objects.create(projectionist=p, pit_level=i['pit_level'], created_on=i['date'])


PITFormset = inlineformset_factory(Projectionist, PitInstance, extra=1,
                                   form=InstanceForm)  # ,formset=ProjectionistUpdateForm)


### ITS TIME FOR A WIZAAAAAAARD
class BulkCreateForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "GET"
        self.helper.layout = Layout(
            Field('contact'),
            Field('billing'),
            Field('date_first', css_class="datepick", ),
            Field('date_second', css_class="datepick", ),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(BulkCreateForm, self).__init__(*args, **kwargs)

    contact = AutoCompleteSelectField('Users', required=True, plugin_options={
        'position': "{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})
    billing = AutoCompleteSelectField('Orgs', required=True, plugin_options={
        'position': "{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})
    date_first = forms.DateField(label="Date of first movie of first term")
    date_second = forms.DateField(label="Date of first movie of second term")


class DateEntryFormSetBase(forms.Form):
    def __init__(self, *args, **kwargs):
        # pop the date out of the iterator here
        # x = kwargs.keys()

        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            Field('date'),
            Field('name'),
            Field('matinee'),
        )

        super(DateEntryFormSetBase, self).__init__(*args, **kwargs)

        self.fields['date'].widget.attrs['readonly'] = True
        #self.fields["date"].initial = dateobj

    date = forms.DateField()
    name = forms.CharField(required=False)
    matinee = forms.BooleanField(required=False)
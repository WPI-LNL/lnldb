from __future__ import division
import datetime

from ajax_select.fields import (AutoCompleteSelectField, AutoCompleteSelectMultipleField)
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Field, Layout, Submit, Hidden
from django import forms
from django.contrib.auth import get_user_model
from django.forms.models import inlineformset_factory
from django.utils import timezone

from events.models import Service
from events.models import Building, Category, Event2019, Location
from projection.models import PitInstance, PITLevel, Projectionist, PitRequest


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
        self.fields['user'].queryset = get_user_model().objects.exclude(projectionist__isnull=False)

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
            Field('created_on'),
            Field('valid'),
            HTML('<hr>'),
        )
        super(InstanceForm, self).__init__(*args, **kwargs)

    created_on = forms.DateField(widget=forms.TextInput(attrs={'class': 'dateinput'}))

    class Meta:
        model = PitInstance
        fields = ('pit_level', 'created_on', 'valid')


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


PITFormset = inlineformset_factory(Projectionist, PitInstance, extra=1, form=InstanceForm)


# ITS TIME FOR A WIZAAAAAAARD
class BulkCreateForm(forms.Form):
    def __init__(self, *args, user=None, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "GET"
        if user and user.has_perm('events.approve_event'):
            self.helper.layout = Layout(
                Field('contact'),
                Field('billing'),
                Field('date_first', css_class="datepick", ),
                Field('date_second', css_class="datepick", ),
                Field('auto_approve'),
                FormActions(
                    Submit('save', 'Continue'),
                )
            )
        else:
            self.helper.layout = Layout(
                Field('contact'),
                Field('billing'),
                Field('date_first', css_class="datepick", ),
                Field('date_second', css_class="datepick", ),
                FormActions(
                    Submit('save', 'Continue'),
                )
            )
        super(BulkCreateForm, self).__init__(*args, **kwargs)

    contact = AutoCompleteSelectField('Users', required=True, plugin_options={
        'position': "{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})
    billing = AutoCompleteSelectField('Orgs', required=True, plugin_options={
        'position': "{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})
    date_first = forms.DateField(label="Date of first movie")
    date_second = forms.DateField(label="Date of last movie")
    auto_approve = forms.BooleanField(label="Auto-approve events", initial=True, required=False)


class DateEntryFormSetBase(forms.Form):
    time_offsets = {  # This names must correspond to the checkboxes above
        'matinee': datetime.timedelta(hours=-6),
        'friday': datetime.timedelta(days=-1),
        'saturday': datetime.timedelta(days=0),
        'sunday': datetime.timedelta(days=1)
    }

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        # self.helper.form_class = "form-horizontal"
        self.helper.template = 'formset_crispy_generic.html'
        self.helper.layout = Layout(
            Field('date'),
            Field('name'),
            *self.time_offsets
        )

        super(DateEntryFormSetBase, self).__init__(*args, **kwargs)

        self.fields['date'].widget.attrs['readonly'] = True

    date = forms.DateField()
    name = forms.CharField(required=False)

    friday = forms.BooleanField(required=False)
    matinee = forms.BooleanField(required=False)
    saturday = forms.BooleanField(required=False, initial=True)
    sunday = forms.BooleanField(required=False, initial=True)

    def save_objects(self, user, contact, org, ip=None, approve=False):
        out = []
        tz = timezone.get_current_timezone()
        # don't count this week if not filled out
        if not self.is_valid():
            return out
        if not self.cleaned_data['name']:
            return out
        # the fields that go into the resulting obj, to start
        building, _ = Building.objects.get_or_create(name="Fuller Labs", shortname="FL")
        cat, _ = Category.objects.get_or_create(name="Projection")
        kwargs = {
            'event_name': self.cleaned_data['name'],
            'contact': contact,
            'submitted_by': user,
            'submitted_ip': ip,
            'location': Location.objects.get_or_create(name="Perreault Hall Upper", defaults={'building': building})[0],
            'billed_in_bulk': True,
            'billing_org': org,
            'send_survey': False
        }
        # if it's possible to approve the event, do so (since there is no bulk approve)
        if approve and user.has_perm('events.approve_event'):
            kwargs['event_status'] = 'Confirmed'
            kwargs['approved_by'] = user
            kwargs['approved_on'] = timezone.now()
            kwargs['approved'] = True

        date = self.cleaned_data['date']

        # prepare base date/times for the usual 8PM Sat start.
        dt_setupcomplete = datetime.datetime.combine(date, datetime.time(19, 30))
        dt_start = datetime.datetime.combine(date, datetime.time(20))
        dt_end = datetime.datetime.combine(date, datetime.time(23))

        # save for each offset (sat, sun, mat, etc.) if checked
        for offset_name in self.time_offsets.keys():
            # do nothing if not checked
            if not self.cleaned_data[offset_name]:
                continue

            offset = self.time_offsets[offset_name]
            kwargs['datetime_setup_complete'] = dt_setupcomplete.astimezone(tz) + offset
            kwargs['datetime_start'] = dt_start.astimezone(tz) + offset
            kwargs['datetime_end'] = dt_end.astimezone(tz) + offset

            e = Event2019.objects.create(**kwargs)
            e.org.add(org)
            e.serviceinstance_set.create(service=Service.objects.get_or_create(
                longname="Digital Projection", shortname='DP',
                defaults={'base_cost': 50, 'addtl_cost': 0, 'category': cat}
            )[0], )
            out.append(e)
        return out


class PITRequestForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('level'),
            HTML('<div class="col-3 form-inline" style="display: inline-block">'),
            Field('scheduled_for', css_class="form-control"),
            HTML('</div><br><br>'),
            Hidden('approved', False),
            FormActions(
                Submit('save', 'Submit Request'),
            )
        )
        super(PITRequestForm, self).__init__(*args, **kwargs)

    level = forms.ModelChoiceField(queryset=PITLevel.objects.all(), empty_label=None, label="PIT")
    scheduled_for = forms.SplitDateTimeField(label="Request Date / Time", required=False)

    class Meta:
        model = PitRequest
        fields = ('level', 'scheduled_for', 'approved')


class PITRequestAdminForm(PITRequestForm):
    def __init__(self, *args, **kwargs):
        super(PITRequestAdminForm, self).__init__(*args, **kwargs)
        self.helper.layout = Layout(
            Field('level'),
            HTML('<div class="col-3 form-inline" style="display: inline-block">'),
            Field('scheduled_for', css_class="form-control"),
            HTML('</div><br><br>'),
            Field('approved'),
            FormActions(
                Submit('save', 'Update'),
            )
        )

    scheduled_for = forms.SplitDateTimeField(label="Date / Time", required=True)
    approved = forms.BooleanField(label="Approve", required=False, help_text="Select this to approve the request "
                                                                             "and schedule this PIT")

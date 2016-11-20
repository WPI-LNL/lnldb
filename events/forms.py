import datetime
import decimal

# python multithreading bug workaround
from pagedown.widgets import PagedownWidget
from data.forms import FieldAccessForm, FieldAccessLevel, DynamicFieldContainer

from django import forms
from django.forms import ModelForm
from django.forms.extras.widgets import SelectDateWidget
from django.utils import timezone
from django.db.models import Q
from helpers.form_text import markdown_at_msgs
from django.core.urlresolvers import reverse
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Submit, Div, Field, HTML, Hidden, \
    Reset
from crispy_forms.bootstrap import InlineCheckboxes, InlineRadios, Tab, TabHolder, FormActions, \
    PrependedText
from events.models import Event, Organization, OrganizationTransfer, OrgBillingVerificationEvent, Fund
from events.models import Extra, Location, Lighting, Sound, Projection, Service, EventCCInstance, EventAttachment, \
    ExtraInstance
from events.models import Billing, CCReport, Hours
from events.widgets import ValueSelectField
from events.fields import GroupedModelChoiceField
from django.core.exceptions import ValidationError
import pytz
from ajax_select import make_ajax_field
from ajax_select.fields import AutoCompleteSelectMultipleField, AutoCompleteSelectField


LIGHT_EXTRAS = Extra.objects.filter(category__name="Lighting")
LIGHT_EXTRAS_ID_NAME = LIGHT_EXTRAS.values_list('id', 'name')
LIGHT_EXTRAS_NAMES = LIGHT_EXTRAS.values('name')

SOUND_EXTRAS = Extra.objects.filter(category__name="Sound")
SOUND_EXTRAS_ID_NAME = SOUND_EXTRAS.values_list('id', 'name')
SOUND_EXTRAS_NAMES = SOUND_EXTRAS.values('name')

PROJ_EXTRAS = Extra.objects.filter(category__name="Projection")
PROJ_EXTRAS_ID_NAME = PROJ_EXTRAS.values_list('id', 'name')
PROJ_EXTRAS_NAMES = PROJ_EXTRAS.values('name')

JOBTYPES = (
    (0, 'Lighting'),
    (1, 'Sound'),
    (2, 'Projection'),
    (3, 'Other Services'),
)

LIGHT_CHOICES = (
    (1, 'L1'),
    (2, 'L2'),
    (3, 'L3'),
    (4, 'L4'),
)

SOUND_CHOICES = (
    (1, 'S1'),
    (2, 'S2'),
    (3, 'S3'),
    (4, 'S4'),
)
PROJ_CHOICES = (
    (16, '16mm'),
    (35, '35mm'),
    ('d', 'Digital'),
)


# gets a set of services from a given event
def get_qs_from_event(event):
    if event.lighting:
        lighting_id = event.lighting.id
    else:
        lighting_id = None
    if event.sound:
        sound_id = event.sound.id
    else:
        sound_id = None
    if event.projection:
        proj_id = event.projection.id
    else:
        proj_id = None

    return Service.objects.filter(Q(id__in=[lighting_id]) | Q(id__in=[sound_id]) | Q(id__in=[proj_id]) | Q(
        id__in=[i.id for i in event.otherservices.all()]))


# LNAdmin Forms
class WorkorderSubmit(ModelForm):
    class Meta:
        model = Event
        exclude = ('submitted_by', 'submitted_ip', 'approved', 'crew', 'crew_chief',
                   'report', 'closed', 'payment_amount', 'paid')

    def __init__(self, *args, **kwargs):
        super(WorkorderSubmit, self).__init__(*args, **kwargs)
        self.fields['datetime_setup_start'].widget = SelectDateWidget()
        # self.fields['datetime_start'].widget = datetime()
        # self.fields['datetime_end'].widget = datetime()


class CrewAssign(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            Field('crew'),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(CrewAssign, self).__init__(*args, **kwargs)

    class Meta:
        model = Event
        fields = ("crew",)

    crew = make_ajax_field(Event, 'crew', 'Members', plugin_options={'minLength': 3})


class CrewChiefAssign(forms.ModelForm):
    crew_chief = make_ajax_field(Event, 'crew_chief', 'Members', plugin_options={'minLength': 3})

    class Meta:
        model = Event
        fields = ("crew_chief",)


class IOrgForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'Contact',
                    Field('name'),
                    'exec_email',
                    'address',
                    Field('phone', css_class="bfh-phone", data_format="(ddd) ddd dddd"),
                ),
                Tab(
                    'Options',
                    'associated_orgs',
                    Field('personal', )
                ),
                Tab(
                    'Money',
                    'accounts'
                ),
                Tab(
                    'People',
                    'user_in_charge',
                    'associated_users',
                )
            ),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(IOrgForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Organization
        fields = ('name', 'exec_email', 'address', 'phone', 'associated_orgs', 'personal',
                  'accounts', 'user_in_charge', 'associated_users')
    # associated_orgs = make_ajax_field(Organization,'associated_orgs','Orgs',plugin_options = {'minLength':2})
    # associated_users = make_ajax_field(Organization,'associated_users','Users',plugin_options = {'minLength':3})
    user_in_charge = AutoCompleteSelectField('Users')
    associated_orgs = AutoCompleteSelectMultipleField('Orgs', required=False)
    associated_users = AutoCompleteSelectMultipleField('Users', required=False)
    accounts = AutoCompleteSelectMultipleField('Funds', required=False)


class IOrgVerificationForm(forms.ModelForm):
    def __init__(self, org, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.org = org
        self.helper.layout = Layout(
            Field('date', css_class="datepick"),
            Field('verified_by'),
            Field('note', size="5"),
            FormActions(
                Submit('save', 'Verify'),
            )
        )
        super(IOrgVerificationForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        obj = super(IOrgVerificationForm, self).save(commit=False)
        obj.org = self.org
        if commit:
            obj.save()
        return obj

    class Meta:
        model = OrgBillingVerificationEvent
        fields = ('date', 'verified_by', 'note')

    verified_by = AutoCompleteSelectField('Officers')


# Flow Forms
class EventApprovalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    "Standard Fields",
                    Field('description', label="Description (optional)", css_class="col-md-6"),
                    HTML('<p class="muted offset2">This will describe the event to your CCs</p>'),
                    Field('internal_notes', label="Internal Notes", css_class="col-md-6"),
                    markdown_at_msgs,
                    Field('datetime_setup_complete', label="Setup Finish", css_class="dtp"),
                    Field('datetime_start', label="Event Start", css_class="dtp"),
                    Field('datetime_end', label="Event End", css_class="dtp"),
                    Field('org'),
                    Field('billing_fund'),
                    Field('billed_by_semester', label="Billed by semester (for films)"),
                    # Field('datetime_setup_start',label="Setup Start",css_class="dtp"),

                ),
                Tab(
                    "Services",
                    Field('lighting'),
                    Field('lighting_reqs', css_class="col-md-8"),
                    Field('sound'),
                    Field('sound_reqs', css_class="col-md-8"),
                    Field('projection'),
                    Field('proj_reqs', css_class="col-md-8"),
                    Field('otherservices'),
                    Field('otherservice_reqs', css_class="col-md-8")
                ),
            ),
            FormActions(
                Submit('save', 'Approve Event'),
            ),
        )
        super(EventApprovalForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Event
        fields = ['description', 'internal_notes', 'datetime_start', 'datetime_end', 'billing_fund',
                  'billed_by_semester', 'datetime_setup_complete', 'lighting', 'lighting_reqs',
                  'sound', 'sound_reqs', 'projection', 'proj_reqs', 'otherservices', 'otherservice_reqs', 'org']
        widgets = {
            'description': PagedownWidget(),
            'internal_notes': PagedownWidget,
            'lighting_reqs': PagedownWidget(),
            'sound_reqs': PagedownWidget(),
            'proj_reqs': PagedownWidget(),
            'otherservice_reqs': PagedownWidget()
        }

    org = AutoCompleteSelectMultipleField('Orgs', required=False, label="Client")
    billing_fund = AutoCompleteSelectField("Funds", required=False)
    datetime_start = forms.SplitDateTimeField(initial=timezone.now, label="Event Start")
    datetime_end = forms.SplitDateTimeField(initial=timezone.now, label="Event End")
    # datetime_setup_start =  forms.SplitDateTimeField(initial=timezone.now)
    datetime_setup_complete = forms.SplitDateTimeField(initial=timezone.now, label="Setup Completed")


class EventDenialForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            Field('cancelled_reason', label="Reason For Cancellation (optional)", css_class="col-md-6"),
            FormActions(
                Submit('save', 'Deny Event'),
            ),
        )
        super(EventDenialForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Event
        fields = ('cancelled_reason',)
        widgets = {
            'cancelled_reason': PagedownWidget()
        }


class EventMeetingForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            Field('datetime_setup_start', label="Setup Start", css_class="dtp"),
            Field('datetime_setup_complete', label="Setup Finish", css_class="dtp"),
            Field('crew_chief', label="Crew Chief"),
            Field('crew', label="Crew"),
            FormActions(
                Submit('save', 'Update Event and Return'),
            )
        )
        super(EventMeetingForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Event
        fields = ['datetime_setup_start', 'datetime_setup_complete', 'crew_chief', 'crew']

    datetime_setup_start = forms.SplitDateTimeField(initial=timezone.now)
    datetime_setup_complete = forms.SplitDateTimeField(initial=timezone.now)
    crew_chief = AutoCompleteSelectMultipleField('Users', required=False)
    crew = AutoCompleteSelectMultipleField('3', required=False)


class InternalEventForm(FieldAccessForm):
    def __init__(self, *args, **kwargs):
        super(InternalEventForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'Name And Location',
                    'event_name',
                    'location',
                    Field('description'),
                    DynamicFieldContainer('internal_notes'),
                    DynamicFieldContainer('billed_by_semester'),
                    'sensitive',
                    'test_event',
                ),
                Tab(
                    'Contact',
                    # 'person_name',
                    'contact',
                    'org',
                    DynamicFieldContainer('billing_fund'),
                ),
                Tab(
                    'Scheduling',
                    Div(
                        Div(Field('datetime_setup_complete', css_class='dtp', title="Setup Completed By"),
                            css_class="padleft"),
                    ),
                    Div(
                        HTML(
                            '<div class="pull-left pushdown"><br />'
                            '<a class="btn btn-primary" href="#" id="samedate1" title="Cascade Dates">'
                            '<i class="glyphicon glyphicon-resize-small icon-white"></i>&nbsp;'
                            '<i class="glyphicon glyphicon-calendar icon-white"></i></a></div>'),
                        Div(Field('datetime_start', css_class='dtp'), css_class="padleft"),
                    ),
                    Div(
                        HTML(
                            '<div class="pull-left pushdown"><br />'
                            '<a class="btn btn-primary" href="#" id="samedate2" title="Cascade Dates">'
                            '<i class="glyphicon glyphicon-resize-small icon-white"></i>&nbsp;'
                            '<i class="glyphicon glyphicon-calendar icon-white"></i></a></div>'),
                        Div(Field('datetime_end', css_class='dtp'), css_class="padleft"),
                    ),
                ),
                Tab(
                    'Lighting',
                    'lighting',
                    'lighting_reqs'
                ),
                Tab(
                    'Sound',
                    'sound',
                    'sound_reqs'
                ),
                Tab(
                    'Projection',
                    'projection',
                    'proj_reqs'
                ),
                Tab(
                    'Other Services',
                    'otherservices',
                    'otherservice_reqs'
                ),
            ),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(InternalEventForm, self).__init__(*args, **kwargs)

    class FieldAccess:
        def __init__(self):
            pass

        internal_notes_write = FieldAccessLevel(
            lambda user, instance: user.has_perm("events.event_view_sensitive", instance),
            enable=('internal_notes',)
        )

        hide_internal_notes = FieldAccessLevel(
            lambda user, instance: not user.has_perm("events.event_view_sensitive", instance),
            exclude=('internal_notes',)
        )

        event_times = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_times', instance),
            enable=('datetime_start', 'datetime_setup_complete', 'datetime_end')
        )

        edit_descriptions = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_text', instance),
            enable=('event_name', 'location', 'description',
                    'lighting_reqs', 'sound_reqs', 'proj_reqs', 'otherservice_reqs')
        )

        change_owner = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.adjust_event_owner', instance),
            enable=('contact', 'org')
        )

        change_type = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.adjust_event_charges', instance),
            enable=('lighting', 'sound', 'projection', 'otherservices', 'billed_by_semester')
        )

        billing_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_fund', instance),
            enable=('billing_fund', 'billed_by_semester')
        )

        billing_view = FieldAccessLevel(
            lambda user, instance: not user.has_perm('events.view_event_billing', instance),
            exclude=('billing_fund', 'billed_by_semester')
        )

        change_flags = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_flags', instance),
            enable=('sensitive', 'test_event')
        )

    class Meta:
        model = Event
        fields = ('event_name', 'location', 'description', 'internal_notes', 'billing_fund',
                  'billed_by_semester', 'contact', 'org', 'datetime_setup_complete', 'datetime_start',
                  'datetime_end', 'lighting', 'lighting_reqs', 'sound', 'sound_reqs', 'projection', 'proj_reqs',
                  'otherservices', 'otherservice_reqs', 'sensitive', 'test_event')
        widgets = {
            'description': PagedownWidget(),
            'internal_notes': PagedownWidget,
            'lighting_reqs': PagedownWidget(),
            'sound_reqs': PagedownWidget(),
            'proj_reqs': PagedownWidget(),
            'otherservice_reqs': PagedownWidget()
        }

    location = GroupedModelChoiceField(
        queryset=Location.objects.filter(show_in_wo_form=True),
        group_by_field="building",
        group_label=lambda group: group.name,
    )
    contact = AutoCompleteSelectField('Users', required=False)
    billing_fund = AutoCompleteSelectField('Funds', required=False)
    org = AutoCompleteSelectMultipleField('Orgs', required=False, label="Client")

    datetime_setup_complete = forms.SplitDateTimeField(initial=timezone.now, label="Setup Completed")
    datetime_start = forms.SplitDateTimeField(initial=timezone.now, label="Event Start")
    datetime_end = forms.SplitDateTimeField(initial=timezone.now, label="Event End")


class EventReviewForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML("<h5>If you'd like to override the billing org, please search for it below</h5>"),
            Field('billing_org'),
            Field('internal_notes', css_class="col-md-6", size="15"),
            FormActions(
                HTML('<h4> Does this look good to you?</h4>'),
                Submit('save', 'Yes!', css_class='btn btn-lg btn-danger'),
                HTML(
                    '<a class="btn btn-lg btn-success" href="{%% url "events.views.flow.viewevent" %s %%}"> No... </a>'
                    % event.id),
            ),
        )
        super(EventReviewForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Event
        fields = ('billing_org', 'internal_notes')
        widgets = {
            'internal_notes': PagedownWidget()
        }

    billing_org = AutoCompleteSelectField('Orgs', required=False, label="")


class InternalReportForm(FieldAccessForm):
    def __init__(self, event, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
            DynamicFieldContainer('crew_chief'),
            HTML('<h4>What you might put in the report:</h4>'
                 '<ul><li>How was the event set up?</li>'
                 '<li>Roughly what equipment was used?</li>'
                 '<li>Were there any last minute changes</li>'
                 '<li>Did you come across any issues?</li>'
                 '<li>Would you classify this event as the level it was booked under?</li>'
                 '<li>What information would be useful for somebody next year?</li></ul>'),
            Field('report', css_class="col-md-10"),
            markdown_at_msgs,
            FormActions(
                Submit('save', 'Save Changes'),
                # Reset('reset','Reset Form'),
            )
        )
        super(InternalReportForm, self).__init__(*args, **kwargs)
        if 'crew_chief' in self.fields and not self.fields['crew_chief'].initial:
            self.fields['crew_chief'].initial = self.user.pk

    def save(self, commit=True):
        obj = super(InternalReportForm, self).save(commit=False)
        if 'crew_chief' not in self.cleaned_data:
            self.instance.crew_chief = self.user  # user field from FAF
        obj.event = self.event
        if commit:
            obj.save()
            self.save_m2m()
        return obj

    class Meta:
        model = CCReport
        fields = ('crew_chief', 'report')
        widgets = {
            'report': PagedownWidget()
        }
    crew_chief = AutoCompleteSelectField('Members', required=False)

    class FieldAccess:
        avg_user = FieldAccessLevel(
            lambda user, instance: not user.has_perm('events.add_event_report'),
            exclude=('crew_chief',)
        )
        admin = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.add_event_report'),
            enable=('crew_chief',)
        )
        all = FieldAccessLevel(lambda user, instance: True, enable=('report',))


# External Organization forms

class ExternalOrgUpdateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
            'address',
            Field('phone', css_class="bfh-phone", data_format="(ddd) ddd dddd"),
            'associated_users',
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(ExternalOrgUpdateForm, self).__init__(*args, **kwargs)

    associated_users = AutoCompleteSelectMultipleField('Users', required=True)

    class Meta:
        model = Organization
        fields = ('address', 'phone', 'associated_users')


class OrgXFerForm(forms.ModelForm):
    def __init__(self, org, user, *args, **kwargs):
        self.user = user
        self.org = org
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
            'new_user_in_charge',
            HTML(
                '<p class="text-muted">'
                'This form will transfer ownership of this Organization to another user associated '
                'with the Organization. A confirmation E-Mail will be sent with a link to confirm the '
                'transfer.</p>'),
            FormActions(
                Submit('save', 'Submit Transfer'),
            )
        )
        super(OrgXFerForm, self).__init__(*args, **kwargs)

        self.fields['new_user_in_charge'].queryset = org.associated_users.all().exclude(id=user.id)

    def save(self, commit=True):
        obj = super(OrgXFerForm, self).save(commit=False)
        obj.old_user_in_charge = self.user
        obj.org = self.org
        if commit:
            obj.save()
        return obj

    # new_user_in_charge = AutoCompleteSelectField('Users', required=True,
    # plugin_options={'position':"{ my : \"right top\", at: \"right bottom\",
    # of: \"#id_person_name_text\"},'minlength':4"})
    class Meta:
        model = OrganizationTransfer
        fields = ('new_user_in_charge',)


class SelfServiceOrgRequestForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.help_text_inline = True
        self.helper.layout = Layout(
            Field('client_name', help_text_inline=True),
            'email',
            'address',
            Field('phone', css_class="bfh-phone", data_format="(ddd) ddd dddd"),
            'fund_info',
            FormActions(
                Submit('save', 'Submit Request'),
            )
        )
        super(SelfServiceOrgRequestForm, self).__init__(*args, **kwargs)

    client_name = forms.CharField(max_length=128, label="Client Name", help_text="EX: Lens & Lights")
    email = forms.EmailField(help_text="EX: lnl@wpi.edu (This should be your exec board alias)")
    address = forms.CharField(widget=forms.Textarea, help_text="EX: Campus Center 339")
    phone = forms.CharField(max_length=15, help_text="EX: (508) - 867 - 5309")
    fund_info = forms.CharField(help_text="EX: 12345-6789-8765")


# Internal Billing forms

class BillingForm(forms.ModelForm):
    def __init__(self, event, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.event = event
        self.helper.layout = Layout(
            PrependedText('date_billed', '<i class="glyphicon glyphicon-calendar"></i>', css_class="datepick"),
            PrependedText('amount', '<strong>$</strong>'),
            Field('opt_out_initial_email'),
            Field('opt_out_update_email'),
            FormActions(
                Submit('save', 'Save Changes'),
                Reset('reset', 'Reset Form'),
            )
        )
        super(BillingForm, self).__init__(*args, **kwargs)

        self.fields['amount'].initial = "%.2f" % event.cost_total
        self.fields['date_billed'].initial = datetime.date.today()
        self.fields['opt_out_initial_email'].initial = True
        self.fields['opt_out_update_email'].initial = True

    def save(self, commit=True):
        obj = super(BillingForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Billing
        fields = ('date_billed', 'amount', 'opt_out_initial_email', 'opt_out_update_email')


class BillingUpdateForm(forms.ModelForm):
    def __init__(self, event, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""

        self.helper.layout = Layout(
            PrependedText('date_paid', '<i class="glyphicon glyphicon-calendar"></i>', css_class="datepick"),
            PrependedText('amount', '<strong>$</strong>'),
            Field('opt_out_update_email'),
            FormActions(
                Submit('save', 'Save Changes'),
                Reset('reset', 'Reset Form'),
            )
        )
        super(BillingUpdateForm, self).__init__(*args, **kwargs)

        self.fields['amount'].initial = str(event.cost_total)
        self.fields['date_paid'].initial = datetime.date.today()

    def save(self, commit=True):
        obj = super(BillingUpdateForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Billing
        fields = ('date_paid', 'amount', 'opt_out_update_email')


# CC Facing Forms
class MKHoursForm(forms.ModelForm):
    def __init__(self, event, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
            Field('user'),
            Field('hours'),
            Field('service'),
            FormActions(
                Submit('save', 'Save Changes'),
                # Reset('reset','Reset Form'),
            )
        )
        super(MKHoursForm, self).__init__(*args, **kwargs)
        self.fields['service'].queryset = get_qs_from_event(event)

    def clean(self):
        super(MKHoursForm, self).clean()
        service = self.cleaned_data['service']
        user = self.cleaned_data['user']
        if self.event.hours.filter(user=user, service=service).exists() and not self.instance.pk:
            raise ValidationError("User already has hours for this service. Edit those instead")

    def save(self, commit=True):
        obj = super(MKHoursForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Hours
        fields = ('user', 'hours', 'service')

    user = AutoCompleteSelectField('Users', required=True)
    hours = forms.DecimalField(min_value=decimal.Decimal("0.00"))


class EditHoursForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
            Field('hours'),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(EditHoursForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Hours
        fields = ('hours',)


class FopalForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
            Field('name'),
            Field('notes'),
            Field('fund'),
            Field('organization'),
            Field('account'),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(FopalForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Fund
        fields = ('name', 'notes', 'fund', 'organization', 'account')


class CCIForm(forms.ModelForm):
    def __init__(self, event, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-inline"
        self.helper.template = 'bootstrap/table_inline_formset.html'
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('crew_chief', placeholder="Crew Chief", title=""),
            Field('service'),
            Field('setup_location'),
            Field('setup_start', css_class="dtp"),
            HTML('<hr>'),
        )
        super(CCIForm, self).__init__(*args, **kwargs)

        # x = self.instance.event.lighting
        self.fields['service'].queryset = get_qs_from_event(event)
        self.fields['setup_start'].initial = self.fields['setup_start'].prepare_value(
            self.event.datetime_setup_complete.replace(second=0, microsecond=0)
        )

    def save(self, commit=True):
        obj = super(CCIForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = EventCCInstance
        fields = ('crew_chief', 'service', 'setup_location', 'setup_start')

    crew_chief = AutoCompleteSelectField('Members', required=True)
    setup_start = forms.SplitDateTimeField(initial=timezone.now)
    setup_location = GroupedModelChoiceField(
        queryset=Location.objects.filter(setup_only=True).select_related('building'),
        group_by_field="building",
        group_label=lambda group: group.name,
    )


# Forms for Inline Formsets
class AttachmentForm(forms.ModelForm):
    def __init__(self, event, externally_uploaded=False, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-inline"
        self.helper.template = 'bootstrap/table_inline_formset.html'
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('for_service'),
            Field('attachment'),
            Field('note', size="2"),
            Hidden('externally_uploaded', externally_uploaded),
            HTML('<hr>'),
        )
        super(AttachmentForm, self).__init__(*args, **kwargs)

        # x = self.instance.event.lighting
        self.fields['for_service'].queryset = get_qs_from_event(event)

    def save(self, commit=True):
        obj = super(AttachmentForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = EventAttachment
        fields = ('for_service', 'attachment', 'note')


class ExtraForm(forms.ModelForm):
    class Meta:
        model = ExtraInstance
        fields = ('extra', 'quant')

    extra = GroupedModelChoiceField(
        queryset=Extra.objects.all(),
        group_by_field="category",
        group_label=lambda group: group.name,
    )


# CrewChiefFS = inlineformset_factory(Event,EventCCInstance,extra=3,form=CCIForm, exclude=[])


# usage
# CrewChiefFS = inlineformset_factory(Event,EventCCInstance,extra=3, exclude=[])
# CrewChiefFS.form = staticmethod(curry(CCIForm, event=request.event))

# Workorder Forms

# Workorder Repeat Form
class WorkorderRepeatForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            Field('location'),
            Field('event_name'),
            TabHolder(
                Tab(
                    "Main Information",
                    Field('description', label="Description (optional)", css_class="col-md-6"),
                    Field('datetime_setup_complete', label="Setup Finish", css_class="dtp"),
                    Field('datetime_start', label="Event Start", css_class="dtp"),
                    Field('datetime_end', label="Event End", css_class="dtp"),
                ),
                Tab(
                    "Lighting",
                    InlineRadios('lighting', title="Lighting", empty_label=None),
                    Field('lighting_reqs', css_class="col-md-8"),
                ),
                Tab(
                    "Sound",
                    InlineRadios('sound', title="Sound"),
                    Field('sound_reqs', css_class="col-md-8"),
                ),
                Tab(
                    "Projection",
                    InlineRadios('projection', title="Projection"),
                    Field('proj_reqs', css_class="col-md-8"),
                ),
                Tab(
                    "Additional Information",
                    InlineCheckboxes('otherservices'),
                    Field('otherservice_reqs', css_class="col-md-8")
                ),
            ),
            FormActions(
                Submit('save', 'Repeat Event'),
            ),
        )
        super(WorkorderRepeatForm, self).__init__(*args, **kwargs)

    datetime_setup_complete = forms.SplitDateTimeField(label="Setup Completed By", required=True)
    datetime_start = forms.SplitDateTimeField(label="Event Starts")
    datetime_end = forms.SplitDateTimeField(label="Event Ends")
    location = GroupedModelChoiceField(
        queryset=Location.objects.filter(show_in_wo_form=True),
        group_by_field="building",
        group_label=lambda group: group.name,
    )
    lighting = forms.ModelChoiceField(
        empty_label=None,
        queryset=Lighting.objects.all(),
        widget=forms.RadioSelect(attrs={'class': 'radio itt'}),
        required=False
    )
    sound = forms.ModelChoiceField(
        empty_label=None,
        queryset=Sound.objects.all(),
        widget=forms.RadioSelect(attrs={'class': 'radio itt'}),
        required=False
    )
    projection = forms.ModelChoiceField(
        empty_label=None,
        queryset=Projection.objects.all(),
        widget=forms.RadioSelect(attrs={'class': 'radio itt'}),
        required=False
    )
    otherservices = forms.ModelMultipleChoiceField(
        queryset=Service.objects.filter(category__name__in=["Misc", "Power"]),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
        required=False
    )

    class Meta:
        model = Event
        fields = ['location', 'event_name', 'description', 'datetime_start', 'datetime_end', 'datetime_setup_complete',
                  'lighting', 'lighting_reqs', 'sound', 'sound_reqs', 'projection', 'proj_reqs', 'otherservices',
                  'otherservice_reqs']

    def clean(self):  # custom validation
        cleaned_data = super(WorkorderRepeatForm, self).clean()

        # time validation
        setup_complete = cleaned_data.get("datetime_setup_complete")
        event_start = cleaned_data.get("datetime_start")
        event_end = cleaned_data.get("datetime_end")

        if not setup_complete or not event_start or not event_end:
            raise ValidationError('Please enter in a valid time in each field')
        if event_start > event_end:
            raise ValidationError('You cannot start after you finish')
        if setup_complete > event_start:
            raise ValidationError('You cannot setup after you finish')
        if setup_complete < datetime.datetime.now(pytz.utc):
            raise ValidationError('Stop trying to time travel')

        # service exists validation
        lighting = cleaned_data.get("lighting", None)
        sound = cleaned_data.get("sound", None)
        projection = cleaned_data.get("projection", None)
        otherservices = cleaned_data.get("otherservices", None)

        if not (lighting or sound or projection or not otherservices):
            raise ValidationError(
                'Please select at least one service, %s %s %s %s' % (lighting, sound, projection, otherservices))

        return cleaned_data


# __        __         _                 _
# \ \      / /__  _ __| | _____  _ __ __| | ___ _ __
#  \ \ /\ / / _ \| '__| |/ / _ \| '__/ _` |/ _ \ '__|
#   \ V  V / (_) | |  |   < (_) | | | (_| |  __/ |
#    \_/\_/ \___/|_|  |_|\_\___/|_|  \__,_|\___|_|

#  _____                            _                  _
# |  ___|__  _ __ _ __ _____      _(_)______ _ _ __ __| |
# | |_ / _ \| '__| '_ ` _ \ \ /\ / / |_  / _` | '__/ _` |
# |  _| (_) | |  | | | | | \ V  V /| |/ / (_| | | | (_| |
# |_|  \___/|_|  |_| |_| |_|\_/\_/ |_/___\__,_|_|  \__,_|

#  _____
# |  ___|__  _ __ _ __ ___  ___
# | |_ / _ \| '__| '_ ` _ \/ __|
# |  _| (_) | |  | | | | | \__ \
# |_|  \___/|_|  |_| |_| |_|___/

SERVICE_INFO_HELP_TEXT = """
Note: Any riders or documentation provided to you from the artist/performer which may help LnL
determine the technical needs of your event may be attached to this request once it is submitted by
going to your LnL account and select "Previous WorkOrders".
"""


# FormWizard Forms
class ContactForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_tag = False
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        self.helper.layout = Layout(
            'name',
            'email',
            Field('phone', css_class="bfh-phone", data_format="(ddd) ddd dddd"),
            HTML(
                '<span class="text-muted">To avoid entering this information again, update your '
                '<a target="_blank" href="%s">contact information</a></span>' % reverse(
                    'accounts:me')),
        )
        super(ContactForm, self).__init__(*args, **kwargs)

    name = forms.CharField()
    email = forms.EmailField()
    phone = forms.CharField()


class OrgForm(forms.Form):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')

        super(OrgForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_tag = False
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        # the org nl, is a special org that everyone has access to and is not listed.
        self.fields['group'].queryset = Organization.objects.filter(
            Q(user_in_charge=user) | Q(associated_users__in=[user.id]) | Q(shortname="nl")).distinct()
        self.helper.layout = Layout(
            'group',
            HTML(
                '<span class="text-muted">If the client account you are looking for does not show up in the list, '
                'please contact the person in charge of the account using <a target="_blank" href="%s">this link</a> '
                'and request authorization to submit workorder son their behalf. If you are attempting to create a '
                'client account which does not exist please click <a target="_blank" href="%s">this link</a></span>'
                % (reverse('my:orgs'), reverse('my:org-request'))),
        )
        # super(OrgForm,self).__init__(*args,**kwargs)

    group = forms.ModelChoiceField(queryset=Organization.objects.all(), label="Organization")
    # group = AutoCompleteSelectField('UserLimitedOrgs', required=True,
    #  plugin_options={'position':"{ my : \"right top\", at: \"right bottom\",
    # of: \"#id_person_name_text\"}",'minLength':2})


class SelectForm(forms.Form):
    def __init__(self, org=None, *args, **kwargs):
        super(SelectForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_tag = False
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        self.helper.layout = Layout(
            Fieldset(
                'Name and Location',
                Field('eventname', css_class="col-md-6"),
                Field('location', css_class="col-md-6"),
                Field('general_description', css_class="col-md-6"),
            ),
            Fieldset(
                'Services',
                InlineCheckboxes('eventtypes')
            )
        )

    eventname = forms.CharField(
        label='Event Name',
        required=True
    )

    # location = forms.ModelChoiceField(
    # queryset = Location.objects.filter(show_in_wo_form=True)
    # )

    # soon to be a
    location = GroupedModelChoiceField(
        queryset=Location.objects.filter(show_in_wo_form=True)
                         .select_related('building__name'),
        group_by_field="building",
        group_label=lambda group: group.name,
    )

    eventtypes = forms.MultipleChoiceField(
        error_messages={'required': 'Please Select at least one service \n\r'},
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
        choices=JOBTYPES,
        label="",
        required=True

    )
    general_description = forms.CharField(
        widget=forms.Textarea(),
        help_text='Please use this space to provide general information or special request regarding your event such '
                  'as staging configuration or that there is an intermission or dinner at a specific time. '
                  'Specific requirements and/or requests for the Sound/Lights/Projection portion of your event '
                  'such as "We need 3 wireless handheld microphones." will be asked for on a later page.',
    )


class LightingForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.form_tag = False
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        self.helper.layout = Layout(
            Fieldset(
                'Basics',  # title
                InlineRadios('lighting', title="test"),
                Field('requirements', css_class="col-md-10"),
            ),
            Fieldset(
                'Extras',  # title
                *[DynamicFieldContainer("e_%s" % extra.id) for extra in LIGHT_EXTRAS.all()],
                css_class="extra_fs"),
        )
        super(LightingForm, self).__init__(*args, **kwargs)
        for extra in LIGHT_EXTRAS:
            self.fields["e_%s" % extra.id] = ValueSelectField(hidetext=extra.checkbox,
                                                              disappear=extra.disappear,
                                                              label=extra.name, initial=0,
                                                              required=False)

    lighting = forms.ModelChoiceField(
        empty_label=None,
        queryset=Lighting.objects.all(),
        widget=forms.RadioSelect(attrs={'class': 'radio itt'}),
    )

    requirements = forms.CharField(
        widget=PagedownWidget(),
        # widget=BootstrapTextInput(prepend='P',),
        label="Lighting Requirements",
        help_text=SERVICE_INFO_HELP_TEXT,
        required=False,
    )

    # extras = ExtraSelectorField(choices=LIGHT_EXTRAS.values_list('id','name'))
    # for extra in LIGHT_EXTRAS:
    # "e__{{0}}" % extra.id = ValueSelectField(extra)


class SoundForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.form_tag = False
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        self.helper.layout = Layout(
            Fieldset(
                'Basics',  # title
                InlineRadios('sound'),
                Field('requirements', css_class="col-md-10"),
            ),
            Fieldset(
                'Extras',  # title
                *[DynamicFieldContainer("e_%s" % extra.id) for extra in SOUND_EXTRAS.all()],
                css_class="extra_fs"
            ),
        )
        super(SoundForm, self).__init__(*args, **kwargs)
        for extra in SOUND_EXTRAS:
            self.fields["e_%s" % extra.id] = ValueSelectField(hidetext=extra.checkbox, disappear=extra.disappear,
                                                              label=extra.name, initial=0, required=False)

    sound = forms.ModelChoiceField(
        empty_label=None,
        queryset=Sound.objects.all(),
        widget=forms.RadioSelect(attrs={'class': 'radio itt'}),
    )
    requirements = forms.CharField(
        widget=PagedownWidget(),
        label="Sound Requirements",
        required=False,
        help_text=SERVICE_INFO_HELP_TEXT,
    )


class ProjectionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.form_tag = False
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        self.helper.layout = Layout(
            Fieldset(
                'Basics',  # title
                InlineRadios('projection'),
                Field('requirements', css_class="col-md-10"),
            ),
            Fieldset(
                'Extras',  # title
                *[DynamicFieldContainer("e_%s" % extra.id) for extra in PROJ_EXTRAS.all()],
                css_class="extra_fs"
            ),


        )
        super(ProjectionForm, self).__init__(*args, **kwargs)
        for extra in PROJ_EXTRAS:
            self.fields["e_%s" % extra.id] = ValueSelectField(hidetext=extra.checkbox, disappear=extra.disappear,
                                                              label=extra.name, initial=0, required=False)

    projection = forms.ModelChoiceField(
        empty_label=None,
        queryset=Projection.objects.all(),
        widget=forms.RadioSelect(attrs={'class': 'radio'}),
    )
    requirements = forms.CharField(
        widget=PagedownWidget(),
        label="Projection Requirements",
        required=False,
        help_text=SERVICE_INFO_HELP_TEXT,
    )


class ServiceForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.form_tag = False
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-8'
        self.helper.layout = Layout(
            Fieldset(
                'Basics',  # title
                'services',
                Field('otherservice_reqs', css_class="col-md-8"),
            ),

        )
        super(ServiceForm, self).__init__(*args, **kwargs)

    services = forms.ModelMultipleChoiceField(
        queryset=Service.objects.filter(category__name__in=["Misc", "Power"]),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
    )
    otherservice_reqs = forms.CharField(
        widget=PagedownWidget(),
        label="Additional Information",
    )


class ScheduleForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.form_tag = False
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-5'
        self.helper.layout = Layout(
            Fieldset(
                'Setup',  # title
                # Field('setup_start',css_class="dtp"),
                Div(
                    HTML(
                        '<div class="pull-left"><a class="btn btn-xs btn-primary" href="#" id="samedate">'
                        '<i class="glyphicon glyphicon-arrow-down icon-white"></i>&nbsp;'
                        '<i class="glyphicon glyphicon-calendar icon-white" title="Cascade"></i></a></div>'),
                    Field('setup_complete', css_class="dtp"),

                ),
            ),
            Fieldset(
                'Event',  # title
                Field('event_start', css_class="dtp"),
                Field('event_end', css_class="dtp"),
            ),
        )
        super(ScheduleForm, self).__init__(*args, **kwargs)

    today = datetime.datetime.today()
    noon = datetime.time(12)
    noontoday = datetime.datetime.combine(today, noon)
    # setup_start = forms.SplitDateTimeField(initial=timezone.now)
    setup_complete = forms.SplitDateTimeField(initial=noontoday, label="Setup Completed By", required=True)
    event_start = forms.SplitDateTimeField(initial=noontoday, label="Event Starts")
    event_end = forms.SplitDateTimeField(initial=noontoday, label="Event Ends")

    def clean(self):
        cleaned_data = super(ScheduleForm, self).clean()

        setup_complete = cleaned_data.get("setup_complete")
        event_start = cleaned_data.get("event_start")
        event_end = cleaned_data.get("event_end")
        if not setup_complete or not event_start or not event_end:
            raise ValidationError('Please enter in a valid time in each field')
        if event_start > event_end:
            raise ValidationError('You cannot start after you finish')
        if setup_complete > event_start:
            raise ValidationError('You cannot setup after you finish')
        if setup_complete < datetime.datetime.now(pytz.utc):
            raise ValidationError('Stop trying to time travel')

        return cleaned_data


# helpers for the formwizard
named_event_forms = (
    ('contact', ContactForm),
    ('organization', OrgForm),
    ('select', SelectForm),
    ('lighting', LightingForm),
    ('sound', SoundForm),
    ('projection', ProjectionForm),
    ('other', ServiceForm),
    ('schedule', ScheduleForm),
)

named_event_tmpls = {
    'organization': 'eventform/org.html',
    'contact': 'eventform/contact.html',
    'select': 'eventform/select.html',
    'lighting': 'eventform/lighting.html',
    'sound': 'eventform/sound.html',
    'projection': 'eventform/projection.html',
    'other': 'eventform/other.html',
    'schedule': 'eventform/schedule.html',
}

import datetime
import decimal
import re
import uuid

import six
from ajax_select import make_ajax_field
from ajax_select.fields import (AutoCompleteSelectField,
                                AutoCompleteSelectMultipleField)
from crispy_forms.bootstrap import (FormActions, InlineCheckboxes, InlineRadios, PrependedText, Tab, TabHolder)
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (HTML, Div, Row, Column, Field, Hidden, Layout, Reset, Submit)
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db.models import Model, Q
from django.forms import ModelChoiceField, ModelMultipleChoiceField, ModelForm, SelectDateWidget, TextInput
from django.utils import timezone
# python multithreading bug workaround
from easymde.widgets import EasyMDEEditor

from data.forms import DynamicFieldContainer, FieldAccessForm, FieldAccessLevel
from events.fields import GroupedModelChoiceField
from events.models import (BaseEvent, Billing, MultiBilling, BillingEmail, MultiBillingEmail,
                           Category, CCReport, Event, Event2019, EventAttachment, EventCCInstance, Extra,
                           ExtraInstance, Hours, Lighting, Location, Organization, OrganizationTransfer,
                           OrgBillingVerificationEvent, Workshop, WorkshopDate, Projection, Service, ServiceInstance,
                           Sound, PostEventSurvey, OfficeHour)
from events.widgets import ValueSelectField
from helpers.form_text import markdown_at_msgs
from helpers.util import curry_class

LIGHT_EXTRAS = Extra.objects.exclude(disappear=True).filter(category__name="Lighting")
LIGHT_EXTRAS_ID_NAME = LIGHT_EXTRAS.values_list('id', 'name')
LIGHT_EXTRAS_NAMES = LIGHT_EXTRAS.values('name')

SOUND_EXTRAS = Extra.objects.exclude(disappear=True).filter(category__name="Sound")
SOUND_EXTRAS_ID_NAME = SOUND_EXTRAS.values_list('id', 'name')
SOUND_EXTRAS_NAMES = SOUND_EXTRAS.values('name')

PROJ_EXTRAS = Extra.objects.exclude(disappear=True).filter(category__name="Projection")
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
    if isinstance(event, Event):
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
    elif isinstance(event, Event2019):
        return Service.objects.filter(pk__in=event.serviceinstance_set.values_list('service', flat=True))


class CustomAutoCompleteSelectMultipleField(AutoCompleteSelectMultipleField):
    def has_changed(self, initial_value, data_value):
        initial_value = [v.pk if isinstance(v, Model) else v for v in (initial_value or [])]
        return AutoCompleteSelectMultipleField.has_changed(self, initial_value, data_value)


class CustomEventModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, event):
        return six.u('%s\u2014%s') % (event.event_name, ', '.join(map(lambda org: org.name, event.org.all())))


class CustomOrganizationEmailModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, org):
        return six.u('%s (%s)') % (org.name, org.exec_email)


class SurveyCustomRadioSelect(forms.widgets.ChoiceWidget):
    input_type = 'radio'
    template_name = 'survey_custom_radio_select.html'
    option_template_name = 'survey_custom_radio_select.html'


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


class IOrgForm(FieldAccessForm):
    """ Internal Organization Details Form """
    def __init__(self, request_user, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        tabs = []
        if request_user.has_perm('events.view_org_notes'):
            tabs.append(
                Tab(
                    'Notes',
                    'notes',
                    'delinquent'
                )
            )
        read_only = 'rw'
        instance = kwargs['instance']
        if instance is not None and instance.locked is True:
            read_only = 'r'
        tabs.extend([
            Tab(
                'Contact',
                Field('name', css_class=read_only),
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
                'workday_fund',
                Field('worktag', placeholder='e.g. 1234-CC'),
            ),
            Tab(
                'People',
                Field('user_in_charge', css_class=read_only),
                'associated_users',
            )
        ])
        self.helper.layout = Layout(
            TabHolder(*tabs),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(IOrgForm, self).__init__(request_user, *args, **kwargs)

    def clean_worktag(self):
        pattern = re.compile('[0-9]+-[A-Z][A-Z]')
        if pattern.match(self.cleaned_data['worktag']) is None and self.cleaned_data['worktag'] not in [None, '']:
            raise ValidationError('What you entered is not a valid worktag. Here are some examples of what a worktag '
                                  'looks like: 1234-CC, 123-AG')
        return self.cleaned_data['worktag']

    class Meta:
        model = Organization
        fields = ('name', 'exec_email', 'address', 'phone', 'associated_orgs', 'personal',
                  'workday_fund', 'worktag', 'user_in_charge', 'associated_users', 'notes', 'delinquent')

    # associated_orgs = make_ajax_field(Organization,'associated_orgs','Orgs',plugin_options = {'minLength':2})
    # associated_users = make_ajax_field(Organization,'associated_users','Users',plugin_options = {'minLength':3})
    user_in_charge = AutoCompleteSelectField('Users')
    associated_orgs = AutoCompleteSelectMultipleField('Orgs', required=False)
    associated_users = AutoCompleteSelectMultipleField('Users', required=False)
    worktag = forms.CharField(required=False, help_text='Ends in -AG, -CC, -GF, -GR, or -DE')
    notes = forms.CharField(widget=EasyMDEEditor(), label="Internal Notes", required=False)

    class FieldAccess:
        def __init__(self):
            pass

        internal_notes_view = FieldAccessLevel(
            lambda user, instance: not user.has_perm("events.view_org_notes", instance),
            exclude=('notes', 'delinquent')
        )

        internal_notes_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm("events.view_org_notes", instance),
            enable=('notes', 'delinquent')
        )

        billing_view = FieldAccessLevel(
            lambda user, instance: not user.has_perm("events.show_org_billing", instance),
            exclude=('workday_fund', 'worktag')
        )

        billing_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm("events.edit_org_billing", instance),
            enable=('workday_fund', 'worktag')
        )

        members_view = FieldAccessLevel(
            lambda user, instance: not user.has_perm("events.list_org_members", instance),
            exclude=('user_in_charge', 'associated_users',)
        )

        members_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm("events.edit_org_members", instance),
            enable=('associated_users',)
        )

        owner_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm("events.transfer_org_ownership", instance),
            enable=('user_in_charge',)
        )

        everything_else_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm("events.edit_org", instance),
            enable=('name', 'exec_email', 'address', 'phone', 'associated_orgs', 'personal')
        )


class IOrgVerificationForm(forms.ModelForm):
    """ Internal Client Billing Verification Form """
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
        super(EventApprovalForm, self).__init__(*args, **kwargs)
        tabs = (
            Tab(
                "Standard Fields",
                Field('description', label="Description (optional)", css_class="col-md-6"),
                Field('internal_notes', label="Internal Notes", css_class="col-md-6"),
                markdown_at_msgs,
                Field('datetime_setup_complete', label="Setup Finish", css_class="dtp"),
                Field('datetime_start', label="Event Start", css_class="dtp"),
                Field('datetime_end', label="Event End", css_class="dtp"),
                'org',
                'billing_org',
                'billed_in_bulk',
                # Field('datetime_setup_start',label="Setup Start",css_class="dtp"),
                active=True
            ),
        )
        if isinstance(self.instance, Event):
            tabs += (
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
            )
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.include_media = False
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(*tabs)

    class Meta:
        model = Event
        fields = ['description', 'internal_notes', 'datetime_start', 'datetime_end', 'org', 'billing_org',
                  'billed_in_bulk', 'datetime_setup_complete', 'lighting', 'lighting_reqs',
                  'sound', 'sound_reqs', 'projection', 'proj_reqs', 'otherservices', 'otherservice_reqs']
        widgets = {
            'description': EasyMDEEditor(),
            'internal_notes': EasyMDEEditor(),
            'lighting_reqs': EasyMDEEditor(),
            'sound_reqs': EasyMDEEditor(),
            'proj_reqs': EasyMDEEditor(),
            'otherservice_reqs': EasyMDEEditor()
        }

    org = AutoCompleteSelectMultipleField('Orgs', required=False, label='Client(s)')
    billing_org = AutoCompleteSelectField('Orgs', required=False, label='Client to bill')
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
            Field('send_email', css_class=""),
            HTML('Please note that the reason will be included in the cancellation email to the event contact. <p />'),
            FormActions(
                Submit('save', 'Deny Event'),
            ),
        )
        super(EventDenialForm, self).__init__(*args, **kwargs)

    send_email = forms.BooleanField(required=False, label="Send Cancellation Email to Event Contact")

    class Meta:
        model = BaseEvent
        fields = ['cancelled_reason', 'send_email']
        widgets = {
            'cancelled_reason': EasyMDEEditor()
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
    def __init__(self, request_user, *args, **kwargs):
        super(InternalEventForm, self).__init__(request_user, *args, **kwargs)
        tabs = (
            Tab(
                'Name And Location',
                'event_name',
                'event_status',
                'location',
                'lnl_contact',
                Field('description'),
                DynamicFieldContainer('internal_notes'),
                'billed_in_bulk',
                'sensitive',
                'test_event',
                active=True
            ),
            Tab(
                'Contact',
                'contact',
                'org',
                DynamicFieldContainer('billing_org'),
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
        )
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.include_media = False
        self.helper.layout = Layout(*tabs)

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
            enable=('lighting', 'sound', 'projection', 'otherservices', 'billed_in_bulk')
        )

        billing_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_fund', instance),
            enable=('billing_org', 'billed_in_bulk')
        )

        billing_view = FieldAccessLevel(
            lambda user, instance: not user.has_perm('events.view_event_billing', instance),
            exclude=('billing_org', 'billed_in_bulk')
        )

        change_flags = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_flags', instance),
            enable=('sensitive', 'test_event')
        )

        change_lnl_contact = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_lnl_contact', instance),
            enable=('lnl_contact',)
        )
        
        change_event_status = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_status', instance),
            enable=('event_status',)
        )

    class Meta:
        model = Event
        fields = ('event_name', 'event_status', 'location', 'lnl_contact', 'description', 'internal_notes', 'billing_org', 'billed_in_bulk', 'contact',
                  'org', 'datetime_setup_complete', 'datetime_start', 'datetime_end', 'lighting', 'lighting_reqs',
                  'sound', 'sound_reqs', 'projection', 'proj_reqs', 'otherservices', 'otherservice_reqs', 'sensitive',
                  'test_event')
        widgets = {
            'description': EasyMDEEditor(),
            'internal_notes': EasyMDEEditor(),
            'lighting_reqs': EasyMDEEditor(),
            'sound_reqs': EasyMDEEditor(),
            'proj_reqs': EasyMDEEditor(),
            'otherservice_reqs': EasyMDEEditor()
        }

    location = GroupedModelChoiceField(
        queryset=Location.objects.filter(show_in_wo_form=True),
        group_by_field="building",
        group_label=lambda group: group.name,
    )
    contact = AutoCompleteSelectField('Users', required=False)
    lnl_contact = AutoCompleteSelectField('Members', required=False)
    org = CustomAutoCompleteSelectMultipleField('Orgs', required=False, label="Client(s)")
    billing_org = AutoCompleteSelectField('Orgs', required=False, label="Client to bill")
    datetime_setup_complete = forms.SplitDateTimeField(initial=timezone.now, label="Setup Completed")
    datetime_start = forms.SplitDateTimeField(initial=timezone.now, label="Event Start")
    datetime_end = forms.SplitDateTimeField(initial=timezone.now, label="Event End")
    otherservices = ModelMultipleChoiceField(queryset=Service.objects.filter(enabled_event2012=True), required=False)


class InternalEventForm2019(FieldAccessForm):
    def __init__(self, request_user, *args, **kwargs):
        super(InternalEventForm2019, self).__init__(request_user, *args, **kwargs)
        tabs = (
            Tab(
                'Name And Location',
                'event_name',
                'event_status',
                'location',
                'lnl_contact',
                'reference_code',
                Field('description'),
                DynamicFieldContainer('internal_notes'),
                HTML('<div style="width: 50%">'),
                'max_crew',
                'cancelled_reason',
                HTML('</div>'),
                'billed_in_bulk',
                'sensitive',
                'test_event',
                'entered_into_workday',
                'send_survey',
                active=True
            ),
            Tab(
                'Contact',
                'contact',
                'org',
                DynamicFieldContainer('billing_org'),
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
        )
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.include_media = False
        self.helper.layout = Layout(*tabs)

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
            enable=('datetime_start', 'datetime_setup_complete', 'datetime_end',
                'reference_code')
        )

        edit_descriptions = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_text', instance),
            enable=('event_name', 'location', 'description',
                    'lighting_reqs', 'sound_reqs', 'proj_reqs', 'otherservice_reqs', 'max_crew')
        )

        change_owner = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.adjust_event_owner', instance),
            enable=('contact', 'org', 'reference_code')
        )

        change_type = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.adjust_event_charges', instance),
            enable=('lighting', 'sound', 'projection', 'otherservices', 'billed_in_bulk')
        )

        billing_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_fund', instance),
            enable=('billing_org', 'billed_in_bulk')
        )

        billing_view = FieldAccessLevel(
            lambda user, instance: not user.has_perm('events.view_event_billing', instance),
            exclude=('billing_org', 'billed_in_bulk', 'entered_into_workday')
        )

        change_flags = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_flags', instance),
            enable=('sensitive', 'test_event')
        )

        change_lnl_contact = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_lnl_contact', instance),
            enable=('lnl_contact',)
        )
        
        change_event_status = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.edit_event_status', instance),
            enable=('event_status',)
        )

        change_entered_into_workday = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.bill_event', instance),
            enable=('entered_into_workday',)
        )

        survey_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.view_posteventsurveyresults') and \
                                   (instance is None or not instance.survey_sent), enable=('send_survey',)
        )

        survey_view = FieldAccessLevel(
            lambda user, instance: not user.has_perm('events.view_posteventsurveyresults'),
            exclude=('send_survey',)
        )

        cancelled_reason_edit = FieldAccessLevel(
            lambda user, instance: user.has_perm('events.cancel_event') and \
                                   (instance is not None and instance.cancelled), enable=('cancelled_reason',)
        )

    class Meta:
        model = Event2019
        fields = ('event_name', 'event_status', 'location', 'lnl_contact', 'description', 'internal_notes', 'billing_org',
                  'billed_in_bulk', 'contact', 'org', 'datetime_setup_complete', 'datetime_start',
                  'datetime_end', 'sensitive', 'test_event',
                  'entered_into_workday', 'send_survey', 'max_crew','cancelled_reason',
                  'reference_code')
        widgets = {
            'description': EasyMDEEditor(),
            'internal_notes': EasyMDEEditor(),
            'cancelled_reason': TextInput(),
        }

    location = GroupedModelChoiceField(
        queryset=Location.objects.filter(show_in_wo_form=True),
        group_by_field="building",
        group_label=lambda group: group.name,
    )
    contact = AutoCompleteSelectField('Users', required=False)
    lnl_contact = AutoCompleteSelectField('Members', label="LNL Contact", required=False)
    org = CustomAutoCompleteSelectMultipleField('Orgs', required=False, label="Client(s)")
    billing_org = AutoCompleteSelectField('Orgs', required=False, label="Client to bill")
    datetime_setup_complete = forms.SplitDateTimeField(initial=timezone.now, label="Setup Completed")
    datetime_start = forms.SplitDateTimeField(initial=timezone.now, label="Event Start")
    datetime_end = forms.SplitDateTimeField(initial=timezone.now, label="Event End")
    max_crew = forms.IntegerField(label="Maximum Crew", help_text="Include this to enforce an occupancy limit",
                                  required=False)
    cancelled_reason = forms.CharField(label="Reason for Cancellation", required=False),
    # Regex will match valid 25Live reservation codes in the format
    # `2022-ABNXQQ`
    reference_code =forms.CharField(validators=[RegexValidator(regex=r"[0-9]{4}-[A-Z]{6}")],
            required = False)


class EventReviewForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'org',
            'billing_org',
            Field('internal_notes', css_class="col-md-6", size="15"),
            FormActions(
                HTML('<h4> Does this look good to you?</h4>'),
                Submit('save', 'Yes!', css_class='btn btn-lg btn-success'),
                HTML(
                    '<a class="btn btn-lg btn-danger" href="{%% url "events:detail" %s %%}"> Cancel </a>'
                    % event.id),
            ),
        )
        super(EventReviewForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Event
        fields = ('org', 'billing_org', 'internal_notes')
        widgets = {
            'internal_notes': EasyMDEEditor()
        }

    org = AutoCompleteSelectMultipleField('Orgs', required=True, label="Client(s)")
    billing_org = AutoCompleteSelectField('Orgs', required=False, label="Client to bill")


class InternalReportForm(FieldAccessForm):
    """ Crew Chief Report Form """
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
                 '<li>Were there any last minute changes?</li>'
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
            'report': EasyMDEEditor()
        }

    crew_chief = AutoCompleteSelectField('Members', required=False)

    class FieldAccess:
        def __init__(self):
            pass

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
    """ Organization Details Form for Client """
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
            'exec_email',
            'address',
            Field('phone', css_class="bfh-phone", data_format="(ddd) ddd dddd"),
            'associated_users',
            'workday_fund',
            Field('worktag', placeholder='e.g. 1234-CC'),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(ExternalOrgUpdateForm, self).__init__(*args, **kwargs)

    associated_users = AutoCompleteSelectMultipleField('Users', required=True)
    worktag = forms.CharField(required=False, help_text='Ends in -AG, -CC, -GF, -GR, or -DE')

    def clean_worktag(self):
        pattern = re.compile('[0-9]+-[A-Z][A-Z]')
        if pattern.match(self.cleaned_data['worktag']) is None and self.cleaned_data['worktag'] not in [None, '']:
            raise ValidationError('What you entered is not a valid worktag. Here are some examples of what a worktag '
                                  'looks like: 1234-CC, 123-AG')
        return self.cleaned_data['worktag']

    class Meta:
        model = Organization
        fields = ('exec_email', 'address', 'phone', 'associated_users', 'workday_fund', 'worktag')


class OrgXFerForm(forms.ModelForm):
    """ Organization Transfer Form """
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

        self.fields['new_user_in_charge'].queryset = org.associated_users.exclude(id=org.user_in_charge_id)

    def save(self, commit=True):
        obj = super(OrgXFerForm, self).save(commit=False)
        obj.initiator = self.user
        obj.old_user_in_charge = self.org.user_in_charge
        obj.org = self.org
        if not obj.uuid:
            obj.uuid = uuid.uuid4()
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
            FormActions(
                Submit('save', 'Submit Request'),
            )
        )
        super(SelfServiceOrgRequestForm, self).__init__(*args, **kwargs)

    client_name = forms.CharField(max_length=128, label="Client Name", help_text="EX: Lens & Lights")
    email = forms.EmailField(help_text="EX: lnl@wpi.edu (This should be your exec board alias)")
    address = forms.CharField(widget=forms.Textarea, help_text="EX: Campus Center 339")
    phone = forms.CharField(max_length=15, help_text="EX: (508) - 867 - 5309")


class WorkdayForm(forms.ModelForm):
    """ Workday Bill Pay Form """
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'workday_fund',
            Field('worktag', placeholder='e.g. 1234-CC'),
            'workday_form_comments',
            FormActions(
                Submit('submit', 'Pay'),
            )
        )
        super(WorkdayForm, self).__init__(*args, **kwargs)
        self.fields['workday_fund'].label = 'Funding source'
        self.fields['workday_fund'].required = True
        self.fields['workday_form_comments'].label = 'Comments'

    def clean_worktag(self):
        pattern = re.compile('[0-9]+-[A-Z][A-Z]')
        if pattern.match(self.cleaned_data['worktag']) is None:
            raise ValidationError('What you entered is not a valid worktag. Here are some examples of what a worktag '
                                  'looks like: 1234-CC, 123-AG')
        return self.cleaned_data['worktag']

    class Meta:
        model = Event2019
        fields = 'workday_fund', 'worktag', 'workday_form_comments'

    worktag = forms.CharField(required=True, help_text='Ends in -AG, -CC, -GF, -GR, or -DE')


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
            FormActions(
                Submit('save-and-return', 'Save and Return'),
                Submit('save-and-make-email', 'Save and Make Email'),
                Reset('reset', 'Reset Form'),
            )
        )
        super(BillingForm, self).__init__(*args, **kwargs)

        self.fields['amount'].initial = "%.2f" % event.cost_total
        self.fields['date_billed'].initial = datetime.date.today()

    def save(self, commit=True):
        obj = super(BillingForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Billing
        fields = ('date_billed', 'amount')


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
        fields = ('date_paid', 'amount')


class MultiBillingForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        show_nonbulk_events = kwargs.pop('show_nonbulk_events')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        layout = []
        if show_nonbulk_events:
            layout += [
                HTML(
                    '<a href="?show_nonbulk_events=false">Switch back to showing only events marked for '
                    'semester billing</a>')
            ]
        else:
            layout += [
                HTML('<a href="?show_nonbulk_events=true">Show events not marked for semester billing</a>')
            ]
        layout += [
            'events',
            PrependedText('date_billed', '<i class="glyphicon glyphicon-calendar"></i>', css_class="datepick"),
            PrependedText('amount', '<strong>$</strong>'),
            FormActions(
                Submit('save-and-return', 'Save and Return'),
                Submit('save-and-make-email', 'Save and Make Email'),
                Reset('reset', 'Reset Form'),
            )
        ]
        self.helper.layout = Layout(*layout)
        super(MultiBillingForm, self).__init__(*args, **kwargs)
        if show_nonbulk_events is True:
            self.fields['events'].queryset = BaseEvent.objects.filter(closed=False, reviewed=True,
                                                                      billings__isnull=True) \
                .exclude(multibillings__isnull=False, multibillings__date_paid__isnull=False)
            self.fields['events'].help_text = 'Only unbilled, reviewed events are listed above.'
        self.fields['date_billed'].initial = datetime.date.today()

    def clean(self):
        cleaned_data = super(MultiBillingForm, self).clean()
        events = cleaned_data.get('events', [])
        if events:
            org = events[0].org_to_be_billed
            for event in events[1:]:
                if event.org_to_be_billed != org:
                    raise ValidationError('All events you select must have the same \'Client to bill\'.')
        return cleaned_data

    def save(self, commit=True):
        instance = super(MultiBillingForm, self).save(commit=False)
        instance.org = self.cleaned_data['events'].first().org_to_be_billed
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = MultiBilling
        fields = ('events', 'date_billed', 'amount')

    events = CustomEventModelMultipleChoiceField(
        queryset=BaseEvent.objects.filter(closed=False, reviewed=True, billings__isnull=True, billed_in_bulk=True) \
            .exclude(multibillings__isnull=False, multibillings__date_paid__isnull=False),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
        help_text="Only unbilled, reviewed events that are marked for semester billing are listed above."
    )


class MultiBillingUpdateForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(MultiBillingUpdateForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        events_str = ', '.join(map(lambda event: event.event_name, self.instance.events.all()))
        self.helper.layout = Layout(
            HTML('<p>Events: ' + events_str + '</p>'),
            PrependedText('date_paid', '<i class="glyphicon glyphicon-calendar"></i>', css_class="datepick"),
            PrependedText('amount', '<strong>$</strong>'),
            FormActions(
                Submit('save', 'Save Changes'),
                Reset('reset', 'Reset Form'),
            )
        )
        self.fields['date_paid'].initial = datetime.date.today()

    class Meta:
        model = MultiBilling
        fields = ('date_paid', 'amount')


class BillingEmailForm(forms.ModelForm):
    def __init__(self, billing, *args, **kwargs):
        super(BillingEmailForm, self).__init__(*args, **kwargs)
        self.billing = billing
        orgs = billing.event.org.all()
        self.fields["email_to_orgs"].queryset = orgs
        self.fields["email_to_orgs"].initial = orgs
        if billing.event.contact:
            self.fields["email_to_users"].initial = [billing.event.contact.pk]
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-10'
        self.helper.layout = Layout(
            HTML('<p class="text-muted">The bill PDF for this event will be attached to the email. The message you '
                 'type below is not the entire contents of the email; a large "PAY NOW" button and identifying '
                 'information about the event being billed will be added to the email below your message.</p>'),
            'subject',
            'message',
            'email_to_users',
            'email_to_orgs',
            FormActions(
                Submit('save', 'Send Email'),
            )
        )

    def clean(self):
        cleaned_data = super(BillingEmailForm, self).clean()
        if not cleaned_data.get('email_to_users', None) and not cleaned_data.get('email_to_orgs', None):
            raise ValidationError('No recipients')
        for user in map(lambda id: get_user_model().objects.get(id=id), cleaned_data.get('email_to_users', [])):
            if not user.email:
                raise ValidationError('User %s has no email address on file' % user.get_full_name())
        for org in cleaned_data.get('email_to_orgs', []):
            if not org.exec_email:
                raise ValidationError('Organization %s has no email address on file' % org.name)
        return cleaned_data

    def save(self, commit=True):
        instance = super(BillingEmailForm, self).save(commit=False)
        instance.billing = self.billing
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = BillingEmail
        fields = ('subject', 'message', 'email_to_users', 'email_to_orgs')

    email_to_users = AutoCompleteSelectMultipleField('Users', required=False, label="User Recipients")
    email_to_orgs = CustomOrganizationEmailModelMultipleChoiceField(
        queryset=Organization.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
        required=False, label="Client Recipients",
        help_text="The email address listed is the client's exec email alias on file."
    )


class MultiBillingEmailForm(forms.ModelForm):
    def __init__(self, multibilling, *args, **kwargs):
        super(MultiBillingEmailForm, self).__init__(*args, **kwargs)
        self.multibilling = multibilling
        orgsets = map(lambda event: event.org.all(), multibilling.events.all())
        orgs = next(iter(orgsets))
        for orgset in orgsets:
            orgs |= orgset
        orgs = orgs.distinct()
        contacts = map(lambda event: event.contact.pk, multibilling.events.filter(contact__isnull=False))
        self.fields["email_to_orgs"].queryset = orgs
        self.fields["email_to_orgs"].initial = multibilling.org
        self.fields["email_to_users"].initial = contacts
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-10'
        self.helper.layout = Layout(
            HTML('<p class="text-muted">The bill PDF will be attached to the email.</p>'),
            'subject',
            'message',
            'email_to_users',
            'email_to_orgs',
            FormActions(
                Submit('save', 'Send Email'),
            )
        )

    def clean(self):
        cleaned_data = super(MultiBillingEmailForm, self).clean()
        if not cleaned_data.get('email_to_users', None) and not cleaned_data.get('email_to_orgs', None):
            raise ValidationError('No recipients')
        for user in map(lambda id: get_user_model().objects.get(id=id), cleaned_data.get('email_to_users', [])):
            if not user.email:
                raise ValidationError('User %s has no email address on file' % user.get_full_name())
        for org in cleaned_data.get('email_to_orgs', []):
            if not org.exec_email:
                raise ValidationError('Organization %s has no email address on file' % org.name)
        return cleaned_data

    def save(self, commit=True):
        instance = super(MultiBillingEmailForm, self).save(commit=False)
        instance.multibilling = self.multibilling
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = MultiBillingEmail
        fields = ('subject', 'message', 'email_to_users', 'email_to_orgs')

    email_to_users = AutoCompleteSelectMultipleField('Users', required=False, label="User Recipients")
    email_to_orgs = CustomOrganizationEmailModelMultipleChoiceField(
        queryset=Organization.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkbox'}),
        required=False, label="Client Recipients",
        help_text="The email address listed is the client's exec email alias on file."
    )


# CC Facing Forms
class MKHoursForm(forms.ModelForm):
    """ Event Hours Form """
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
        if isinstance(event, Event2019):
            self.fields['category'].queryset = Category.objects.filter(
                pk__in=event.serviceinstance_set.values_list('service__category', flat=True))
            if len(self.fields['category'].queryset) == 1:
                self.fields['category'].initial = self.fields['category'].queryset.first()

    def clean(self):
        super(MKHoursForm, self).clean()
        category = self.cleaned_data.get('category')
        service = self.cleaned_data.get('service')
        user = self.cleaned_data.get('user')
        if user is None:
            # this problem will raise an error elsewhere
            return
        if self.event.hours.filter(user=user, category=category, service=service).exists() and not self.instance.pk:
            raise ValidationError("User already has hours for this category/service. Edit those instead")

    def save(self, commit=True):
        obj = super(MKHoursForm, self).save(commit=False)
        if obj.category is None and obj.service is not None:
            obj.category = obj.service.category
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = Hours
        fields = ('user', 'hours', 'category', 'service')

    user = AutoCompleteSelectField('Users', required=True)
    hours = forms.DecimalField(min_value=decimal.Decimal("0.00"))
    category = ModelChoiceField(queryset=Category.objects.all(), required=False)
    service = ModelChoiceField(queryset=Service.objects.all(), required=False)  # queryset gets changed in constructor


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


class CCIForm(forms.ModelForm):
    """ Crew Chief Instance form """
    def __init__(self, event, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "form-inline"
        self.helper.template = 'bootstrap/table_inline_formset.html'
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('crew_chief', placeholder="Crew Chief", title=""),
            Field('service' if isinstance(event, Event) else 'category'),
            Field('setup_location'),
            Field('setup_start', css_class="dtp"),
            HTML('<hr>'),
        )
        super(CCIForm, self).__init__(*args, **kwargs)

        # x = self.instance.event.lighting
        self.fields['service'].queryset = get_qs_from_event(event)
        if isinstance(event, Event2019):
            self.fields['category'].queryset = Category.objects.filter(
                pk__in=event.serviceinstance_set.values_list('service__category', flat=True))
            if len(self.fields['category'].queryset) == 1:
                self.fields['category'].initial = self.fields['category'].queryset.first()
        self.fields['setup_start'].initial = self.fields['setup_start'].prepare_value(
            self.event.datetime_setup_complete.replace(second=0, microsecond=0)
        )

    def clean(self):
        cleaned_data = super(CCIForm, self).clean()
        if cleaned_data.get('category') is None and cleaned_data.get('service') is None:
            self.add_error('category', 'category/service is a required field')
            self.add_error('service', 'category/service is a required field')
        return cleaned_data

    def save(self, commit=True):
        obj = super(CCIForm, self).save(commit=False)
        try:
            obj.category
        except Category.DoesNotExist:
            try:
                obj.category = obj.service.category
            except Service.DoesNotExist:
                pass
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = EventCCInstance
        fields = ('category', 'crew_chief', 'service', 'setup_location', 'setup_start')

    crew_chief = AutoCompleteSelectField('Members', required=True)
    setup_start = forms.SplitDateTimeField(initial=timezone.now)
    setup_location = GroupedModelChoiceField(
        queryset=Location.objects.filter(setup_only=True).select_related('building'),
        group_by_field="building",
        group_label=lambda group: group.name,
    )
    category = ModelChoiceField(queryset=Category.objects.all(), required=False)
    service = ModelChoiceField(queryset=Service.objects.all(), required=False)  # queryset gets changed in constructor


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
            self.save_m2m()
        return obj

    class Meta:
        model = EventAttachment
        fields = ('for_service', 'attachment', 'note')


class ExtraForm(forms.ModelForm):
    class Meta:
        model = ExtraInstance
        fields = ('extra', 'quant')

    extra = GroupedModelChoiceField(
        queryset=Extra.objects.filter(disappear=False),
        group_by_field="category",
        group_label=lambda group: group.name,
    )


class ServiceInstanceForm(forms.ModelForm):
    def __init__(self, event, *args, **kwargs):
        self.event = event
        super(ServiceInstanceForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        obj = super(ServiceInstanceForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = ServiceInstance
        fields = ('service', 'detail')
        widgets = {
            'detail': EasyMDEEditor(attrs={"show_preview":False}),
        }

    service = ModelChoiceField(queryset=Service.objects.filter(enabled_event2019=True))


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
        if setup_complete < datetime.datetime.now(datetime.timezone.utc):
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


class PostEventSurveyForm(forms.ModelForm):

    def __init__(self, event, *args, **kwargs):
        self.event = event
        self.helper = FormHelper()
        self.helper.form_class = "custom-survey-form"
        self.helper.layout = Layout(
            Div(
                Div(
                    HTML('<div class="striped">'),
                    'services_quality',
                    HTML('</div>'),
                    'lighting_quality',
                    HTML('<div class="striped">'),
                    'sound_quality',
                    HTML('</div>'),
                    HTML(
                        '<div class="row" style="padding-top: 1%; padding-bottom: 1%; padding-left: 1%">'
                        '<div class="col-md-4">'
                    ),
                    'work_order_method',
                    HTML('</div></div>'),
                    HTML('<div style="border-bottom: 2px solid gray; padding-bottom: 1%; margin: 0"></div>'),
                    HTML('<div id="workorder" style="display: none"><div class="striped">'),
                    'work_order_experience',
                    HTML('</div>'),
                    'work_order_ease',
                    HTML('<div class="striped" style="padding-bottom: 1%; margin-bottom: 1%">'),
                    Field('work_order_comments', style='max-width: 75%; margin: 1%;'),
                    HTML('</div></div>'),
                    css_class='col'
                ),
                css_class='row'
            ),
            Div(
                Div(
                    HTML('<br><br><h2>Please rate your level of agreement with the following statements.</h2><br>'),
                    HTML('<div class="striped">'),
                    'communication_responsiveness',
                    HTML('</div>'),
                    'pricelist_ux',
                    HTML('<div class="striped">'),
                    'setup_on_time',
                    HTML('</div>'),
                    'crew_respectfulness',
                    HTML('<div class="striped">'),
                    'price_appropriate',
                    HTML('</div>'),
                    'customer_would_return',
                    HTML('<br>'),
                    css_class='col'
                ),
                css_class='row'
            ),
            Div(
                Div(
                    HTML('<h2>Additional Comments</h2>'),
                    'comments',
                    css_class='col'
                ),
                css_class='row'
            ),
            FormActions(
                Submit('save', 'Submit'),
            ),
        )
        super(PostEventSurveyForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        obj = super(PostEventSurveyForm, self).save(commit=False)
        obj.event = self.event
        if commit:
            obj.save()
        return obj

    class Meta:
        model = PostEventSurvey
        fields = ('services_quality', 'lighting_quality', 'sound_quality', 'work_order_method', 'work_order_experience',
                  'work_order_ease', 'work_order_comments', 'communication_responsiveness', 'pricelist_ux',
                  'setup_on_time', 'crew_respectfulness', 'price_appropriate', 'customer_would_return', 'comments')

    services_quality = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('services_quality').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('services_quality').choices,
    )

    lighting_quality = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('lighting_quality').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('lighting_quality').choices,
    )

    sound_quality = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('sound_quality').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('sound_quality').choices,
    )

    work_order_method = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('work_order_method').verbose_name,
        widget=forms.Select,
        choices=PostEventSurvey._meta.get_field('work_order_method').choices,
    )

    work_order_ease = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('work_order_ease').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('work_order_ease').choices,
    )

    work_order_experience = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('work_order_experience').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('work_order_experience').choices,
    )

    communication_responsiveness = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('communication_responsiveness').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('communication_responsiveness').choices,
    )

    pricelist_ux = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('pricelist_ux').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('pricelist_ux').choices,
    )

    setup_on_time = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('setup_on_time').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('setup_on_time').choices,
    )

    crew_respectfulness = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('crew_respectfulness').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('crew_respectfulness').choices,
    )

    price_appropriate = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('price_appropriate').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('price_appropriate').choices,
    )

    customer_would_return = forms.ChoiceField(
        label=PostEventSurvey._meta.get_field('customer_would_return').verbose_name,
        widget=SurveyCustomRadioSelect,
        choices=PostEventSurvey._meta.get_field('customer_would_return').choices,
    )


class OfficeHoursForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.form_show_labels = False
        self.helper.layout = Layout(
            Field('day'),
            Field('location'),
            Field('hour_start'),
            Field('hour_end'),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(OfficeHoursForm, self).__init__(*args, **kwargs)
        self.fields['location'].queryset = Location.objects.filter(setup_only=True)

    class Meta:
        model = OfficeHour
        fields = ('day', 'location', 'hour_start', 'hour_end')


class WorkshopForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
            Field('name'),
            Field('instructors'),
            Field('description'),
            Field('location'),
            Field('notes'),
            FormActions(
                Submit('save', 'Save')
            )
        )
        super(WorkshopForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Workshop
        fields = ('name', 'instructors', 'description', 'location', 'notes')


class WorkshopDatesForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
            Field('workshop'),
            Field('date', css_class="form-control"),
            FormActions(
                Submit('save', 'Save')
            )
        )
        super(WorkshopDatesForm, self).__init__(*args, **kwargs)

    date = forms.SplitDateTimeField(required=False)

    class Meta:
        model = WorkshopDate
        fields = ('workshop', 'date')


class CrewCheckinForm(forms.Form):
    def __init__(self, *args, **kwargs):
        events = kwargs.pop('events')
        title = kwargs.pop('title')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6 m-auto"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
            HTML('<h2 class="h3">' + title + '</h2><br>'),
            Field('event'),
            HTML('<hr>'),
            FormActions(
                Submit('save', 'Submit')
            )
        )
        super(CrewCheckinForm, self).__init__(*args, **kwargs)

        options = []
        for event in events:
            if event.max_crew:
                options.append(
                    (event.pk, " %s (%i spots remaining)" %
                     (event.event_name, event.max_crew - event.crew_attendance.filter(active=True).count())))
            else:
                options.append((event.pk, " %s" % event.event_name))

        self.fields['event'] = forms.ChoiceField(choices=options, label="Select Event", widget=forms.RadioSelect)
        if len(options) == 1:
            self.fields['event'].initial = options[0][0]


class CrewCheckoutForm(forms.Form):
    checkin = forms.SplitDateTimeField(required=True, label="Verify Checkin Time")
    checkout = forms.SplitDateTimeField(required=True, label="Confirm Checkout Time")

    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal container"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        self.helper.layout = Layout(
            HTML('<br><h2 class="h3">Does this look correct?</h2><p>Review the checkin and checkout times listed '
                 'below and verify that they are accurate. Once you submit, you will not be able to edit this '
                 'information.<br><br></p>'),
            Field('checkin', css_class="control mb-2"),
            Field('checkout', css_class="control mb-2"),
            FormActions(
                Submit('save', 'Confirm')
            )
        )
        super(CrewCheckoutForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super(CrewCheckoutForm, self).clean()
        if cleaned_data['checkout'] > timezone.now():
            raise ValidationError('Ha, nice try. Unless you\'ve figured out time travel, you cannot submit a '
                                  'checkout time in the future.')


class CheckoutHoursForm(forms.Form):
    disabled_widget = forms.NumberInput(attrs={'readonly': True, 'step': 0.25})
    total = forms.DecimalField(label="Total", decimal_places=2, widget=disabled_widget, required=False)

    def __init__(self, *args, **kwargs):
        categories = kwargs.pop('categories')
        self.total_hrs = kwargs.pop('total_hrs')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal container"
        self.helper.form_method = "post"
        self.helper.form_action = ""
        hour_set = Row(css_class="justify-between")
        self.helper.layout = Layout(
            HTML('<br><h2 class="h3">Submit Hours</h2><p>If you\'d like to log the hours you have worked, please '
                 'indicate which services you helped provide.<br><br></p>'),
            hour_set,
            HTML('<hr>'),
            FormActions(
                Submit('save', 'Submit')
            )
        )
        super(CheckoutHoursForm, self).__init__(*args, **kwargs)

        self.fields['total'].initial = self.total_hrs
        for category in categories:
            self.fields['hours_%s' % category.name] = forms.DecimalField(label=category.name, required=False,
                                                                         min_value=0)
            hour_set.fields.append(Column('hours_%s' % category.name, css_class="mx-2"))
        hour_set.fields.append(Column('total', css_class="mx-2"))
        if len(categories) == 1:
            self.fields['hours_%s' % categories[0].name].initial = self.total_hrs

    def clean(self):
        cleaned_data = super(CheckoutHoursForm, self).clean()
        hour_fields = []
        for field in self.fields:
            if "hour" in field:
                hour_fields.append(field)
        total = 0
        for field in hour_fields:
            if cleaned_data[field]:
                total += self.cleaned_data[field]
        if total != self.total_hrs and total > 0:
            raise ValidationError('Hour totals do not match')


class BulkCheckinForm(forms.Form):
    secure_widget = forms.PasswordInput(attrs={'autofocus': 'autofocus'})
    id = forms.IntegerField(required=True, label="Scan / Swipe Student ID", widget=secure_widget)

    def __init__(self, *args, **kwargs):
        event = kwargs.pop('event')
        result = kwargs.pop('result')
        user_name = kwargs.pop('user_name')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-8 m-auto"
        self.helper.form_method = 'post'
        self.helper.form_action = ""
        output = HTML("")
        if result == 'checkin-success':
            output = HTML("<div class='alert alert-success w-75 m-auto'>Welcome " + user_name + "</div>")
        elif result == 'checkin-fail':
            output = HTML("<div class='alert alert-danger w-75 m-auto'>Checkin Failed - User is checked into "
                          "another event</div>")
        elif result == 'checkin-limit':
            output = HTML("<div class='alert alert-warning w-100 m-auto'>Checkin Failed - This event has reached its "
                          "crew member or occupancy limit</div>")
        elif result == 'checkout-success':
            output = HTML("<div class='alert alert-success w-75 m-auto'>Bye. Thanks for your help!</div>")
        elif result == 'fail':
            output = HTML("<div class='alert alert-danger w-75 m-auto'>Invalid ID</div>")
        elif result:
            output = HTML("<div class='alert w-75 m-auto' style='background-color: black; color: white'>"
                          "An unknown error occurred.</div>")
        self.helper.layout = Layout(
            HTML('<h2 class="h6"><strong>Event:</strong> ' + event + '</h2><br>'),
            Field('id'),
            FormActions(
                Submit('save', 'Enter', css_class="d-none")
            ),
            Div(output, css_class="mt-4 text-center")
        )
        super(BulkCheckinForm, self).__init__(*args, **kwargs)


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
Note: Any riders or documentation provided to you from the artist/performer which may help LNL
determine the technical needs of your event may be attached to this request once it is submitted by
going to your LNL account and selecting "Previous Workorders".
"""

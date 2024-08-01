import datetime

from ajax_select.fields import AutoCompleteSelectMultipleField
from crispy_forms.bootstrap import FormActions, Tab, TabHolder
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Button, Field, Layout, Submit, HTML
from django import forms
from django.db.models import Q
from django.forms.fields import SplitDateTimeField
from django.urls.base import reverse
from multiupload.fields import MultiFileField
from natural_duration import NaturalDurationField
from simplemde.widgets import SimpleMDEEditor

from data.forms import FieldAccessForm, FieldAccessLevel
from helpers.form_text import slack_channel_msgs
from events.models import Event2019, Location
from meetings.models import (CCNoticeSend, Meeting, MeetingAnnounce, MeetingType, MtgAttachment)


class MeetingAdditionForm(FieldAccessForm):
    def __init__(self, *args, **kwargs):
        super(MeetingAdditionForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.form_tag = False
        self.helper.include_media = False
        actions = FormActions(
            Submit('save', 'Save Changes')
        )
        if kwargs.get("instance", None):
            actions = FormActions(
                Submit('save', 'Save Changes'),
                HTML('<a class="btn btn-danger" href="{%% url "meetings:delete" %s %%}"> Delete </a>'
                     % kwargs.get("instance").pk),
            )
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'Basic Info',
                    'meeting_type',
                    'location',
                    Field('datetime', css_class='dtp'),
                    'duration'
                ),
                Tab(
                    'Attendance',
                    'attendance',
                ),
                Tab(
                    'Agenda',
                    'agenda',
                ),
                Tab(
                    'Open Minutes',
                    'minutes',
                    slack_channel_msgs,
                    'attachments'
                ),
                Tab(
                    'Closed Minutes',
                    'minutes_private',
                    slack_channel_msgs,
                    'attachments_private'
                ),
            ),
            actions
        )
        self.fields['duration'].widget.attrs['placeholder'] = "e.g. 1 minute"

    duration = NaturalDurationField(
        human_values=True, required=True,
        help_text='<span class="small">This field accepts a quantifier followed by a unit of time. '
                  '<a href="https://lnldb.readthedocs.io/en/latest/help/meetings/meeting-details.html">Learn more</a>'
    )
    attendance = AutoCompleteSelectMultipleField('Users', required=False)
    datetime = SplitDateTimeField(required=True, initial=datetime.datetime.today())
    location = forms.ModelChoiceField(queryset=Location.objects.filter(available_for_meetings=True), label="Location",
                                      required=False)
    meeting_type = forms.ModelChoiceField(queryset=MeetingType.objects.filter(archived=False), required=True)
    attachments = MultiFileField(max_file_size=1024 * 1024 * 20,  # 20 MB
                                 required=False)
    attachments_private = MultiFileField(max_file_size=1024 * 1024 * 20,  # 20 MB
                                         label="Closed Attachments",
                                         required=False)
    minutes = forms.CharField(widget=SimpleMDEEditor(),
                              required=False)
    agenda = forms.CharField(widget=SimpleMDEEditor(),
                             required=False)
    minutes_private = forms.CharField(widget=SimpleMDEEditor(), label="Closed Minutes", required=False)

    class Meta:
        model = Meeting
        widgets = {
            'datetime': forms.widgets.DateInput(attrs={"class": "datepick"}),
        }
        fields = ('meeting_type', 'location', 'datetime', 'attendance', 'duration',
                  'agenda', 'minutes', 'minutes_private')

    class FieldAccess:
        def __init__(self):
            pass

        hasperm = FieldAccessLevel(
            lambda user, instance: user.has_perm('meetings.edit_mtg', instance) or
                                   user.has_perm('meetings.create_mtg', instance),
            enable=('meeting_type', 'location', 'datetime', 'attendance', 'duration', 'agenda', 'minutes',
                    'attachments')
        )
        edit_closed = FieldAccessLevel(
            lambda user, instance: user.has_perm('meetings.view_mtg_closed', instance),
            enable=('minutes_private', 'attachments_private')
        )
        no_closed = FieldAccessLevel(
            lambda user, instance: not user.has_perm('meetings.view_mtg_closed', instance),
            exclude=('minutes_private',)
        )


class MtgAttachmentEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Submit'))
        super(MtgAttachmentEditForm, self).__init__(*args, **kwargs)
        self.helper.add_input(Button('delete', 'Delete',
                                     onClick='window.location.href="{}"'
                                     .format(reverse('meetings:att-rm',
                                                     args=(self.instance.meeting.pk, self.instance.pk))),
                                     css_class='btn-danger'))

    class Meta:
        model = MtgAttachment
        fields = ('name', 'file', 'private')


class AnnounceSendForm(forms.ModelForm):
    def __init__(self, meeting, *args, **kwargs):
        super(AnnounceSendForm, self).__init__(*args, **kwargs)
        now = meeting.datetime
        twodaysago = now + datetime.timedelta(days=-4)
        aweekfromnow = now + datetime.timedelta(days=9)
        self.meeting = meeting
        self.fields["events"].queryset = Event2019.objects.filter(
            datetime_setup_complete__gte=twodaysago, approved=True,
            datetime_setup_complete__lte=aweekfromnow
        ).exclude(Q(closed=True) | Q(cancelled=True))
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-7'
        self.helper.layout = Layout(
            'subject',
            'message',
            'email_to',
            Field('events', css_class="col-md-6", size="15"),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )

    def save(self, commit=True):
        self.instance = super(AnnounceSendForm, self).save(commit=False)
        self.instance.meeting = self.meeting
        if commit:
            self.instance.save()
            self.save_m2m()
        return self.instance

    class Meta:
        model = MeetingAnnounce
        fields = ('events', 'subject', 'message', 'email_to')
        widgets = {
            'message': SimpleMDEEditor(),
        }

    events = forms.ModelMultipleChoiceField(queryset=Event2019.objects.all(), required=False)


class AnnounceCCSendForm(forms.ModelForm):
    def __init__(self, meeting, *args, **kwargs):
        now = meeting.datetime
        twodaysago = now + datetime.timedelta(days=-4)
        aweekfromnow = now + datetime.timedelta(days=17)
        self.meeting = meeting

        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.label_class = 'col-lg-2'
        self.helper.field_class = 'col-lg-5'
        self.helper.layout = Layout(
            Field('events', css_class="col-md-6", size="15"),
            Field('addtl_message', css_class="col-md-6"),
            Field('email_to', css_class="col-md-6"),
            FormActions(
                Submit('save', 'Send'),
            ),
        )
        super(AnnounceCCSendForm, self).__init__(*args, **kwargs)

        self.fields["events"].queryset = Event2019.objects.filter(
            datetime_setup_complete__gte=twodaysago, approved=True,
            datetime_setup_complete__lte=aweekfromnow
        ).exclude(Q(closed=True) | Q(cancelled=True))

    def save(self, commit=True):
        self.instance = super(AnnounceCCSendForm, self).save(commit=False)
        self.instance.meeting = self.meeting
        if commit:
            self.instance.save()
            self.save_m2m()
        return self.instance

    class Meta:
        model = CCNoticeSend
        fields = ('events', 'addtl_message', 'email_to')
        widgets = {
            'addtl_message': SimpleMDEEditor()
        }
        # events = forms.ModelMultipleChoiceField(queryset=Event.objects.all(),required=False)

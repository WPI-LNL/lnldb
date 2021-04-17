import datetime

from ajax_select.fields import AutoCompleteSelectMultipleField
from crispy_forms.bootstrap import FormActions, Tab, TabHolder
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Button, Field, Layout, Submit
from django import forms
from django.db.models import Q
from django.forms.fields import SplitDateTimeField
from django.urls.base import reverse
from multiupload.fields import MultiFileField
from natural_duration import NaturalDurationField
from pagedown.widgets import PagedownWidget

from events.models import Event, Location
from meetings.models import (CCNoticeSend, Meeting, MeetingAnnounce,
                             MtgAttachment)


class MeetingAdditionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.form_tag = False
        self.helper.include_media = False
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
                    'attachments'
                ),
                Tab(
                    'Closed Minutes',
                    'minutes_private',
                    'attachments_private'
                ),
            ),
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(MeetingAdditionForm, self).__init__(*args, **kwargs)

    duration = NaturalDurationField(human_values=True, required=True)
    attendance = AutoCompleteSelectMultipleField('Users', required=False)
    datetime = SplitDateTimeField(required=True, initial=datetime.datetime.today())
    location = forms.ModelChoiceField(queryset=Location.objects.filter(available_for_meetings=True), label="Location",
                                      required=False)
    attachments = MultiFileField(max_file_size=1024 * 1024 * 20,  # 20 MB
                                 required=False)
    attachments_private = MultiFileField(max_file_size=1024 * 1024 * 20,  # 20 MB
                                         label="Closed Attachments",
                                         required=False)
    minutes = forms.CharField(widget=PagedownWidget(),
                              required=False)
    agenda = forms.CharField(widget=PagedownWidget(),
                             required=False)
    minutes_private = forms.CharField(widget=PagedownWidget(),
                                      label="Closed Minutes",
                                      required=False)

    class Meta:
        model = Meeting
        widgets = {
            'datetime': forms.widgets.DateInput(attrs={"class": "datepick"}),
        }
        fields = ('meeting_type', 'location', 'datetime', 'attendance', 'duration',
                  'agenda', 'minutes', 'minutes_private')


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
        self.fields["events"].queryset = Event.objects.filter(datetime_setup_complete__gte=twodaysago, approved=True,
                                                              datetime_setup_complete__lte=aweekfromnow).exclude(
            Q(closed=True) | Q(cancelled=True))
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
            'message': PagedownWidget(),
        }

    events = forms.ModelMultipleChoiceField(queryset=Event.objects.all(), required=False)


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

        self.fields["events"].queryset = Event.objects.filter(datetime_setup_complete__gte=twodaysago, approved=True,
                                                              datetime_setup_complete__lte=aweekfromnow).exclude(
            Q(closed=True) | Q(cancelled=True))

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
            'addtl_message': PagedownWidget()
        }
        # events = forms.ModelMultipleChoiceField(queryset=Event.objects.all(),required=False)

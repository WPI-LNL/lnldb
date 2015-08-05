import datetime

from django import forms
from django.db.models import Q
from django.forms.fields import SplitDateTimeField
from django.core.urlresolvers import reverse
from pagedown.widgets import PagedownWidget
from data.forms import FormFooter
from meetings.models import Meeting, MeetingAnnounce, CCNoticeSend, MtgAttachment
from events.models import Event, Location
from ajax_select.fields import AutoCompleteSelectMultipleField
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Field, Button
from crispy_forms.bootstrap import FormActions, TabHolder, Tab
from multiupload.fields import MultiFileField


class MeetingAdditionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'Basic Info',
                    'meeting_type',
                    'location',
                    'datetime',
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
            FormFooter('Save changes')
        )
        super(MeetingAdditionForm, self).__init__(*args, **kwargs)

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
                                     .format(reverse('meetings.views.rm_att',
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
        self.helper.field_class = 'col-lg-5'
        self.helper.layout = Layout(
            Field('events', css_class="col-md-6", size="15"),
            'subject',
            'message',
            'email_to',
            FormFooter('Save changes')
        )

    def save(self, commit=True):
        obj = super(AnnounceSendForm, self).save(commit=False)
        obj.meeting = self.meeting
        if commit:
            obj.save()
        return obj

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
            FormFooter('Send')
        )
        super(AnnounceCCSendForm, self).__init__(*args, **kwargs)

        self.fields["events"].queryset = Event.objects.filter(datetime_setup_complete__gte=twodaysago, approved=True,
                                                              datetime_setup_complete__lte=aweekfromnow).exclude(
            Q(closed=True) | Q(cancelled=True))

    def save(self, commit=True):
        obj = super(AnnounceCCSendForm, self).save(commit=False)
        obj.meeting = self.meeting
        if commit:
            obj.save()
        return obj

    class Meta:
        model = CCNoticeSend
        fields = ('events', 'addtl_message', 'email_to')
        widgets = {
            'addtl_message': PagedownWidget()
        }
        # events = forms.ModelMultipleChoiceField(queryset=Event.objects.all(),required=False)

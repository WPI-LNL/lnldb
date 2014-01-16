from django import forms
from django.forms import Form, ModelForm

import datetime

from meetings.models import Meeting,MeetingAnnounce,CCNoticeSend
from events.models import Event

from ajax_select import make_ajax_field
from ajax_select.fields import AutoCompleteSelectMultipleField,AutoCompleteSelectField

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML,Hidden
from crispy_forms.bootstrap import AppendedText,InlineCheckboxes,InlineRadios,Tab,TabHolder,FormActions

class MeetingAdditionForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            'datetime',
            'attendance',
            'meeting_type',
            FormActions(
                Submit('save', 'Save Changes'),
            )
        )
        super(MeetingAdditionForm,self).__init__(*args,**kwargs)
    attendance = AutoCompleteSelectMultipleField('Users',required=False)
    
    class Meta:
        model = Meeting
        widgets = {
            'datetime' :forms.widgets.DateInput(attrs={"class":"datepick"}),
        }
        
        
class AnnounceSendForm(forms.ModelForm):
    def __init__(self,meeting,*args,**kwargs):
        super(AnnounceSendForm,self).__init__(*args,**kwargs)
        now = meeting.datetime
        twodaysago = now + datetime.timedelta(days=-3)
        
        self.fields["events"].queryset = Event.objects.filter(datetime_setup_complete__gte=twodaysago)
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            Hidden('meeting',meeting.id),
            'events',
            'subject',
            'message',
            'email_to',
            FormActions(
                Submit('save', 'Save Changes'),
                )
            )
        
    class Meta:
        model = MeetingAnnounce
       
       
class AnnounceCCSendForm(forms.ModelForm):
    def __init__(self,meeting,*args,**kwargs):
        now = meeting.datetime
        twodaysago = now + datetime.timedelta(days=-3)
        
        
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            Hidden('meeting',meeting.id),
            'events',
            FormActions(
                Submit('save', 'Save Changes'),
                ),
            )
        super(AnnounceCCSendForm,self).__init__(*args,**kwargs)

        self.fields["events"].queryset = Event.objects.filter(datetime_setup_start__gte=twodaysago)
        
    class Meta:
        model = CCNoticeSend

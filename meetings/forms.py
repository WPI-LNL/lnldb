from django import forms
from django.forms import Form, ModelForm

from meetings.models import Meeting

from ajax_select import make_ajax_field
from ajax_select.fields import AutoCompleteSelectMultipleField,AutoCompleteSelectField

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML
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
                Submit('save', 'Save changes'),
            )
        )
        super(MeetingAdditionForm,self).__init__(*args,**kwargs)
    attendance = AutoCompleteSelectMultipleField('Users',required=False)
    
    class Meta:
        model = Meeting
        widgets = {
            'datetime' :forms.widgets.DateInput(attrs={"class":"datepick"}),
        }
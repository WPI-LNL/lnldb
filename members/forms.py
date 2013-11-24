from django import forms
from django.forms import Form, ModelForm, TextInput
from django.forms.extras.widgets import SelectDateWidget
from django.db.models import Q

from django.contrib.auth.models import User
from helpers.form_fields import django_msgs
from django.core.urlresolvers import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML
from crispy_forms.bootstrap import AppendedText,InlineCheckboxes,InlineRadios,Tab,TabHolder,FormActions

class MemberForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.layout = Layout(
            
            'username',
            'first_name',
            'last_name',
            'groups',
            FormActions(
                Submit('save', 'Update Member and Return'),
            )
        )
        super(MemberForm,self).__init__(*args,**kwargs)
        
    class Meta:
        model = User
        fields = ['username','first_name','last_name','groups']
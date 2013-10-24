from django import forms
from django.forms import Form, ModelForm, TextInput
from django.forms.extras.widgets import SelectDateWidget
from django.db.models import Q

from django.contrib.auth.models import User
from helpers.form_fields import django_msgs
from helpers.form_text import markdown_at_msgs
from django.core.urlresolvers import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML,Hidden,Reset
from crispy_forms.bootstrap import AppendedText,InlineCheckboxes,InlineRadios,Tab,TabHolder,FormActions,PrependedText

from projection.models import Projectionist

class ProjectionistUpdateForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal" 
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
                django_msgs,
                
                'pit_level',
                'license_number',
                Field('license_expiry',css_class="datepick"),
                FormActions(
                    Submit('save', 'Save changes'),
                )
        )
        super(ProjectionistUpdateForm,self).__init__(*args,**kwargs)
        
    class Meta:
        model = Projectionist
        fields = ('pit_level','license_number','license_expiry')
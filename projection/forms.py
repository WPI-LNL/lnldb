from django import forms
from django.forms import Form, ModelForm, TextInput
from django.forms.models import inlineformset_factory
from django.forms.extras.widgets import SelectDateWidget
from django.db.models import Q

import datetime

from django.contrib.auth.models import User
from helpers.form_fields import django_msgs
from helpers.form_text import markdown_at_msgs
from django.core.urlresolvers import reverse

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML,Hidden,Reset
from crispy_forms.bootstrap import AppendedText,InlineCheckboxes,InlineRadios,Tab,TabHolder,FormActions,PrependedText

from projection.models import Projectionist, PitInstance, PITLevel
from ajax_select.fields import AutoCompleteSelectField,AutoCompleteSelectMultipleField

class ProjectionistUpdateForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal" 
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_tag = False
        self.helper.layout = Layout(
                django_msgs,
                
                #'pit_level',
                'license_number',
                Field('license_expiry',css_class="datepick"),
        )
        super(ProjectionistUpdateForm,self).__init__(*args,**kwargs)
        
    class Meta:
        model = Projectionist
        fields = ('license_number','license_expiry')
        
class ProjectionistForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal" 
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.layout = Layout(
                django_msgs,
                'user',
                #'pit_level',
                'license_number',
                Field('license_expiry',css_class="datepick"),
                FormActions(
                    Submit('save', 'Save changes'),
                )
        )
        super(ProjectionistForm,self).__init__(*args,**kwargs)
        self.fields['user'].queryset = User.objects.exclude(projectionist__isnull=False)
    
    user =AutoCompleteSelectField('Users', required=True, plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})
    class Meta:
        model = Projectionist
        fields = ('user','license_number','license_expiry')
        
class InstanceForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field('pit_level'),
            Field('created_on',css_class="dtp"),
            Field('valid'),
            HTML('<hr>'),
        )
        super(InstanceForm,self).__init__(*args,**kwargs)
        
    class Meta:
        model = PitInstance
    created_on =  forms.SplitDateTimeField(initial=datetime.datetime.now())
    
    
class BulkUpdateForm(forms.Form):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('users'),
            Field('date',css_class="datepick"),
            Field('pit_level'),
            FormActions(
                Submit('save', 'Save changes'),
            )
        )
        super(BulkUpdateForm,self).__init__(*args,**kwargs)
    users = AutoCompleteSelectMultipleField('Users', required=True, plugin_options={'position':"{ my : \"right top\", at: \"right bottom\", of: \"#id_person_name_text\"},'minlength':4"})
    date = forms.DateField()
    pit_level = forms.ModelChoiceField(queryset=PITLevel.objects.all(), empty_label=None)
    
    def create_updates(self):
        i = self.cleaned_data
        for user in i['users']:
            p,created = Projectionist.objects.get_or_create(user_id=user)
            PitInstance.objects.create(projectionist=p,pit_level=i['pit_level'],created_on=i['date'])
            
        
        
PITFormset = inlineformset_factory(Projectionist,PitInstance,extra=1,form=InstanceForm)#,formset=ProjectionistUpdateForm)
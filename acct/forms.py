from django.contrib.auth.models import User
from django import forms
from django.forms.models import inlineformset_factory

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML
from crispy_forms.bootstrap import AppendedText,InlineCheckboxes,InlineRadios,Tab,TabHolder,FormActions

from helpers.form_fields import django_msgs

from acct.models import Profile

class UserAcct(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''

        self.helper.layout = Layout(
                django_msgs,
                'username',
                'first_name',
                'last_name',
                FormActions(
                    Submit('save', 'Save changes'),
                )
        )
        super(UserAcct,self).__init__(*args,**kwargs)
    class Meta:
        model = User
        
        fields = ('first_name','last_name')
       
class ProfileAcct(forms.ModelForm):
    class Meta:
        model = Profile
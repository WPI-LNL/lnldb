from django.forms import ModelForm
from inventory.models import Equipment

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout,Fieldset,Button,ButtonHolder,Submit,Div,MultiField,Field,HTML
from crispy_forms.bootstrap import AppendedText,InlineCheckboxes,Tab,TabHolder,FormActions

class InvForm(ModelForm):
    def __init__(self,*args,**kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
        TabHolder(
            Tab(
                'Name And Categorization',
                'name',
                'subcategory',
                'major',
                'description',
            ),
            Tab(
                'Purchase Information',
                'purchase_date',
                'purchase_cost',
                ),
            Tab(
                'General Info',
                'model_number',
                'serial_number',
                'road_case',
                'manufacturer',
                'home',
                ),
            ),
            FormActions(
                Submit('save', 'Save changes'),
            )
        )
        super(InvForm,self).__init__(*args,**kwargs)
    class Meta:
        model = Equipment
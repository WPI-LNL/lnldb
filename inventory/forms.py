from django.forms import ModelForm
from inventory.models import Equipment, EquipmentMaintEntry

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Fieldset, Submit, Field, Hidden
from crispy_forms.bootstrap import Tab, TabHolder, FormActions

from helpers.form_text import markdown_at_msgs
from helpers.form_fields import django_msgs


class InvForm(ModelForm):
    def __init__(self, *args, **kwargs):
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
        super(InvForm, self).__init__(*args, **kwargs)

    class Meta:
        model = Equipment


class EntryForm(ModelForm):
    def __init__(self, user, equipment, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            Fieldset(
                'Maintenance Information',
                django_msgs,
                Field('desc', label="Description", css_class="span8"),
                Field('entry', css_class="span8"),
                markdown_at_msgs,
                Field('status', css_class="span8"),
                Hidden('user', user.id),
                Hidden('equipment', equipment.id),
            ),

            FormActions(
                Submit('save', 'Save changes'),
            )
        )
        super(EntryForm, self).__init__(*args, **kwargs)

    class Meta:
        model = EquipmentMaintEntry
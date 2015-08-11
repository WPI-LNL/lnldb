from ajax_select.fields import AutoCompleteSelectField, autoselect_fields_check_can_add
from django import forms
from django.core.exceptions import ValidationError
from django.forms import ModelForm, Form, ModelChoiceField, CharField
from mptt.forms import TreeNodeChoiceField
from pagedown.widgets import PagedownWidget
from inventory.models import *


from crispy_forms.helper import FormHelper
from crispy_forms import layout
from crispy_forms.layout import Layout, Fieldset, Submit, Field, Hidden, Column, Div, HTML
from crispy_forms.bootstrap import Tab, TabHolder, FormActions


class CategoryForm(ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            'name',
            'parent',
            'usual_place',
            FormActions(
                Submit('save', 'Save changes'),
            )
        )
        super(CategoryForm, self).__init__(*args, **kwargs)
        self.fields['usual_place'].queryset = EquipmentCategory.possible_locations()

    def clean_parent(self):
        if self.cleaned_data['parent'] in self.instance.get_descendants_inclusive:
            raise ValidationError('A category cannot be a subcategory of itself or one of its children.')

    class Meta:
        model = EquipmentCategory
        fields = ('name', 'usual_place', 'parent')


class EquipmentItemForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(EquipmentItemForm, self).__init__(*args, **kwargs)
        self.fields['home'].queryset = EquipmentCategory.possible_locations()

    class Meta:
        model = EquipmentItem
        fields = ('barcode', 'purchase_date', 'home', 'serial_number', 'features')


class EquipmentClassForm(ModelForm):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            TabHolder(
                Tab(
                    'Basic Info',
                    'name',
                    'category',
                    'description',
                    'url',
                ),
                Tab(
                    'Detailed Information',
                    'manufacturer',
                    'model_number',
                    'value',
                    'weight',
                    'length',
                    'width',
                    'height'
                ),
                Tab(
                    'Wiki',
                    'wiki_text'
                ),
            ),
            FormActions(
                Submit('save', 'Save changes'),
            )
        )
        super(EquipmentClassForm, self).__init__(*args, **kwargs)

    class Meta:
        model = EquipmentClass
        fields = ('name', 'category', 'description', 'value', 'url',
                  'model_number', 'manufacturer', 'length', 'width', 'height', 'weight',
                  'wiki_text')
        widgets = {
            'description': PagedownWidget(),
            'wiki_text': PagedownWidget(),
        }


class FastAdd(Form):
    item_name = CharField(label="New Item Type Name", required=False)
    item_cat = TreeNodeChoiceField(EquipmentCategory.objects.all(),
                                   label="New Item Category", required=False)

    num_to_add = forms.IntegerField(min_value=1)
    item_type = AutoCompleteSelectField('EquipmentClass', help_text=None,
                                        label="Select Existing Item Type", required=False,
                                        plugin_options={'autoFocus': True})

    def __init__(self, user, *args, **kwargs):
        self.helper = FormHelper()
        self.can_add = user.has_perm('inventory.add_equipmentclass')
        if self.can_add:
            self.helper.layout = Layout(
                Div(Div('item_type',
                        HTML('<span style="font-size:24pt;">OR</span>'),
                        layout.Row(Div('item_name', css_class='col-md-6'),
                                   Div('item_cat', css_class='col-md-6')),
                        css_class='panel-body'),
                    css_class='panel panel-default'),
                'num_to_add',
                FormActions(
                    Submit('save', 'Save changes'),
                )
            )
        else:
            self.helper.layout = Layout(
                Div(Div('item_type',
                        css_class='panel-body'),
                    css_class='panel panel-default'),
                'num_to_add',
                FormActions(
                    Submit('save', 'Save changes'),
                )
            )
        super(FastAdd, self).__init__(*args, **kwargs)

    def clean(self):
        data = self.cleaned_data
        if data.get('item_type', None):
            return data
        elif not self.can_add:
            raise forms.ValidationError('Choose an equipment type')
        elif data.get('item_name', None) and data.get('item_cat', None):
            return data
        elif data.get('item_name', None) or data.get('item_cat', None):
            raise forms.ValidationError('Provide both a name and category for the new type.')
        else:
            raise forms.ValidationError('Choose a type or enter information for a new one')

    def save(self):
        data = self.cleaned_data
        if data.get('item_type', None):
            e_type = data.get('item_type', None)
        else:
            e_type = EquipmentClass.objects.create(name=data['item_name'], category=data['item_cat'])
            e_type.save()

        EquipmentItem.objects.bulk_add_helper(e_type, data['num_to_add'])

        return e_type

#
# class EntryForm(ModelForm):
#     def __init__(self, user, equipment, *args, **kwargs):
#         self.helper = FormHelper()
#         self.helper.form_class = 'form-horizontal'
#         self.helper.layout = Layout(
#             Fieldset(
#                 'Maintenance Information',
#                 Field('desc', label="Description", css_class="span8"),
#                 Field('entry', css_class="span8"),
#                 markdown_at_msgs,
#                 Field('status', css_class="span8"),
#                 Hidden('user', user.id),
#                 Hidden('equipment', equipment.id),
#             ),
#
#             FormActions(
#                 Submit('save', 'Save changes'),
#             )
#         )
#         super(EntryForm, self).__init__(*args, **kwargs)
#
#     class Meta:
#         model = EquipmentMaintEntry
#         fields = ('desc', 'entry', 'status', 'user', 'equipment')
#         widgets = {'user': forms.HiddenInput(), 'equipment': forms.HiddenInput()}

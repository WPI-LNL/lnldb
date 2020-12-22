from django import forms
from crispy_forms.bootstrap import FormActions, Tab, TabHolder
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Hidden, Layout, Submit
from ajax_select.fields import AutoCompleteSelectField, AutoCompleteSelectMultipleField

from . import models

# Inventory is now read-only since we are now using Snipe
# from crispy_forms import layout
# from django.core.exceptions import ValidationError
# from django.forms import CharField, Form, ModelForm
# from mptt.forms import TreeNodeChoiceField
# from pagedown.widgets import PagedownWidget


# class CategoryForm(ModelForm):
#     def __init__(self, *args, **kwargs):
#         super(CategoryForm, self).__init__(*args, **kwargs)
#         self.helper = FormHelper()
#         self.helper.form_class = 'form-horizontal'
#         self.helper.layout = Layout(
#             'name',
#             'parent',
#             'usual_place',
#             FormActions(
#                 Submit('save', 'Save changes'),
#             )
#         )
#         self.fields['usual_place'].queryset = models.EquipmentCategory.possible_locations()
#
#     def clean_parent(self):
#         if self.instance.pk:
#             if self.cleaned_data['parent'] == self.instance:
#                 raise ValidationError('A category cannot be a subcategory of itself.')
#             if self.cleaned_data['parent'] in self.instance.get_descendants_inclusive:
#                 raise ValidationError('A category cannot be a subcategory of one of its children.')
#         return self.cleaned_data['parent']
#
#     class Meta:
#         model = models.EquipmentCategory
#         fields = ('name', 'usual_place', 'parent')
#
#
# class EquipmentItemForm(ModelForm):
#     case = AutoCompleteSelectField('EquipmentContainer', label="Put into container",
#                                    required=False)
#
#     def __init__(self, *args, **kwargs):
#         self.helper = FormHelper()
#         self.helper.layout = Layout(
#             'features',
#             'purchase_date',
#             layout.Row(Div('barcode', css_class='col-md-6'),
#                        Div('serial_number', css_class='col-md-6')),
#             Div(Div(Field('home', help_text="Place where this belongs"),
#                     HTML('<span style="font-size:24pt;">OR</span>'),
#                     'case',
#                     css_class='panel-body'),
#                 css_class='panel panel-default'),
#             FormActions(
#                 Submit('save', 'Save changes'),
#             )
#         )
#         super(EquipmentItemForm, self).__init__(*args, **kwargs)
#         self.fields['home'].queryset = models.EquipmentCategory.possible_locations()
#
#     def clean_case(self):
#         if self.instance.pk:
#             if self.cleaned_data['case'] == self.instance:
#                 raise ValidationError('You cannot put an item inside itself.')
#             if self.cleaned_data['case'] in self.instance.get_descendants():
#                 raise ValidationError('You cannot put an item inside an item inside itself.')
#         return self.cleaned_data['case']
#
#     class Meta:
#         model = models.EquipmentItem
#         fields = ('barcode', 'purchase_date', 'case', 'home', 'serial_number', 'features')
#
#
# class EquipmentClassForm(ModelForm):
#     def __init__(self, *args, **kwargs):
#         self.helper = FormHelper()
#         self.helper.form_class = 'form-horizontal'
#         self.helper.layout = Layout(
#             TabHolder(
#                 Tab(
#                     'Basic Info',
#                     'name',
#                     'category',
#                     'description',
#                     'url',
#                     'holds_items',
#                 ),
#                 Tab(
#                     'Detailed Information',
#                     'manufacturer',
#                     'model_number',
#                     'value',
#                     'weight',
#                     'length',
#                     'width',
#                     'height'
#                 ),
#                 Tab(
#                     'Wiki',
#                     'wiki_text'
#                 ),
#             ),
#             FormActions(
#                 Submit('save', 'Save changes'),
#             )
#         )
#         super(EquipmentClassForm, self).__init__(*args, **kwargs)
#
#     class Meta:
#         model = models.EquipmentClass
#         fields = ('name', 'category', 'description', 'value', 'url',
#                   'model_number', 'manufacturer', 'length', 'width', 'height', 'weight',
#                   'wiki_text', 'holds_items')
#         widgets = {
#             'description': PagedownWidget(),
#             'wiki_text': PagedownWidget(),
#         }
#
#
# class FastAdd(Form):
#     item_name = CharField(label="New Item Type Name", required=False)
#     item_cat = TreeNodeChoiceField(models.EquipmentCategory.objects.all(),
#                                    label="New Item Category", required=False)
#
#     num_to_add = forms.IntegerField(min_value=1)
#     item_type = AutoCompleteSelectField('EquipmentClass', help_text=None,
#                                         label="Select Existing Item Type", required=False,
#                                         plugin_options={'autoFocus': True})
#
#     put_into = AutoCompleteSelectField('EquipmentContainer', label="(Optional) Put into container",
#                                        required=False)
#
#     def __init__(self, user, *args, **kwargs):
#         self.helper = FormHelper()
#         self.can_add = user.has_perm('inventory.add_equipmentclass')
#         if self.can_add:
#             self.helper.layout = Layout(
#                 Div(Div('item_type',
#                         HTML('<span style="font-size:24pt;">OR</span>'),
#                         layout.Row(Div('item_name', css_class='col-md-6'),
#                                    Div('item_cat', css_class='col-md-6')),
#                         css_class='panel-body'),
#                     css_class='panel panel-default'),
#                 layout.Row(Div('num_to_add', css_class='col-md-6'),
#                            Div('put_into', css_class='col-md-6')),
#                 FormActions(
#                     Submit('save', 'Save changes'),
#                 )
#             )
#         else:
#             self.helper.layout = Layout(
#                 Div(Div('item_type',
#                         css_class='panel-body'),
#                     css_class='panel panel-default'),
#                 layout.Row(Div('num_to_add', css_class='col-md-6'),
#                            Div('put_into', css_class='col-md-6')),
#                 FormActions(
#                     Submit('save', 'Save changes'),
#                 )
#             )
#         super(FastAdd, self).__init__(*args, **kwargs)
#
#     def clean(self):
#         data = self.cleaned_data
#         if data.get('item_type', None):
#             return data
#         elif not self.can_add:
#             raise forms.ValidationError('Choose an equipment type')
#         elif data.get('item_name', None) and data.get('item_cat', None):
#             return data
#         elif data.get('item_name', None) or data.get('item_cat', None):
#             raise forms.ValidationError('Provide both a name and category for the new type.')
#         else:
#             raise forms.ValidationError('Choose a type or enter information for a new one')
#
#     def save(self):
#         data = self.cleaned_data
#         if data.get('item_type', None):
#             e_type = data.get('item_type', None)
#         else:
#             e_type = models.EquipmentClass.objects.create(name=data['item_name'], category=data['item_cat'])
#             e_type.save()
#
#         models.EquipmentItem.objects.bulk_add_helper(e_type, data['num_to_add'])
#
#         return e_type


class SnipeCheckoutForm(forms.Form):
    def __init__(self, checkout_to_choices, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.help_text_inline = True
        self.helper.layout = Layout(
            HTML('<p>This form should be used for rental checkouts. It will check out the specified assets and '
                 'accessories to the selected user in Snipe.</p>'),
            'checkout_to',
            'asset_tags',
            HTML('<p>Do not press "Check out" more than once. Be patient. It WILL take a while for the DB to check '
                 'out a large number of assets.</p>'),
            FormActions(
                Submit('save', 'Check out'),
            )
        )
        super(SnipeCheckoutForm, self).__init__(*args, **kwargs)
        self.fields['checkout_to'] = forms.IntegerField(
            widget=forms.Select(choices=checkout_to_choices), help_text='This dropdown contains all Snipe users in the '
                                                                        '"rental" group.')

    asset_tags = forms.CharField(widget=forms.Textarea(),
                                 help_text='Enter asset tags and accessory barcodes separated by any non-alphanumeric '
                                           'character, white space, or new lines. For accessories, scan the accessory '
                                           'barcode multiple times for the number of that accessory being checked out.')


class SnipeCheckinForm(forms.Form):
    def __init__(self, checkin_from_choices, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.help_text_inline = True
        self.helper.layout = Layout(
            HTML('<p>This form should be used for rental checkins. It will check in the specified assets and '
                 'accessories from the selected user in Snipe.</p>'),
            'checkin_from',
            'asset_tags',
            HTML('<p>Do not press "Check in" more than once. Be patient. It WILL take a while for the DB to check in '
                 'a large number of assets.</p>'),
            FormActions(
                Submit('save', 'Check in'),
            )
        )
        super(SnipeCheckinForm, self).__init__(*args, **kwargs)
        self.fields['checkin_from'] = forms.IntegerField(
            widget=forms.Select(choices=checkin_from_choices), help_text='This dropdown contains all Snipe users in the '
                                                                         '"rental" group.')

    asset_tags = forms.CharField(widget=forms.Textarea(),
                                 help_text='Enter asset tags and accessory barcodes separated by any non-alphanumeric '
                                           'character, white space, or new lines. For accessories, scan the accessory '
                                           'barcode multiple times for the number of that accessory being checked in.')


class AccessForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        space = kwargs.pop('location')
        r = kwargs.pop('reason')
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal col-md-6 m-auto"
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        title = "Sign in"
        if not r:
            reason_field = Field('reason')
        else:
            reason_field = Hidden('reason', value=r)
            if r == "OUT":
                title = "Sign out"
        self.helper.layout = Layout(
            HTML('<h2 class="h3">' + title + '</h2><br><p><strong>Location: </strong>' + space + '</p><hr>'),
            Field('users'),
            reason_field,
            FormActions(
                Submit('save', 'Submit')
            )
        )
        super(AccessForm, self).__init__(*args, **kwargs)

    users = AutoCompleteSelectMultipleField('Users', label="Select Members",
                                            help_text="<span class='small'>Enter text to search. List everyone who is "
                                                      "with you. Each member only needs to be checked in once per "
                                                      "visit.</span><br><br>")
    reason = forms.CharField(label="Reason for visit")

    class Meta:
        model = models.AccessRecord
        fields = ('users', 'reason')

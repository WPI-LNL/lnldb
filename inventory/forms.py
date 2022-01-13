from django import forms
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Layout, Submit


class SnipeRentalForm(forms.Form):
    def __init__(self, rental_clients, checkout, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.form_action = ''
        self.helper.form_tag = False
        self.helper.help_text_inline = True
        if checkout:
            description = '<p>This form should be used for rental checkouts. It will check out the specified assets ' \
                          'and accessories to the selected user in Snipe.</p>'
        else:
            description = '<p>This form should be used for rental checkins. It will check in the specified assets and '\
                          'accessories from the selected user in Snipe.</p>'
        self.helper.layout = Layout(
            HTML(description),
            'renter',
            'asset_tag',
            'saved_tags',
            FormActions(
                Submit('save', 'Add item'),
            )
        )
        super(SnipeRentalForm, self).__init__(*args, **kwargs)
        self.fields['renter'] = forms.IntegerField(
            widget=forms.Select(choices=rental_clients), help_text='This dropdown contains all Snipe users in the '
                                                                   '"rental" group.')

    saved_tags = forms.CharField(required=False, widget=forms.HiddenInput)
    asset_tag = forms.CharField(help_text='Enter or scan an asset tag or accessory barcode. Note that for accessories, '
                                          'you may need to scan the barcode multiple times for the number of that '
                                          'accessory being rented.', required=False,
                                widget=forms.TextInput(attrs={'autofocus': ''}))


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
            HTML('<p>Do not press "Check out" more than once. Be patient. It WILL take a while for the DB to check out '
                 'a large number of assets.</p>'),
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

from django import forms
from .models import Position
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit

class UpdateCreatePosition(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Submit'))
    class Meta:
        model = Position
        fields = ('name', 'description', 'position_start', 'position_end',
                'closes', 'reports_to', 'application_form')

from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from ajax_select.fields import AutoCompleteSelectField, AutoCompleteSelectMultipleField
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Field, Fieldset, Hidden, Layout, Reset, Submit

from .models import TrainingType, Trainee, Training

class TrainingForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.helper = FormHelper()
        self.helper.help_text_inline = True
        self.helper.layout = Layout(
            HTML('<h1>Record a Training</h1>'),
            'training_type',
            'date',
            'trainer',
            'trainees',
            'expiration_date',
            'notes',
            FormActions(
                Submit('save', 'Save'),
            )
        )
        super(TrainingForm, self).__init__(*args, **kwargs)

    def clean_date(self):
        if self.cleaned_data['date'] > date.today():
            raise ValidationError('This date must not be in the future.')
        return self.cleaned_data['date']

    def clean_trainer(self):
        if not 'training_type' in self.cleaned_data:
            return self.cleaned_data['trainer']
        if self.cleaned_data['trainer'] is None:
            if self.cleaned_data['training_type'].external:
                return self.cleaned_data['trainer']
            raise ValidationError('The trainer must be specified for internal trainings.')
        for training in self.cleaned_data['trainer'].trainings.filter(training__training_type=self.cleaned_data['training_type']):
            if training.was_valid_on(self.cleaned_data['date']):
                return self.cleaned_data['trainer']
        raise ValidationError('The trainer did not possess valid {} on the date specified.'.format(self.cleaned_data['training_type']))

    def clean_trainees(self):
        if 'trainer' in self.cleaned_data and self.cleaned_data['trainer'] in get_user_model().objects.filter(id__in=self.cleaned_data['trainees']):
            raise ValidationError('Self-training is not allowed. ' + str(self.cleaned_data['trainer']) + ' may not train his/herself.')
        return self.cleaned_data['trainees']

    training_type = forms.ModelChoiceField(queryset=TrainingType.objects.all())
    date = forms.DateField()
    trainer = AutoCompleteSelectField('Users', required=False)
    trainees = AutoCompleteSelectMultipleField('Users')
    expiration_date = forms.DateField(required=False)
    notes = forms.CharField(widget=forms.Textarea(), required=False)

class TraineeNotesForm(forms.ModelForm):
    class Meta:
        model = Trainee
        fields = 'notes',

    def __init__(self, *args, **kwargs):
        super(TraineeNotesForm, self).__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.help_text_inline = True
        self.helper.layout = Layout(
            HTML('<h2>Edit notes on {} for {}</h2>'.format(self.instance.person, self.instance.training)),
            'notes',
            FormActions(
                Submit('save', 'Save'),
            )
        )
